"""Processamento em background de um ticket: classificar, agrupar e (se couber) abrir incidente (ADR-009)."""
import logging
from typing import Optional

from sqlalchemy import text

from . import atendimento_ia, exemplos, incidents, midias, tickets
from .classifier import LLMError, classificar, sugerir_resposta
from .db import com_retry_deadlock, get_engine, utcnow

logger = logging.getLogger(__name__)


@com_retry_deadlock()
def _salvar_classificacao(ticket_id: int, c) -> None:
    """Primeiro atualiza o ticket (trava exclusiva) e só depois insere a classificação (FK).
    Essa ordem evita deadlock com outras transações que atualizam o mesmo ticket."""
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE tickets SET status = 'classificado' WHERE id = :id"), {"id": ticket_id})
        conn.execute(
            text(
                "INSERT INTO classifications (ticket_id, assunto, urgencia, sentimento, equipe, "
                "resposta_sugerida, idioma, conf_assunto, conf_urgencia, conf_sentimento, conf_equipe, origem, prompt_version, "
                "exemplos, classified_at) "
                "VALUES (:id, :a, :u, :s, :e, :r, :i, :ca, :cu, :cs, :ce, :o, :pv, :ex, :q) "
                "ON DUPLICATE KEY UPDATE assunto = VALUES(assunto), urgencia = VALUES(urgencia), "
                "sentimento = VALUES(sentimento), equipe = VALUES(equipe), "
                "resposta_sugerida = VALUES(resposta_sugerida), idioma = VALUES(idioma), conf_assunto = VALUES(conf_assunto), "
                "conf_urgencia = VALUES(conf_urgencia), conf_sentimento = VALUES(conf_sentimento), "
                "conf_equipe = VALUES(conf_equipe), origem = VALUES(origem), prompt_version = VALUES(prompt_version), "
                "exemplos = VALUES(exemplos), classified_at = VALUES(classified_at)"
            ),
            {
                "id": ticket_id, "a": c.assunto, "u": c.urgencia, "s": c.sentimento, "e": c.equipe,
                "r": c.resposta_sugerida, "i": c.idioma or "pt", "ca": c.confianca["assunto"], "cu": c.confianca["urgencia"],
                "cs": c.confianca["sentimento"], "ce": c.confianca["equipe"], "o": c.origem,
                "pv": c.prompt_version, "ex": ",".join(map(str, c.exemplos)) or None, "q": utcnow(),
            },
        )


def processar_ticket(ticket_id: int) -> str:
    """Nunca levanta exceção para quem chamou. Retorna o estado final: classificado | ignorado | erro."""
    try:
        eng = get_engine()
        with eng.connect() as conn:
            t = conn.execute(
                text("SELECT id, texto, status FROM tickets WHERE id = :id"), {"id": ticket_id}
            ).fetchone()
        if t is None or t.status != "pendente":
            return "ignorado"

        # Áudio e foto viram texto antes da triagem (ADR-017).
        texto = midias.processar(ticket_id, t.texto) or t.texto

        # Few-shot dinâmico: tickets revisados parecidos orientam a classificação (ADR-014).
        refs = exemplos.buscar(texto, excluir_ticket=ticket_id)
        c = classificar(texto, exemplos=refs)
        _salvar_classificacao(ticket_id, c)
        logger.info("ticket %s classificado (origem=%s, prompt=%s, idioma=%s, exemplos=%s)",
                    ticket_id, c.origem, c.prompt_version, c.idioma, c.exemplos)
    except Exception:
        logger.exception("erro ao classificar o ticket %s", ticket_id)
        return "erro"

    try:
        incidents.registrar(ticket_id)
    except Exception:
        # Falha no agrupamento não invalida a classificação já salva.
        logger.exception("erro ao agrupar o ticket %s", ticket_id)
    # O cliente pode ter escrito de novo enquanto a 1ª mensagem era classificada: a sugestão já responde à última.
    atualizar_sugestao(ticket_id)
    # Urgência baixa ou média: a IA responde sozinha; alta ou crítica: vai para um atendente (ADR-019).
    atendimento_ia.iniciar(ticket_id)
    return "classificado"


def recuperar_pendentes() -> int:
    """Reprocessa tickets que ficaram 'pendente' (ex.: a API reiniciou no meio do processamento)."""
    with get_engine().connect() as conn:
        ids = [r.id for r in conn.execute(text("SELECT id FROM tickets WHERE status = 'pendente' ORDER BY id"))]
    for i in ids:
        processar_ticket(i)
    return len(ids)


def atualizar_sugestao(ticket_id: int, mensagem_id: Optional[int] = None, forcar: bool = False) -> str:
    """Reescreve a resposta sugerida para a ÚLTIMA mensagem do cliente, com a conversa como contexto.

    A triagem (assunto, urgência, equipe e prazo) continua a da 1ª mensagem (ADR-016); só a sugestão acompanha a
    conversa. Sem LLM, ou se ele falhar, a sugestão anterior fica. Nunca levanta exceção.
    `forcar` (botão do painel): gera de novo mesmo com uma só mensagem do cliente ou se já havia sugestão para ela,
    para considerar também o que o atendente já respondeu.
    Retorna: atualizada | sem_mudanca | ignorado | mantida
    """
    try:
        t = tickets.obter(ticket_id)
        if t["status"] == "pendente" or t.get("desfecho"):
            return "ignorado"  # ainda classificando (processar_ticket chama de novo no fim) ou atendimento encerrado
        msgs = tickets.mensagens(ticket_id)
        entradas = [m for m in msgs if m["direcao"] == "entrada"]
        if not entradas:
            return "sem_mudanca"
        if len(entradas) < 2 and not forcar:
            return "sem_mudanca"  # só a 1ª mensagem: a sugestão da triagem já responde a ela
        ultima = entradas[-1]
        if mensagem_id is not None and ultima["id"] != mensagem_id:
            return "ignorado"  # chegou uma mensagem mais nova; a tarefa dela atualiza
        if t.get("sugestao_mensagem_id") == ultima["id"] and not forcar:
            return "sem_mudanca"
        conversa = [("cliente" if m["direcao"] == "entrada" else "atendente", m["texto"]) for m in msgs if m["texto"]]
        triagem = {k: t.get(k) for k in ("assunto", "urgencia", "sentimento", "equipe")}
        resposta = sugerir_resposta(conversa, triagem)
    except LLMError as exc:
        logger.info("sugestão do ticket %s mantida: %s", ticket_id, exc)
        return "mantida"
    except Exception:
        logger.exception("erro ao atualizar a sugestão do ticket %s", ticket_id)
        return "mantida"
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE tickets SET sugestao_contexto = :r, sugestao_em = :q, sugestao_mensagem_id = :m WHERE id = :id"),
            {"r": resposta, "q": utcnow(), "m": ultima["id"], "id": ticket_id},
        )
    return "atualizada"


def mensagem_anexada(ticket_id: int, mensagem_id: Optional[int], texto: str = "", tem_midia: bool = False) -> None:
    """Background de uma mensagem que entrou numa conversa já aberta: lê a mídia (se houver) e atualiza a sugestão."""
    if tem_midia:
        try:
            midias.processar(ticket_id, texto, mensagem_id)
        except Exception:
            logger.exception("erro ao ler a mídia da mensagem %s do ticket %s", mensagem_id, ticket_id)
    # Atendimento da IA: ela responde (ou passa para um atendente); nos outros, só a sugestão para o atendente muda.
    if atendimento_ia.responder(ticket_id, mensagem_id) in ("respondida", "ignorado"):
        return
    atualizar_sugestao(ticket_id, mensagem_id)
