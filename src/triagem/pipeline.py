"""Processamento em background de um ticket: classificar, agrupar e (se couber) abrir incidente (ADR-009)."""
import logging

from sqlalchemy import text

from . import incidents
from .classifier import classificar
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
                "resposta_sugerida, conf_assunto, conf_urgencia, conf_sentimento, conf_equipe, origem, classified_at) "
                "VALUES (:id, :a, :u, :s, :e, :r, :ca, :cu, :cs, :ce, :o, :q) "
                "ON DUPLICATE KEY UPDATE assunto = VALUES(assunto), urgencia = VALUES(urgencia), "
                "sentimento = VALUES(sentimento), equipe = VALUES(equipe), "
                "resposta_sugerida = VALUES(resposta_sugerida), conf_assunto = VALUES(conf_assunto), "
                "conf_urgencia = VALUES(conf_urgencia), conf_sentimento = VALUES(conf_sentimento), "
                "conf_equipe = VALUES(conf_equipe), origem = VALUES(origem), classified_at = VALUES(classified_at)"
            ),
            {
                "id": ticket_id, "a": c.assunto, "u": c.urgencia, "s": c.sentimento, "e": c.equipe,
                "r": c.resposta_sugerida, "ca": c.confianca["assunto"], "cu": c.confianca["urgencia"],
                "cs": c.confianca["sentimento"], "ce": c.confianca["equipe"], "o": c.origem, "q": utcnow(),
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

        c = classificar(t.texto)
        _salvar_classificacao(ticket_id, c)
        logger.info("ticket %s classificado (origem=%s)", ticket_id, c.origem)
    except Exception:
        logger.exception("erro ao classificar o ticket %s", ticket_id)
        return "erro"

    try:
        incidents.registrar(ticket_id)
    except Exception:
        # Falha no agrupamento não invalida a classificação já salva.
        logger.exception("erro ao agrupar o ticket %s", ticket_id)
    return "classificado"


def recuperar_pendentes() -> int:
    """Reprocessa tickets que ficaram 'pendente' (ex.: a API reiniciou no meio do processamento)."""
    with get_engine().connect() as conn:
        ids = [r.id for r in conn.execute(text("SELECT id FROM tickets WHERE status = 'pendente' ORDER BY id"))]
    for i in ids:
        processar_ticket(i)
    return len(ids)
