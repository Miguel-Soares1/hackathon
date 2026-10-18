"""Atendimento automático pela IA (ADR-022): toda mensagem é atendida na hora, sem sugestão para revisar.

A IA resolve o que dá para resolver com orientação ou encaminha para a equipe da triagem (financeiro, suporte técnico,
engenharia, retenção, atendimento) e avisa o cliente, no idioma dele, para quem o caso foi.
- Encaminha direto, sem perguntar ao modelo: urgência alta ou crítica, pedido de cancelamento, ameaça de cancelar ou
  de sair, exigência de solução imediata, pedido para falar com uma pessoa, triagem sem a IA (plano B), conversa da
  IA longa demais (limites em app_config) e qualquer falha da IA.
- Nos outros casos, a cada mensagem do cliente a IA decide (`classifier.atender`) entre resolver e encaminhar.
- O aviso de encaminhamento não conta como 1ª resposta: o prazo (SLA) segue até uma pessoa da equipe responder.
- Se um atendente responde num atendimento da IA, ele assume (`assumir`).
As mensagens da IA são assinadas como AUTOR_IA e não contam como resposta humana na fila.
"""
import logging
import re
import unicodedata
from typing import Optional

from sqlalchemy import text

from . import sla, tickets
from .classifier import LLMError, atender
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

# Risco de perder o cliente (pt, en e es, comparado sem acentos): ameaça de cancelar ou de sair, órgão de defesa do
# consumidor ou processo, e exigência de solução imediata. A IA não negocia isso: passa na hora para uma pessoa.
AMEACA_SAIR = re.compile(
    r"\b(cancel\w*|vou (sair|embora|trocar)|trocar de (empresa|operadora|banco|fornecedor)|procon|reclame ?aqui|"
    r"consumidor\.gov|advogad\w*|process(ar|o judicial)|justica|chargeback|lawyer|sue you|switch to another|"
    r"abogad\w*|demandar)\b",
    re.IGNORECASE,
)
EXIGE_AGORA = re.compile(
    r"\b(imediatamente|agora mesmo|urgente|urgencia|(consert|resolv|arrum|corrig)\w* (isso |isto |o problema )?"
    r"(agora|ja|hoje)|immediately|right now|asap|inmediatamente|ahora mismo)\b",
    re.IGNORECASE,
)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")


def risco_de_perder_cliente(texto: str) -> Optional[str]:
    """Motivo para uma pessoa assumir já (ou None): ameaça de cancelar/sair ou exigência de solução imediata."""
    t = _sem_acento(texto)
    if AMEACA_SAIR.search(t):
        return "o cliente ameaçou cancelar ou sair"
    if EXIGE_AGORA.search(t):
        return "o cliente exigiu solução imediata"
    return None


# Aviso ao cliente quando a IA encaminha: diz para qual equipe o caso foi (pt, en e es; outros idiomas, em inglês).
EQUIPE_NOME = {
    "financeiro": ("nossa equipe financeira", "our billing team", "nuestro equipo financiero"),
    "suporte_tecnico": ("nosso suporte técnico", "our technical support team", "nuestro soporte técnico"),
    "engenharia": ("nossa equipe técnica", "our engineering team", "nuestro equipo técnico"),
    "retencao": ("nossa equipe de relacionamento", "our customer relations team", "nuestro equipo de relación con clientes"),
    "atendimento": ("nossa equipe de atendimento", "our customer service team", "nuestro equipo de atención"),
}
AVISO_ENCAMINHADO = {
    "pt": "Entendi. Encaminhei o seu caso{prioridade} para {equipe}, que já está com esta conversa e continua com você "
          "por aqui em instantes.",
    "en": "Got it. I've forwarded your case{prioridade} to {equipe}, who already have this conversation and will "
          "continue with you here shortly.",
    "es": "Entendido. Remití tu caso{prioridade} a {equipe}, que ya tiene esta conversación y seguirá contigo por aquí "
          "en unos instantes.",
}
PRIORIDADE = {"pt": " com prioridade", "en": " as a priority", "es": " con prioridad"}
IDIOMAS_AVISO = ("pt", "en", "es")


def aviso_encaminhado(equipe: Optional[str], idioma: Optional[str], urgente: bool = False) -> str:
    lingua = idioma if idioma in IDIOMAS_AVISO else ("en" if idioma else "pt")
    nomes = EQUIPE_NOME.get(equipe or "atendimento", EQUIPE_NOME["atendimento"])
    return AVISO_ENCAMINHADO[lingua].format(equipe=nomes[IDIOMAS_AVISO.index(lingua)],
                                           prioridade=PRIORIDADE[lingua] if urgente else "")


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


def _motivo_inicial(t: dict) -> Optional[str]:
    """Casos que vão direto para a equipe, sem perguntar ao modelo (ou None)."""
    if t.get("origem") != "llm":
        return "triagem sem a IA (plano B)"
    if t.get("urgencia") not in URGENCIAS_IA:
        return f"urgência {t.get('urgencia') or 'indefinida'}"
    if t.get("assunto") == "cancelamento":
        return "pedido de cancelamento"
    return risco_de_perder_cliente(t["texto"]) or (
        "o cliente pediu para falar com uma pessoa" if PEDE_PESSOA.search(t["texto"] or "") else None)


def _atender(ticket_id: int, t: dict, conversa: list[tuple[str, str]], idioma: Optional[str]) -> str:
    """A IA decide: resolve (responde ao cliente) ou encaminha para a equipe. Retorna respondida | encaminhada."""
    triagem = {k: t.get(k) for k in ("assunto", "urgencia", "sentimento", "equipe", "idioma")}
    for tentativa in (1, 2):  # uma segunda chance (resposta em outro idioma, JSON quebrado) antes de encaminhar
        try:
            acao, resposta, equipe = atender(conversa, triagem)
            break
        except LLMError as exc:
            if tentativa == 2:
                encaminhar(ticket_id, f"a IA não conseguiu responder ({exc})", t, idioma)
                return "encaminhada"
            logger.info("ticket %s: a IA tenta de novo (%s)", ticket_id, exc)
    if acao == "encaminhar":
        if equipe and equipe != t.get("equipe"):
            t = _redirecionar(ticket_id, t, equipe)
        encaminhar(ticket_id, "a IA avaliou que o caso precisa da equipe", t, idioma)
        return "encaminhada"
    tickets.responder_chat(ticket_id, resposta, AUTOR_IA)
    _definir_modo(ticket_id, "ia")
    return "respondida"


def _redirecionar(ticket_id: int, t: dict, equipe: str) -> dict:
    """O problema mudou na conversa (ex.: dúvida de boleto virou erro 500): a IA troca a equipe da triagem."""
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE classifications SET equipe = :e WHERE ticket_id = :t"), {"e": equipe, "t": ticket_id})
    logger.info("ticket %s: a IA trocou a equipe de %s para %s", ticket_id, t.get("equipe"), equipe)
    return {**t, "equipe": equipe}


def iniciar(ticket_id: int) -> str:
    """Logo depois da triagem: a IA resolve ou encaminha. Retorna ia | humano | ignorado. Nunca levanta exceção."""
    try:
        t = tickets.obter(ticket_id)
        if t.get("desfecho") or t.get("modo") or t["status"] == "pendente":
            return "ignorado"
        if not _config().get("ia_auto_ativo"):
            _definir_modo(ticket_id, "humano")  # atendimento automático desligado: tudo vai para as pessoas
            return "humano"
        motivo = _motivo_inicial(t)
        if motivo:
            encaminhar(ticket_id, motivo, t, t.get("idioma"))
            return "humano"
        resultado = _atender(ticket_id, t, _conversa(ticket_id), t.get("idioma"))
        logger.info("ticket %s: urgência %s, a IA %s", ticket_id, t.get("urgencia"), resultado)
        return "ia" if resultado == "respondida" else "humano"
    except Exception:
        logger.exception("erro ao iniciar o atendimento do ticket %s", ticket_id)
        try:
            encaminhar(ticket_id, "erro no atendimento da IA")
        except Exception:
            pass
        return "humano"


def motivo_para_atendente(t: dict, conversa: list[tuple[str, str]], cfg: dict, agora=None) -> Optional[str]:
    """Por que a IA deve passar a conversa para uma pessoa (ou None, se ela continua)."""
    agora = agora or utcnow()
    ultima = next((texto for papel, texto in reversed(conversa) if papel == "cliente"), "")
    if PEDE_PESSOA.search(ultima or ""):
        return "o cliente pediu para falar com uma pessoa"
    risco = risco_de_perder_cliente(ultima)
    if risco:
        return risco
    minutos = (agora - t["received_at"]).total_seconds() / 60
    if minutos >= cfg.get("ia_max_minutos", 15):
        return f"atendimento da IA passou de {int(cfg.get('ia_max_minutos', 15))} min"
    respostas_ia = sum(1 for m in tickets.mensagens(t["ticket_id"]) if m["direcao"] == "saida" and m["autor"] == AUTOR_IA)
    if respostas_ia >= cfg.get("ia_max_respostas", 5):
        return f"a IA já respondeu {respostas_ia} vezes sem resolver"
    return None


def encaminhar(ticket_id: int, motivo: str, t: Optional[dict] = None, idioma: Optional[str] = None) -> None:
    """Passa a conversa para a equipe da triagem: avisa o cliente para quem foi e põe o atendimento na fila dela."""
    try:
        t = t or tickets.obter(ticket_id)
        urgente = t.get("urgencia") in ("alta", "critica")
        aviso = aviso_encaminhado(t.get("equipe"), idioma or t.get("idioma"), urgente)
        tickets.responder_chat(ticket_id, aviso, AUTOR_IA, conta_resposta=False)
    except Exception:
        logger.exception("não consegui avisar o cliente do ticket %s sobre o encaminhamento", ticket_id)
    _definir_modo(ticket_id, "humano", motivo, escalado=True)
    logger.info("ticket %s encaminhado para a equipe: %s", ticket_id, motivo)


escalar = encaminhar  # nome antigo (ADR-019)


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
            encaminhar(ticket_id, motivo, t, idioma)
            return "escalada"
        return "respondida" if _atender(ticket_id, t, conversa, idioma) == "respondida" else "escalada"
    except Exception:
        logger.exception("erro no atendimento da IA do ticket %s", ticket_id)
        try:
            encaminhar(ticket_id, "erro no atendimento da IA")
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


def apos_correcao(ticket_id: int, correcoes: dict) -> bool:
    """Roteamento depois da correção do atendente: urgência corrigida para alta/crítica tira a conversa da IA.

    Retorna True se a conversa foi passada para um atendente. Nunca levanta exceção.
    """
    nova = correcoes.get("urgencia")
    if not nova or nova in URGENCIAS_IA:
        return False
    try:
        t = tickets.obter(ticket_id)
        if t.get("desfecho") or t.get("modo") != "ia":
            return False
        encaminhar(ticket_id, f"urgência corrigida para {nova} pelo atendente", t, t.get("idioma"))
        return True
    except Exception:
        logger.exception("erro ao rotear o ticket %s depois da correção", ticket_id)
        return False
