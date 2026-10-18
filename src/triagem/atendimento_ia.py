"""Atendimento pela IA (ADR-019): urgência baixa e média é respondida sozinha; alta e crítica vão para um atendente.

- Depois da triagem, `iniciar` decide o modo do atendimento. Baixa ou média: a IA envia a resposta ao cliente e passa
  a responder cada nova mensagem (`responder`), com a conversa como contexto. Alta ou crítica, ou triagem feita pelo
  plano B (sem a IA): vai direto para a fila do Atendimento, para uma pessoa.
- A IA passa a conversa para um atendente (`escalar`) quando ela demora demais (minutos desde a 1ª mensagem ou número
  de respostas da IA, limites em app_config), quando o cliente pede uma pessoa ou quando a IA falha. O cliente é
  avisado e o atendimento volta para "Em espera" até uma pessoa responder.
- Se um atendente responde num atendimento da IA, ele assume (`assumir`).
As respostas da IA são assinadas como AUTOR_IA e não contam como resposta humana na fila.
"""
import logging
import re
from typing import Optional

from sqlalchemy import text

from . import sla, tickets
from .classifier import LLMError, sugerir_resposta
from .db import get_engine, utcnow
from .idioma import detectar

logger = logging.getLogger(__name__)

AUTOR_IA = tickets.AUTOR_IA
URGENCIAS_IA = ("baixa", "media")

# Pedido explícito para falar com uma pessoa (pt, en e es).
PEDE_PESSOA = re.compile(
    r"\b(atendente|humano|humana|pessoa de verdade|algu[eé]m de verdade|falar com (um|uma|o|a)?\s*"
    r"(pessoa|gerente|supervisor|supervisora|respons[aá]vel)|operador|operadora|"
    r"human|real person|agent|representative|persona real|agente)\b",
    re.IGNORECASE,
)

TRANSFERENCIA = {
    "pt": "Vou te transferir para um atendente da nossa equipe, que continua com você por aqui em instantes. Obrigado pela paciência!",
    "en": "I'm transferring you to one of our agents, who will continue with you here shortly. Thank you for your patience!",
    "es": "Voy a transferirte a un agente de nuestro equipo, que seguirá contigo por aquí en unos instantes. ¡Gracias por tu paciencia!",
}


def _config() -> dict:
    with get_engine().connect() as conn:
        return sla.carregar_config(conn)


def _definir_modo(ticket_id: int, modo: str, motivo: Optional[str] = None, escalado: bool = False) -> None:
    with get_engine().begin() as conn:
        if escalado:
            conn.execute(text("UPDATE tickets SET modo = :m, escalado_em = :q, motivo_escalada = :r WHERE id = :id"),
                         {"m": modo, "q": utcnow(), "r": (motivo or "")[:160], "id": ticket_id})
        else:
            conn.execute(text("UPDATE tickets SET modo = :m WHERE id = :id"), {"m": modo, "id": ticket_id})


def _conversa(ticket_id: int) -> list[tuple[str, str]]:
    return [("cliente" if m["direcao"] == "entrada" else "atendente", m["texto"])
            for m in tickets.mensagens(ticket_id) if m["texto"]]


def iniciar(ticket_id: int) -> str:
    """Logo depois da triagem: decide quem atende. Retorna ia | humano | ignorado. Nunca levanta exceção."""
    try:
        t = tickets.obter(ticket_id)
        if t.get("desfecho") or t.get("modo") or t["status"] == "pendente":
            return "ignorado"
        cfg = _config()
        if not cfg.get("ia_auto_ativo") or t.get("urgencia") not in URGENCIAS_IA or t.get("origem") != "llm" \
                or not t.get("resposta_sugerida"):
            _definir_modo(ticket_id, "humano")
            return "humano"
        tickets.responder_chat(ticket_id, t["resposta_sugerida"], AUTOR_IA)
        _definir_modo(ticket_id, "ia")
        logger.info("ticket %s: urgência %s, a IA atende", ticket_id, t.get("urgencia"))
        return "ia"
    except Exception:
        logger.exception("erro ao iniciar o atendimento do ticket %s", ticket_id)
        try:
            _definir_modo(ticket_id, "humano")
        except Exception:
            pass
        return "humano"


def motivo_para_atendente(t: dict, conversa: list[tuple[str, str]], cfg: dict, agora=None) -> Optional[str]:
    """Por que a IA deve passar a conversa para uma pessoa (ou None, se ela continua)."""
    agora = agora or utcnow()
    ultima = next((texto for papel, texto in reversed(conversa) if papel == "cliente"), "")
    if PEDE_PESSOA.search(ultima or ""):
        return "o cliente pediu para falar com uma pessoa"
    minutos = (agora - t["received_at"]).total_seconds() / 60
    if minutos >= cfg.get("ia_max_minutos", 15):
        return f"atendimento da IA passou de {int(cfg.get('ia_max_minutos', 15))} min"
    respostas_ia = sum(1 for m in tickets.mensagens(t["ticket_id"]) if m["direcao"] == "saida" and m["autor"] == AUTOR_IA)
    if respostas_ia >= cfg.get("ia_max_respostas", 5):
        return f"a IA já respondeu {respostas_ia} vezes sem resolver"
    return None


def escalar(ticket_id: int, motivo: str, idioma: Optional[str] = None) -> None:
    """Passa a conversa para um atendente: avisa o cliente e devolve o atendimento para a fila."""
    aviso = TRANSFERENCIA.get(idioma or "pt", TRANSFERENCIA["en"])
    try:
        tickets.responder_chat(ticket_id, aviso, AUTOR_IA)
    except Exception:
        logger.exception("não consegui avisar o cliente do ticket %s sobre a transferência", ticket_id)
    _definir_modo(ticket_id, "humano", motivo, escalado=True)
    logger.info("ticket %s vai para um atendente: %s", ticket_id, motivo)


def responder(ticket_id: int, mensagem_id: Optional[int] = None) -> str:
    """Nova mensagem do cliente num atendimento da IA: responde ou passa para uma pessoa.

    Retorna: respondida | escalada | humano (não é atendimento da IA) | ignorado. Nunca levanta exceção.
    """
    try:
        t = tickets.obter(ticket_id)
        if t.get("desfecho") or t.get("modo") != "ia":
            return "humano"
        entradas = [m for m in tickets.mensagens(ticket_id) if m["direcao"] == "entrada"]
        if mensagem_id is not None and entradas and entradas[-1]["id"] != mensagem_id:
            return "ignorado"  # chegou outra mensagem depois desta: a tarefa dela responde
        conversa = _conversa(ticket_id)
        ultima = next((texto for papel, texto in reversed(conversa) if papel == "cliente"), "")
        idioma = detectar(ultima).codigo if ultima else t.get("idioma")
        motivo = motivo_para_atendente(t, conversa, _config())
        if motivo:
            escalar(ticket_id, motivo, idioma)
            return "escalada"
        triagem = {k: t.get(k) for k in ("assunto", "urgencia", "sentimento", "equipe")}
        try:
            resposta = sugerir_resposta(conversa, triagem)
        except LLMError as exc:
            escalar(ticket_id, f"a IA não conseguiu responder ({exc})", idioma)
            return "escalada"
        tickets.responder_chat(ticket_id, resposta, AUTOR_IA)
        return "respondida"
    except Exception:
        logger.exception("erro no atendimento da IA do ticket %s", ticket_id)
        try:
            escalar(ticket_id, "erro no atendimento da IA")
        except Exception:
            pass
        return "escalada"


def assumir(ticket_id: int, quem: Optional[str]) -> None:
    """Um atendente respondeu num atendimento da IA: a conversa passa a ser dele."""
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE tickets SET modo = 'humano', escalado_em = COALESCE(escalado_em, :q), "
                 "motivo_escalada = COALESCE(motivo_escalada, :r) WHERE id = :id AND modo = 'ia'"),
            {"q": utcnow(), "r": f"assumido por {quem or 'um atendente'}"[:160], "id": ticket_id},
        )
