"""Processamento em background de um ticket: classificar, agrupar e (se couber) abrir incidente (ADR-009)."""
import logging

from sqlalchemy import text

from . import exemplos, incidents, midias
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
    return "classificado"


def recuperar_pendentes() -> int:
    """Reprocessa tickets que ficaram 'pendente' (ex.: a API reiniciou no meio do processamento)."""
    with get_engine().connect() as conn:
        ids = [r.id for r in conn.execute(text("SELECT id FROM tickets WHERE status = 'pendente' ORDER BY id"))]
    for i in ids:
        processar_ticket(i)
    return len(ids)
