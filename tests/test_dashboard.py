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


def _app_atendimento(client):
    client.post("/webhook/mensagens", json={"canal": "whatsapp", "cliente": "Ana", "texto": "Meu Pix não funciona, estou perdendo vendas!"}, headers=CHAVE)
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.sidebar.button if b.key == "nav_atendimento").click().run()
    return at


def test_navegacao_abre_a_pagina_de_atendimento_com_a_fila(client):
    at = _app_atendimento(client)
    assert not at.exception
    assert at.session_state["pagina"] == "atendimento"
    assert any(b.key and b.key.startswith("abrir_e_") for b in at.button)  # cartão na aba "Em espera"


def test_abrir_atendimento_mostra_o_painel_com_a_resposta_sugerida(client):
    at = _app_atendimento(client)
    next(b for b in at.button if b.key and b.key.startswith("abrir_e_")).click().run()
    assert not at.exception
    assert at.session_state["ticket_sel"] == 1
    assert any(b.label == "✓ Triagem correta" for b in at.button)


def test_texto_do_cliente_e_escapado_nos_cartoes(client):
    client.post("/webhook/mensagens", json={"canal": "chat", "cliente": "<b>X</b>", "texto": "<script>alert(1)</script> preciso de ajuda"}, headers=CHAVE)
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.sidebar.button if b.key == "nav_atendimento").click().run()
    html_cartoes = " ".join(m.value for m in at.markdown if "cartao" in m.value)
    assert "<script>" not in html_cartoes and "&lt;script&gt;" in html_cartoes
    assert "<b>X</b>" not in html_cartoes


def test_atendente_envia_mensagem_no_chat_e_ela_fica_registrada(client):
    at = _app_atendimento(client)
    next(b for b in at.button if b.key and b.key.startswith("abrir_e_")).click().run()
    at.text_area(key="chat_texto_1").input("Olá! Já estamos verificando o seu Pix.")
    next(b for b in at.button if b.label == "Enviar").click().run()
    assert not at.exception
    msgs = client.get("/tickets/1/mensagens", headers=CHAVE).json()
    assert [m["direcao"] for m in msgs] == ["entrada", "saida"]
    assert msgs[1]["texto"] == "Olá! Já estamos verificando o seu Pix." and msgs[1]["autor"] == "Atendente"
    assert client.get("/tickets/1", headers=CHAVE).json()["first_response_at"] is not None


def test_chat_nao_envia_mensagem_vazia(client):
    at = _app_atendimento(client)
    next(b for b in at.button if b.key and b.key.startswith("abrir_e_")).click().run()
    next(b for b in at.button if b.label == "Enviar").click().run()
    assert len(client.get("/tickets/1/mensagens", headers=CHAVE).json()) == 1
    assert any("Escreva uma mensagem" in w.value for w in at.warning)


def test_chat_escapa_html_das_mensagens_do_cliente(client):
    client.post("/webhook/mensagens", json={"canal": "chat", "cliente": "Eve", "texto": "<img src=x onerror=alert(1)> oi pessoal"}, headers=CHAVE)
    at = AppTest.from_file(APP, default_timeout=30).run()
    next(b for b in at.sidebar.button if b.key == "nav_atendimento").click().run()
    next(b for b in at.button if b.key and b.key.startswith("abrir_e_")).click().run()
    bolhas = " ".join(m.value for m in at.markdown if "bolha" in m.value)
    assert "<img" not in bolhas and "&lt;img" in bolhas
