"""Política de SLA (Spec 5, ADR-007): prazo por urgência, estado do ticket e SLI/SLO."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

CONFIG_PADRAO = {
    "sla_risco_pct": 75.0,
    "similarity_threshold": 0.60,
    "window_minutes": 30.0,
    "min_group_size": 3.0,
    "slo_alvo_pct": 95.0,
    "slo_janela_dias": 7.0,
    "ia_auto_ativo": 1.0,      # 1 = a IA atende sozinha as urgências baixa e média (ADR-019)
    "ia_max_minutos": 15.0,    # passou disso desde a 1ª mensagem: vai para um atendente
    "ia_max_respostas": 5.0,   # a IA já respondeu tantas vezes: vai para um atendente
    "encerrar_inativo_min": 10.0,  # cliente sem responder por tanto tempo: atendimento encerrado (0 desliga)
}


def carregar_config(conn: Connection) -> dict[str, float]:
    cfg = dict(CONFIG_PADRAO)
    for chave, valor in conn.execute(text("SELECT chave, valor FROM app_config")):
        if chave in cfg:
            cfg[chave] = float(valor)
    return cfg


def carregar_prazos(conn: Connection) -> dict[str, int]:
    rows = conn.execute(text("SELECT urgencia, prazo_minutos FROM sla_policy"))
    return {urgencia: int(prazo) for urgencia, prazo in rows}


@dataclass(frozen=True)
class EstadoSLA:
    estado: str  # aguardando_classificacao | no_prazo | em_risco | estourado | respondido
    prazo_minutos: Optional[int]
    vence_em: Optional[datetime]
    consumido_pct: Optional[float]
    cumpriu: Optional[bool]  # True/False quando o desfecho já é conhecido; None se ainda em aberto no prazo


def avaliar(
    received_at: datetime,
    urgencia: Optional[str],
    prazos: dict[str, int],
    first_response_at: Optional[datetime],
    agora: datetime,
    risco_pct: float = 75.0,
) -> EstadoSLA:
    if urgencia is None or urgencia not in prazos:
        return EstadoSLA("aguardando_classificacao", None, None, None, None)
    prazo = prazos[urgencia]
    vence = received_at + timedelta(minutes=prazo)
    if first_response_at is not None:
        gasto = (first_response_at - received_at).total_seconds() / 60.0
        return EstadoSLA("respondido", prazo, vence, round(gasto / prazo * 100, 1), first_response_at <= vence)
    consumido = (agora - received_at).total_seconds() / 60.0 / prazo * 100.0
    if consumido >= 100.0:
        return EstadoSLA("estourado", prazo, vence, round(consumido, 1), False)
    if consumido >= risco_pct:
        return EstadoSLA("em_risco", prazo, vence, round(consumido, 1), None)
    return EstadoSLA("no_prazo", prazo, vence, round(max(consumido, 0.0), 1), None)


def calcular_sli(cumpriu: list[Optional[bool]], alvo_pct: float) -> dict:
    """SLI = % de tickets com desfecho 'cumpriu'. Tickets ainda no prazo (None) não entram."""
    decididos = [c for c in cumpriu if c is not None]
    total = len(decididos)
    if total == 0:
        return {"total": 0, "violacoes": 0, "sli_pct": None, "alvo_pct": alvo_pct,
                "orcamento": 0.0, "consumo_orcamento_pct": None, "politica": "sem_dados"}
    violacoes = sum(1 for c in decididos if c is False)
    sli = (total - violacoes) / total * 100.0
    orcamento = total * (100.0 - alvo_pct) / 100.0
    if orcamento > 0:
        consumo = violacoes / orcamento * 100.0
    else:
        consumo = 0.0 if violacoes == 0 else 999.0
    return {
        "total": total,
        "violacoes": violacoes,
        "sli_pct": round(sli, 1),
        "alvo_pct": alvo_pct,
        "orcamento": round(orcamento, 2),
        "consumo_orcamento_pct": round(consumo, 1),
        "politica": politica(consumo),
    }


def politica(consumo_pct: float) -> str:
    """Política de error budget (docs/slo.md)."""
    if consumo_pct >= 100.0:
        return "congelar_funcionalidades"
    if consumo_pct >= 50.0:
        return "alerta"
    return "normal"
