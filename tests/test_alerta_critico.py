"""Alerta do painel: cliente de urgência crítica esperando resposta há 10 minutos."""
from sqlalchemy import text

from conftest import CHAVE
from triagem.db import get_engine


def _critico(client, conversa_id="cli-1"):
    r = client.post("/webhook/mensagens", headers=CHAVE,
                    json={"canal": "chat", "texto": "Minha loja parou de receber pagamentos", "conversa_id": conversa_id,
                          "cliente": "Ana"})
    tid = r.json()["ticket_id"]
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE classifications SET urgencia = 'critica' WHERE ticket_id = :t"), {"t": tid})
    return tid


def _envelhecer(tid, minutos):
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE tickets SET received_at = received_at - INTERVAL :m MINUTE WHERE id = :t"),
                     {"m": minutos, "t": tid})
        conn.execute(text("UPDATE messages SET created_at = created_at - INTERVAL :m MINUTE WHERE ticket_id = :t"),
                     {"m": minutos, "t": tid})


def _ticket(client, tid):
    return client.get(f"/tickets/{tid}", headers=CHAVE).json()


def test_critico_sem_resposta_ha_10_min_alerta(client):
    tid = _critico(client)
    _envelhecer(tid, 11)

    t = _ticket(client, tid)
    assert t["alerta_critico"] is True and t["espera_min"] >= 10
    assert any(x["ticket_id"] == tid and x["alerta_critico"] for x in client.get("/tickets", headers=CHAVE).json())


def test_antes_dos_10_min_nao_alerta(client):
    tid = _critico(client)
    _envelhecer(tid, 9)

    assert _ticket(client, tid)["alerta_critico"] is False


def test_resposta_do_atendente_tira_o_alerta(client):
    tid = _critico(client)
    _envelhecer(tid, 11)
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "Já estou verificando", "autor": "Bruno"}, headers=CHAVE)

    t = _ticket(client, tid)
    assert t["alerta_critico"] is False and t["espera_min"] is None


def test_nova_mensagem_sem_resposta_conta_desde_ela(client):
    tid = _critico(client)
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "Já estou verificando", "autor": "Bruno"}, headers=CHAVE)
    _envelhecer(tid, 30)
    client.post("/webhook/mensagens", headers=CHAVE,
                json={"canal": "chat", "texto": "Ainda não voltou", "conversa_id": "cli-1", "cliente": "Ana"})

    t = _ticket(client, tid)
    assert t["aguardando"] is True and t["alerta_critico"] is False and t["espera_min"] < 1


def test_alta_nao_alerta(client):
    tid = _critico(client)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE classifications SET urgencia = 'alta' WHERE ticket_id = :t"), {"t": tid})
    _envelhecer(tid, 30)

    assert _ticket(client, tid)["alerta_critico"] is False
