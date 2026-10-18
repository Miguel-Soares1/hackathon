"""Métricas do painel (Spec 4): motivos de contato, SLA/SLI e resumo."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from . import corrections, incidents, sla
from .db import get_engine, utcnow


# Horário de Brasília (sem horário de verão desde 2019): "hoje" é o dia do painel, não o dia em UTC.
BRT = timezone(timedelta(hours=-3))
# Reprocessamentos (a API reiniciou com tickets pendentes) não entram na média do tempo de triagem.
TEMPO_TRIAGEM_MAX_S = 3600


def inicio_do_dia(agora: Optional[datetime] = None) -> datetime:
    """Meia-noite de hoje em Brasília, em UTC sem fuso (como as datas do banco)."""
    agora = agora or utcnow()
    local = agora.replace(tzinfo=timezone.utc).astimezone(BRT)
    meia_noite = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return meia_noite.astimezone(timezone.utc).replace(tzinfo=None)


def triagem_hoje(agora: Optional[datetime] = None) -> dict:
    """Quantas mensagens a triagem automática classificou hoje e quanto tempo levou cada uma.

    O tempo vai da gravação do ticket (created_at) até a classificação: received_at pode ser a hora original
    de uma mensagem importada ou simulada.
    """
    with get_engine().connect() as conn:
        r = conn.execute(
            text(
                "SELECT COUNT(*) AS total, COALESCE(SUM(cl.origem = 'llm'), 0) AS ia, "
                "AVG(CASE WHEN TIMESTAMPDIFF(SECOND, t.created_at, cl.classified_at) BETWEEN 0 AND :max "
                "THEN TIMESTAMPDIFF(SECOND, t.created_at, cl.classified_at) END) AS tempo "
                "FROM classifications cl JOIN tickets t ON t.id = cl.ticket_id WHERE cl.classified_at >= :ini"
            ),
            {"ini": inicio_do_dia(agora), "max": TEMPO_TRIAGEM_MAX_S},
        ).fetchone()
    total, ia = int(r.total), int(r.ia)
    return {
        "triadas_hoje": total,
        "triadas_ia_hoje": ia,
        "plano_b_hoje": total - ia,
        "tempo_medio_s": None if r.tempo is None else round(float(r.tempo), 1),
    }


def motivos_contato() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT assunto, COUNT(*) AS total FROM vw_tickets WHERE assunto IS NOT NULL "
                "GROUP BY assunto ORDER BY total DESC, assunto"
            )
        ).fetchall()
    return [{"assunto": r.assunto, "total": int(r.total)} for r in rows]


def idiomas() -> list[dict]:
    """Quantos tickets chegaram em cada idioma (ADR-015)."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT idioma, COUNT(*) AS total FROM vw_tickets WHERE idioma IS NOT NULL "
                "GROUP BY idioma ORDER BY total DESC, idioma"
            )
        ).fetchall()
    return [{"idioma": r.idioma, "total": int(r.total)} for r in rows]


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
        "idiomas": idiomas(),
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
        "triagem": triagem_hoje(agora),
    }
