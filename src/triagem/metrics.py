"""Métricas do painel (Spec 4): motivos de contato, SLA/SLI e resumo."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from . import corrections, incidents, sla
from .db import get_engine, utcnow


def motivos_contato() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT assunto, COUNT(*) AS total FROM vw_tickets WHERE assunto IS NOT NULL "
                "GROUP BY assunto ORDER BY total DESC, assunto"
            )
        ).fetchall()
    return [{"assunto": r.assunto, "total": int(r.total)} for r in rows]


def sli_slo(agora: Optional[datetime] = None) -> dict:
    """SLI de cumprimento do prazo na janela móvel do SLO (docs/slo.md)."""
    agora = agora or utcnow()
    with get_engine().connect() as conn:
        cfg = sla.carregar_config(conn)
        prazos = sla.carregar_prazos(conn)
        ini = agora - timedelta(days=cfg["slo_janela_dias"])
        rows = conn.execute(
            text(
                "SELECT received_at, urgencia, first_response_at FROM vw_tickets "
                "WHERE received_at >= :ini AND urgencia IS NOT NULL"
            ),
            {"ini": ini},
        ).fetchall()
    desfechos = [
        sla.avaliar(r.received_at, r.urgencia, prazos, r.first_response_at, agora, cfg["sla_risco_pct"]).cumpriu
        for r in rows
    ]
    resultado = sla.calcular_sli(desfechos, cfg["slo_alvo_pct"])
    resultado["janela_dias"] = int(cfg["slo_janela_dias"])
    return resultado


def prazos_em_risco(agora: Optional[datetime] = None) -> list[dict]:
    """Tickets sem resposta cujo prazo está em risco ou estourado, os mais críticos primeiro."""
    from . import tickets

    abertos = tickets.listar(limite=1000, apenas_abertos=True, agora=agora)
    criticos = [t for t in abertos if t["sla"]["estado"] in ("em_risco", "estourado")]
    return sorted(criticos, key=lambda t: -(t["sla"]["consumido_pct"] or 0))


def resumo(agora: Optional[datetime] = None) -> dict:
    risco = prazos_em_risco(agora)
    return {
        "motivos_contato": motivos_contato(),
        "prazos_em_risco": [
            {"ticket_id": t["ticket_id"], "urgencia": t["urgencia"], "estado": t["sla"]["estado"],
             "consumido_pct": t["sla"]["consumido_pct"]}
            for t in risco
        ],
        "sli": sli_slo(agora),
        "precisao": corrections.precisao(),
        "precisao_llm": corrections.precisao("llm"),
        "precisao_fallback": corrections.precisao("fallback"),
        "precisao_por_versao": corrections.precisao_por_versao(),
        "incidentes": len(incidents.listar_incidentes(apenas_incidentes=True)),
    }
