"""Teste de fumaça do painel: renderiza sem exceções com e sem dados."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import CHAVE

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


def test_painel_renderiza_vazio(db):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception


def test_painel_renderiza_com_tickets_e_correcoes(client):
    for texto in ("Meu Pix não funciona, estou perdendo vendas!", "Como altero o e-mail do cadastro?"):
        client.post("/webhook/mensagens", json={"canal": "chat", "texto": texto}, headers=CHAVE)
    client.post("/tickets/1/correcoes", json={"urgencia": "alta"}, headers=CHAVE)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Tickets" in m.label for m in at.metric)


def test_painel_exige_senha_quando_configurada(db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "senha-do-painel-123")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.text_input) == 1 and not at.metric  # só o formulário de login, sem dados


def test_painel_libera_com_senha_correta_e_bloqueia_a_errada(db, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "senha-do-painel-123")
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].input("errada")
    at.button[0].click().run()
    assert any("incorreta" in e.value for e in at.error) and not at.metric

    at.text_input[0].input("senha-do-painel-123")
    at.button[0].click().run()
    at.run()  # o st.rerun() do login dispara uma nova execução
    assert at.metric  # painel carregado


def test_painel_bloqueado_em_producao_sem_senha(db, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("bloqueado" in e.value for e in at.error) and not at.metric
