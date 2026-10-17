import hashlib
import hmac
import json
from datetime import datetime, timezone

from sqlalchemy import text

from conftest import CHAVE
from triagem import canais, tickets
from triagem.email_imap import criar_enviador, varrer_caixa

SEGREDO = "segredo-do-app"
TOKEN = "token-de-verificacao"


def _assinar(corpo: bytes, segredo=SEGREDO) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest(),
            "Content-Type": "application/json"}


def _payload(mid="wamid.1", texto="Meu pix não caiu e preciso resolver hoje", de="5521999990000", tipo="text"):
    msg = {"id": mid, "from": de, "timestamp": "1760000000", "type": tipo}
    if tipo == "text":
        msg["text"] = {"body": texto}
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": de, "profile": {"name": "Ana"}}], "messages": [msg]}}]}]}


def _client(client, monkeypatch, segredo=SEGREDO, token=TOKEN):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", segredo)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", token)
    from fastapi.testclient import TestClient
    from triagem.api import create_app
    return TestClient(create_app())


# ---------- WhatsApp: funções puras ----------
def test_assinatura_valida_e_invalida():
    corpo = b'{"a":1}'
    ok = _assinar(corpo)["X-Hub-Signature-256"]
    assert canais.assinatura_valida(corpo, ok, SEGREDO)
    assert not canais.assinatura_valida(corpo + b" ", ok, SEGREDO)
    assert not canais.assinatura_valida(corpo, None, SEGREDO)
    assert not canais.assinatura_valida(corpo, ok, "")  # sem segredo configurado nunca valida


def test_mensagens_whatsapp_extrai_texto_e_ignora_midia_e_status():
    msgs = canais.mensagens_whatsapp(_payload())
    assert len(msgs) == 1 and msgs[0]["external_id"] == "wamid.1"
    assert msgs[0]["cliente"] == "Ana (5521999990000)"
    assert msgs[0]["received_at"] == datetime.fromtimestamp(1760000000, tz=timezone.utc).replace(tzinfo=None)
    assert canais.mensagens_whatsapp(_payload(tipo="image")) == []
    assert canais.mensagens_whatsapp({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}) == []
    assert canais.mensagens_whatsapp({"entry": "lixo"}) == []
    assert canais.mensagens_whatsapp({"entry": [None, {"changes": "x"}, {"changes": [{"value": 5}]}]}) == []
    assert canais.mensagens_whatsapp([]) == []


# ---------- WhatsApp: endpoints ----------
def test_verificacao_devolve_o_desafio_com_token_correto(client, monkeypatch):
    c = _client(client, monkeypatch)
    r = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "12345"})
    assert r.status_code == 200 and r.text == "12345"


def test_verificacao_recusa_token_errado_ou_nao_configurado(client, monkeypatch):
    c = _client(client, monkeypatch)
    r = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "1"})
    assert r.status_code == 403
    c2 = _client(client, monkeypatch, token="")
    r = c2.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert r.status_code == 403


def test_post_assinado_cria_ticket_e_reenvio_nao_duplica(client, monkeypatch, db):
    c = _client(client, monkeypatch)
    corpo = json.dumps(_payload()).encode()
    r1 = c.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo))
    r2 = c.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo))
    assert r1.status_code == 200 and r1.json() == {"recebidas": 1}
    assert r2.status_code == 200 and r2.json() == {"recebidas": 0}
    with db.connect() as conn:
        linhas = conn.execute(text("SELECT canal, cliente, external_id FROM tickets")).fetchall()
    assert len(linhas) == 1 and linhas[0][0] == "whatsapp" and linhas[0][2] == "wamid.1"


def test_post_com_assinatura_invalida_ou_sem_segredo_nao_cria_nada(client, monkeypatch, db):
    c = _client(client, monkeypatch)
    corpo = json.dumps(_payload()).encode()
    assert c.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo, "outro")).status_code == 403
    assert c.post("/webhooks/whatsapp", content=corpo).status_code == 403
    c2 = _client(client, monkeypatch, segredo="")
    assert c2.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo)).status_code == 503
    with db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar() == 0


def test_post_assinado_com_json_invalido_devolve_400(client, monkeypatch):
    c = _client(client, monkeypatch)
    corpo = b"nao eh json"
    assert c.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo)).status_code == 400


def test_ticket_do_whatsapp_e_classificado_em_background(client, monkeypatch, db):
    c = _client(client, monkeypatch)
    corpo = json.dumps(_payload(texto="O pix não funciona, urgente")).encode()
    c.post("/webhooks/whatsapp", content=corpo, headers=_assinar(corpo))
    with db.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM classifications")).scalar()
    assert n == 1


# ---------- webhook genérico: idempotência ----------
def test_webhook_com_external_id_repetido_responde_duplicado(client):
    corpo = {"canal": "email", "texto": "Preciso de ajuda com a fatura", "external_id": "<a@x>"}
    r1 = client.post("/webhook/mensagens", json=corpo, headers=CHAVE)
    r2 = client.post("/webhook/mensagens", json=corpo, headers=CHAVE)
    assert r1.status_code == 202 and r1.json()["status"] == "pendente"
    assert r2.status_code == 202 and r2.json() == {"ticket_id": r1.json()["ticket_id"], "status": "duplicado"}


def test_mesmo_external_id_em_canais_diferentes_nao_conflita(db):
    a = tickets.criar_ticket("email", "mensagem um", None, None, "id-1")
    b = tickets.criar_ticket("whatsapp", "mensagem dois", None, None, "id-1")
    assert a != b


# ---------- E-mail ----------
def _eml(de="Cliente <cli@exemplo.com>", assunto="Cobrança duplicada", corpo="Fui cobrado duas vezes no cartão.",
         extra="", mid="<m1@exemplo.com>"):
    return (f"From: {de}\r\nTo: suporte@empresa.com\r\nSubject: {assunto}\r\nMessage-ID: {mid}\r\n"
            f"Date: Fri, 17 Oct 2026 10:00:00 -0300\r\n{extra}Content-Type: text/plain; charset=utf-8\r\n\r\n{corpo}\r\n"
            ).encode()


def test_email_vira_mensagem_com_assunto_corpo_e_horario_utc():
    m = canais.email_para_mensagem(_eml())
    assert m["external_id"] == "<m1@exemplo.com>" and m["cliente"] == "cli@exemplo.com"
    assert m["texto"].startswith("Cobrança duplicada\n\nFui cobrado")
    assert m["received_at"] == datetime(2026, 10, 17, 13, 0)


def test_email_remove_citacao_de_resposta():
    corpo = "Ainda não resolveram.\r\n\r\nEm sex, 16 de out. de 2026 escreveu:\r\n> texto antigo"
    assert "texto antigo" not in canais.email_para_mensagem(_eml(corpo=corpo))["texto"]


def test_email_automatico_e_ignorado():
    assert canais.email_para_mensagem(_eml(extra="Auto-Submitted: auto-replied\r\n")) is None
    assert canais.email_para_mensagem(_eml(extra="Precedence: bulk\r\n")) is None
    assert canais.email_para_mensagem(_eml(de="noreply@banco.com")) is None
    assert canais.email_para_mensagem(_eml(de="MAILER-DAEMON@x.com")) is None
    assert canais.email_para_mensagem(_eml(mid="")) is None


class FakeImap:
    def __init__(self, emails):
        self.emails, self.vistos = emails, set()

    def search(self, _c, _crit):
        ids = [str(i + 1).encode() for i in range(len(self.emails)) if (i + 1) not in self.vistos]
        return "OK", [b" ".join(ids)]

    def fetch(self, num, _p):
        return "OK", [(b"1 (RFC822 {1}", self.emails[int(num) - 1]), b")"]

    def store(self, num, _op, _flag):
        self.vistos.add(int(num))


def test_varredura_envia_ignora_e_marca_como_lido():
    imap = FakeImap([_eml(), _eml(de="noreply@x.com", mid="<2@x>"), _eml(mid="<3@x>")])
    enviados = []
    resumo = varrer_caixa(imap, lambda m: enviados.append(m) or True)
    assert resumo == {"enviados": 2, "ignorados": 1, "falhas": 0}
    assert imap.vistos == {1, 2, 3}
    assert varrer_caixa(imap, lambda m: True) == {"enviados": 0, "ignorados": 0, "falhas": 0}


def test_varredura_mantem_nao_lido_quando_a_api_falha():
    imap = FakeImap([_eml()])
    assert varrer_caixa(imap, lambda m: False)["falhas"] == 1
    assert imap.vistos == set()


def test_enviador_posta_na_api_com_chave_e_trata_erros():
    import httpx

    vistos = {}

    def handler(req: httpx.Request):
        vistos["chave"] = req.headers.get("x-api-key")
        vistos["corpo"] = json.loads(req.content)
        return httpx.Response(vistos.get("status", 202), json={})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    enviar = criar_enviador("http://api:8000", "k", http)
    msg = canais.email_para_mensagem(_eml())
    assert enviar(msg) is True
    assert vistos["chave"] == "k" and vistos["corpo"]["canal"] == "email" and vistos["corpo"]["external_id"] == "<m1@exemplo.com>"
    vistos["status"] = 500
    assert enviar(msg) is False
    vistos["status"] = 400
    assert enviar(msg) is True  # inválida: não reenviar para sempre
    def cai(_r): raise httpx.ConnectError("x")
    assert criar_enviador("http://api", "k", httpx.Client(transport=httpx.MockTransport(cai)))(msg) is False
