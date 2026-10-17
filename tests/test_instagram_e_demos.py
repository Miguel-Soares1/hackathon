"""Canal Instagram (webhook da Meta) e telas de demonstração de WhatsApp/Instagram."""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from triagem import canais, demo_chat

SEGREDO = "segredo-do-app"
TOKEN = "token-ig"


def _assinar(corpo: bytes, segredo=SEGREDO) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest(),
            "Content-Type": "application/json"}


def _evento(mid="m_1", texto="Meu pix não caiu, preciso hoje", de="1784", eco=False, ts=1760000000000):
    msg = {"mid": mid, "text": texto}
    if eco:
        msg["is_echo"] = True
    return {"sender": {"id": de}, "recipient": {"id": "999"}, "timestamp": ts, "message": msg}


def _payload(*eventos):
    return {"object": "instagram", "entry": [{"id": "999", "time": 1, "messaging": list(eventos)}]}


def _app(monkeypatch, **env):
    for k, v in {"INSTAGRAM_APP_SECRET": SEGREDO, "INSTAGRAM_VERIFY_TOKEN": TOKEN, **env}.items():
        monkeypatch.setenv(k, v)
    from triagem.api import create_app
    return TestClient(create_app())


# ---------- Instagram: função pura ----------
def test_mensagens_instagram_extrai_texto_e_ignora_eco_reacao_e_anexo():
    # Arrange
    payload = _payload(
        _evento(),
        _evento(mid="m_2", eco=True),                                          # a própria empresa respondendo
        {"sender": {"id": "1784"}, "timestamp": 1, "reaction": {"emoji": "❤"}},  # reação
        {"sender": {"id": "1784"}, "timestamp": 1, "message": {"mid": "m_3", "attachments": [{"type": "image"}]}},
    )
    # Act
    msgs = canais.mensagens_instagram(payload)
    # Assert
    assert len(msgs) == 1
    assert msgs[0]["cliente"] == "instagram:1784" and msgs[0]["external_id"] == "m_1"
    assert msgs[0]["received_at"].year == 2025


def test_mensagens_instagram_tolera_payload_malformado():
    assert canais.mensagens_instagram({"object": "page"}) == []
    assert canais.mensagens_instagram({"entry": "x"}) == []
    assert canais.mensagens_instagram([]) == []


# ---------- Instagram: webhook ----------
def test_instagram_verificacao(db, monkeypatch):
    c = _app(monkeypatch)
    ok = c.get("/webhooks/instagram", params={"hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "42"})
    ruim = c.get("/webhooks/instagram", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert ruim.status_code == 403


def test_instagram_post_assinado_cria_ticket_classificado_e_nao_duplica(db, monkeypatch):
    # Arrange
    c = _app(monkeypatch)
    corpo = json.dumps(_payload(_evento())).encode()
    # Act
    r1 = c.post("/webhooks/instagram", content=corpo, headers=_assinar(corpo))
    r2 = c.post("/webhooks/instagram", content=corpo, headers=_assinar(corpo))
    # Assert
    assert r1.json() == {"recebidas": 1} and r2.json() == {"recebidas": 0}
    with db.connect() as conn:
        canal, status = conn.execute(text("SELECT canal, status FROM tickets")).one()
    assert canal == "instagram" and status == "classificado"


def test_instagram_assinatura_invalida_ou_sem_segredo(db, monkeypatch):
    corpo = json.dumps(_payload(_evento())).encode()
    c = _app(monkeypatch)
    assert c.post("/webhooks/instagram", content=corpo, headers=_assinar(corpo, "outro")).status_code == 403
    c2 = _app(monkeypatch, INSTAGRAM_APP_SECRET="", WHATSAPP_APP_SECRET="")
    assert c2.post("/webhooks/instagram", content=corpo, headers=_assinar(corpo)).status_code == 503


def test_instagram_usa_segredo_do_whatsapp_quando_nao_tem_o_proprio(db, monkeypatch):
    c = _app(monkeypatch, INSTAGRAM_APP_SECRET="", WHATSAPP_APP_SECRET=SEGREDO)
    corpo = json.dumps(_payload(_evento())).encode()
    assert c.post("/webhooks/instagram", content=corpo, headers=_assinar(corpo)).json() == {"recebidas": 1}


# ---------- Demonstrações ----------
def test_payloads_de_demo_passam_pelos_conversores_reais():
    wa = demo_chat.mensagem_demo("whatsapp", "5511987654321", "Mariana", "meu pix não caiu")
    ig = demo_chat.mensagem_demo("instagram", "mari.souza", None, "meu pix não caiu")
    assert wa["cliente"] == "Mariana (5511987654321)" and wa["external_id"].startswith("wamid.DEMO")
    assert ig["cliente"] == "instagram:mari.souza" and ig["external_id"].startswith("m_DEMO")


def test_telas_de_demo_disponiveis(client):
    for canal in ("whatsapp", "instagram", "email"):
        r = client.get(f"/demo/{canal}")
        assert r.status_code == 200, canal
    assert client.get("/demo/telegram").status_code == 404


def test_demo_whatsapp_e_instagram_criam_ticket_do_canal(client, db):
    for canal, remetente in (("whatsapp", "5511987654321"), ("instagram", "mari.souza")):
        r = client.post(f"/demo/{canal}", json={"remetente": remetente, "nome": "Mariana", "texto": "não consigo entrar na conta"})
        assert r.status_code == 202
        with db.connect() as conn:
            c, status = conn.execute(text("SELECT canal, status FROM tickets WHERE id = :i"), {"i": r.json()["ticket_id"]}).one()
        assert c == canal and status == "classificado"


def test_telas_de_conversa_nao_mostram_a_triagem_ao_cliente(client):
    for canal in ("whatsapp", "instagram"):
        html = client.get(f"/demo/{canal}").text.lower()
        assert "triagem" not in html and "urgência" not in html and "/demo/tickets" not in html
    r = client.post("/demo/whatsapp", json={"remetente": "5511987654321", "texto": "não consigo entrar na conta"})
    assert client.get(f"/demo/tickets/{r.json()['ticket_id']}").status_code == 404


def test_demo_valida_remetente_por_canal(client):
    assert client.post("/demo/whatsapp", json={"remetente": "abc", "texto": "olá, tudo bem?"}).status_code == 400
    assert client.post("/demo/instagram", json={"remetente": "Nome Com Espaço", "texto": "olá, tudo bem?"}).status_code == 400
    assert client.post("/demo/whatsapp", json={"remetente": "5511987654321", "texto": "oi"}).status_code == 400


def test_demos_desligadas_em_producao(db, monkeypatch):
    c = _app(monkeypatch, ENVIRONMENT="production", API_KEY="x" * 32, DASHBOARD_PASSWORD="senha-forte-123",
             DATABASE_URL="mysql+pymysql://u:p@127.0.0.1:3306/hackathon_test")
    for canal in ("whatsapp", "instagram", "email"):
        assert c.get(f"/demo/{canal}").status_code == 404
