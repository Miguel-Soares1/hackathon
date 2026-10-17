"""Ingestão e consulta de tickets (Specs 1 e 5)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from . import sla
from .db import com_retry_deadlock, get_engine, utcnow


class TicketNaoEncontrado(Exception):
    pass


class RespostaAnteriorAoRecebimento(ValueError):
    pass


def criar_ticket(canal: str, texto: str, cliente: Optional[str] = None, received_at: Optional[datetime] = None) -> int:
    """Persiste o ticket como 'pendente' (ADR-009). A classificação acontece em background."""
    agora = utcnow()
    with get_engine().begin() as conn:
        res = conn.execute(
            text(
                "INSERT INTO tickets (canal, cliente, texto, status, received_at) "
                "VALUES (:canal, :cliente, :texto, 'pendente', :received_at)"
            ),
            {"canal": canal, "cliente": cliente, "texto": texto, "received_at": received_at or agora},
        )
        return int(res.lastrowid)


def _linha_para_dict(row, prazos, risco_pct, agora) -> dict:
    d = dict(row._mapping)
    d["revisado"] = bool(d.get("revisado"))
    est = sla.avaliar(d["received_at"], d.get("urgencia"), prazos, d["first_response_at"], agora, risco_pct)
    d["sla"] = {
        "estado": est.estado,
        "prazo_minutos": est.prazo_minutos,
        "vence_em": est.vence_em,
        "consumido_pct": est.consumido_pct,
        "cumpriu": est.cumpriu,
    }
    return d


def listar(limite: int = 200, apenas_abertos: bool = False, agora: Optional[datetime] = None) -> list[dict]:
    agora = agora or utcnow()
    with get_engine().connect() as conn:
        prazos = sla.carregar_prazos(conn)
        risco = sla.carregar_config(conn)["sla_risco_pct"]
        rows = conn.execute(
            text(
                "SELECT * FROM vw_tickets WHERE (:so_abertos = 0 OR first_response_at IS NULL) "
                "ORDER BY received_at DESC, ticket_id DESC LIMIT :limite"
            ),
            {"limite": limite, "so_abertos": 1 if apenas_abertos else 0},
        ).fetchall()
    return [_linha_para_dict(r, prazos, risco, agora) for r in rows]


def obter(ticket_id: int, agora: Optional[datetime] = None) -> dict:
    agora = agora or utcnow()
    with get_engine().connect() as conn:
        prazos = sla.carregar_prazos(conn)
        risco = sla.carregar_config(conn)["sla_risco_pct"]
        row = conn.execute(text("SELECT * FROM vw_tickets WHERE ticket_id = :id"), {"id": ticket_id}).fetchone()
    if row is None:
        raise TicketNaoEncontrado(ticket_id)
    return _linha_para_dict(row, prazos, risco, agora)


@com_retry_deadlock()
def _registrar_resposta(ticket_id: int, quando: datetime) -> None:
    with get_engine().begin() as conn:
        existe = conn.execute(text("SELECT received_at FROM tickets WHERE id = :id"), {"id": ticket_id}).fetchone()
        if existe is None:
            raise TicketNaoEncontrado(ticket_id)
        if quando < existe.received_at:
            raise RespostaAnteriorAoRecebimento(ticket_id)
        conn.execute(
            text("UPDATE tickets SET first_response_at = :q WHERE id = :id AND first_response_at IS NULL"),
            {"q": quando, "id": ticket_id},
        )


def marcar_respondido(ticket_id: int, quando: Optional[datetime] = None) -> dict:
    """Registra a primeira resposta. Se já houver uma, a original é preservada (idempotente)."""
    _registrar_resposta(ticket_id, quando or utcnow())
    return obter(ticket_id)
