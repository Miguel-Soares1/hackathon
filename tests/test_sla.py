from datetime import datetime, timedelta

from triagem import sla

PRAZOS = {"critica": 15, "alta": 60, "media": 240, "baixa": 1440}
T0 = datetime(2026, 10, 17, 12, 0, 0)


def estado(urgencia, minutos, resposta_em=None):
    resp = T0 + timedelta(minutes=resposta_em) if resposta_em is not None else None
    return sla.avaliar(T0, urgencia, PRAZOS, resp, T0 + timedelta(minutes=minutos))


def test_ticket_dentro_do_prazo_fica_no_prazo():
    # Arrange / Act
    r = estado("alta", 30)
    # Assert
    assert r.estado == "no_prazo" and r.cumpriu is None


def test_ticket_com_75_por_cento_do_prazo_consumido_esta_em_risco():
    r = estado("alta", 45)  # 45/60 = 75%
    assert r.estado == "em_risco"


def test_ticket_logo_abaixo_de_75_por_cento_nao_esta_em_risco():
    assert estado("alta", 44).estado == "no_prazo"


def test_ticket_com_prazo_vencido_esta_estourado_e_nao_cumpriu():
    r = estado("critica", 15)
    assert r.estado == "estourado" and r.cumpriu is False


def test_resposta_dentro_do_prazo_cumpre_o_sla():
    r = estado("alta", 500, resposta_em=59)
    assert r.estado == "respondido" and r.cumpriu is True


def test_resposta_depois_do_prazo_viola_o_sla():
    r = estado("alta", 500, resposta_em=61)
    assert r.estado == "respondido" and r.cumpriu is False


def test_ticket_sem_urgencia_aguarda_classificacao():
    r = sla.avaliar(T0, None, PRAZOS, None, T0)
    assert r.estado == "aguardando_classificacao" and r.prazo_minutos is None


def test_risco_pct_configuravel():
    r = sla.avaliar(T0, "alta", PRAZOS, None, T0 + timedelta(minutes=36), risco_pct=50)
    assert r.estado == "em_risco"


def test_sli_e_orcamento_de_erro():
    # 20 tickets decididos, 1 violação, alvo 95% -> orçamento de 1 violação -> 100% consumido
    r = sla.calcular_sli([True] * 19 + [False], 95.0)
    assert r["sli_pct"] == 95.0
    assert r["orcamento"] == 1.0
    assert r["consumo_orcamento_pct"] == 100.0
    assert r["politica"] == "congelar_funcionalidades"


def test_sli_ignora_tickets_ainda_no_prazo():
    r = sla.calcular_sli([True, None, None, False], 95.0)
    assert r["total"] == 2


def test_sli_sem_dados():
    assert sla.calcular_sli([None, None], 95.0)["sli_pct"] is None


def test_politica_de_error_budget_por_faixa():
    assert sla.politica(10) == "normal"
    assert sla.politica(50) == "alerta"
    assert sla.politica(99.9) == "alerta"
    assert sla.politica(100) == "congelar_funcionalidades"
