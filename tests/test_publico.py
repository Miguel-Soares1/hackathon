from sqlalchemy import text

from conftest import CHAVE
from triagem.ratelimit import LimitadorJanela

TEXTO = "Estou sem conseguir pagar a fatura pelo Pix, aparece erro."


# ---------- limitador (puro) ----------
class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_limitador_bloqueia_apos_o_limite_por_chave_e_libera_com_o_tempo():
    r = Relogio()
    lim = LimitadorJanela(por_chave=2, global_=100, janela_s=60, relogio=r)
    assert lim.permitir("a")[0] and lim.permitir("a")[0]
    ok, espera = lim.permitir("a")
    assert ok is False and 1 <= espera <= 61
    r.t += 61
    assert lim.permitir("a")[0] is True


def test_limitador_isola_chaves_diferentes():
    lim = LimitadorJanela(por_chave=1, global_=100, relogio=Relogio())
    assert lim.permitir("a")[0] and lim.permitir("b")[0]


def test_limitador_global_vale_para_todas_as_chaves():
    lim = LimitadorJanela(por_chave=10, global_=2, relogio=Relogio())
    assert lim.permitir("a")[0] and lim.permitir("b")[0]
    assert lim.permitir("c")[0] is False


def test_limitador_nao_conta_eventos_negados():
    r = Relogio()
    lim = LimitadorJanela(por_chave=1, global_=100, janela_s=60, relogio=r)
    lim.permitir("a")
    for _ in range(5):
        lim.permitir("a")  # negados
    r.t += 61
    assert lim.permitir("a")[0] is True


# ---------- endpoint público ----------
def test_pagina_de_envio_e_servida_com_csp(client):
    r = client.get("/enviar")
    assert r.status_code == 200 and "<form" in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_envio_publico_cria_ticket_classificado_sem_exigir_chave(client):
    r = client.post("/public/mensagens", json={"texto": TEXTO, "cliente": "Maria"})
    assert r.status_code == 202 and r.json()["protocolo"]
    t = client.get(f"/tickets/{r.json()['protocolo']}", headers=CHAVE).json()
    assert t["canal"] == "formulario-web" and t["status"] == "classificado"


def test_envio_publico_nao_revela_a_classificacao(client):
    corpo = client.post("/public/mensagens", json={"texto": TEXTO}).json()
    assert set(corpo) == {"protocolo", "status"}


def test_honeypot_preenchido_descarta_sem_criar_ticket(client, db):
    r = client.post("/public/mensagens", json={"texto": TEXTO, "website": "http://spam.exemplo"})
    assert r.status_code == 202 and r.json()["protocolo"] is None
    with db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar() == 0


def test_texto_curto_ou_ausente_retorna_400(client):
    assert client.post("/public/mensagens", json={"texto": "oi"}).status_code == 400
    assert client.post("/public/mensagens", json={}).status_code == 400
    assert client.post("/public/mensagens", json={"texto": "x" * 1001}).status_code == 400


def test_limite_por_ip_retorna_429_com_retry_after(db, monkeypatch):
    from fastapi.testclient import TestClient

    from triagem.api import create_app

    monkeypatch.setenv("PUBLIC_RATE_PER_IP_MIN", "3")
    c = TestClient(create_app())
    codigos = [c.post("/public/mensagens", json={"texto": TEXTO}).status_code for _ in range(5)]
    assert codigos == [202, 202, 202, 429, 429]
    assert "retry-after" in c.post("/public/mensagens", json={"texto": TEXTO}).headers


def test_limite_global_protege_o_custo_do_llm(db, monkeypatch):
    from fastapi.testclient import TestClient

    from triagem.api import create_app

    monkeypatch.setenv("PUBLIC_RATE_GLOBAL_MIN", "2")
    monkeypatch.setenv("TRUST_PROXY", "1")
    c = TestClient(create_app())
    codigos = [c.post("/public/mensagens", json={"texto": TEXTO}, headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
               for i in range(4)]
    assert codigos == [202, 202, 429, 429]  # IPs diferentes, mas o teto global vale para todos


def test_x_forwarded_for_so_vale_com_trust_proxy(db, monkeypatch):
    from fastapi.testclient import TestClient

    from triagem.api import create_app

    monkeypatch.setenv("PUBLIC_RATE_PER_IP_MIN", "1")
    c = TestClient(create_app())  # TRUST_PROXY desligado: cabeçalho ignorado, mesmo IP
    a = c.post("/public/mensagens", json={"texto": TEXTO}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code
    b = c.post("/public/mensagens", json={"texto": TEXTO}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code
    assert (a, b) == (202, 429)


def test_endpoint_publico_nao_expoe_o_restante_da_api(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/metricas").status_code == 401
