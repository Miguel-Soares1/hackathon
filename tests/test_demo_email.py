"""Tela de demonstração do canal e-mail (/demo/email)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from triagem.demo_email import email_demo_para_mensagem

EMAIL = {"de_email": "mariana@exemplo.com", "de_nome": "Mariana Souza", "assunto": "Cobrança duplicada",
         "corpo": "Fui cobrada duas vezes na fatura deste mês. Quero o estorno."}


def test_email_demo_passa_pelo_mesmo_conversor_do_imap():
    # Act
    m = email_demo_para_mensagem("Mariana@Exemplo.com", "Mariana", "atendimento@x.com", "Assunto", "Corpo da mensagem")
    # Assert
    assert m["cliente"] == "mariana@exemplo.com"
    assert m["texto"] == "Assunto\n\nCorpo da mensagem"
    assert m["external_id"].endswith("@demo.local>")


def test_pagina_demo_disponivel_em_desenvolvimento(client):
    r = client.get("/demo/email")
    assert r.status_code == 200 and "Receber e-mail de cliente" in r.text
    assert "connect-src 'self'" in r.headers["content-security-policy"]


def test_envio_demo_cria_ticket_do_canal_email(client, db):
    # Act
    r = client.post("/demo/email", json=EMAIL)
    # Assert
    assert r.status_code == 202
    with db.connect() as conn:
        canal, status = conn.execute(text("SELECT canal, status FROM tickets WHERE id = :i"), {"i": r.json()["ticket_id"]}).one()
    assert canal == "email" and status == "classificado"  # o TestClient roda a tarefa em background antes de devolver


def test_rota_antiga_de_ticket_da_demo_nao_existe(client):
    r = client.post("/demo/email", json=EMAIL)
    assert client.get(f"/demo/email/tickets/{r.json()['ticket_id']}").status_code == 404


def test_conversa_por_email_com_cliente_simulado(client, db):
    # Arrange: sem chave do LLM, o cliente segue o roteiro da situação
    inicio = client.post("/demo/email/conversas", json={"cenario": "nota_fiscal"}).json()
    # Act
    seguinte = client.post(f"/demo/conversas/{inicio['conversa']}/respostas",
                           json={"texto": "Claro! Envio hoje. Pode ser neste e-mail?"}).json()["mensagem"]
    # Assert
    assert inicio["mensagem"]["assunto"] == "Nota fiscal"
    assert seguinte["texto"] and seguinte["ticket_id"] is None  # o fio continua no mesmo ticket
    with db.connect() as conn:
        canal, texto, respondido = conn.execute(text("SELECT canal, texto, first_response_at FROM tickets WHERE id = :i"),
                                                {"i": inicio["mensagem"]["ticket_id"]}).one()
    assert canal == "email" and texto.startswith("Nota fiscal") and respondido is not None


def test_envio_demo_respeita_filtro_de_remetente_automatico(client):
    r = client.post("/demo/email", json={**EMAIL, "de_email": "no-reply@exemplo.com"})
    assert r.status_code == 400


def test_envio_demo_valida_remetente(client):
    assert client.post("/demo/email", json={**EMAIL, "de_email": "sem-arroba"}).status_code == 400


def test_demo_desligada_em_producao(db, monkeypatch):
    # Arrange
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_KEY", "x" * 32)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "senha-forte-123")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://u:p@127.0.0.1:3306/hackathon_test")
    from triagem.api import create_app
    # Act
    c = TestClient(create_app())
    # Assert
    assert c.get("/demo/email").status_code == 404
    assert c.post("/demo/email", json=EMAIL).status_code in (404, 405)


def test_demo_pode_ser_desligada_por_variavel(db, monkeypatch):
    monkeypatch.delenv("DEMO", raising=False)  # DEMO, se existir no .env, tem prioridade sobre DEMO_EMAIL
    monkeypatch.setenv("DEMO_EMAIL", "0")
    from triagem.api import create_app
    assert TestClient(create_app()).get("/demo/email").status_code == 404
