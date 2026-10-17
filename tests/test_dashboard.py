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
