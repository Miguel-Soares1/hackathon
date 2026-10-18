"""Encerramento automático quando o cliente para de responder."""
from datetime import timedelta

from sqlalchemy import text

from conftest import CHAVE
from triagem import inatividade, tickets
from triagem.db import get_engine, utcnow


def _conversa(client, conversa_id="cli-1"):
    r = client.post("/webhook/mensagens", headers=CHAVE,
                    json={"canal": "chat", "texto": "Como troco meu endereço?", "conversa_id": conversa_id, "cliente": "Ana"})
    return r.json()["ticket_id"]


def _responder(client, tid, texto="Pode me confirmar seu CPF?", autor="Bruno"):
    client.post(f"/tickets/{tid}/mensagens", json={"texto": texto, "autor": autor}, headers=CHAVE)


def _envelhecer(tid, minutos):
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE messages SET created_at = created_at - INTERVAL :m MINUTE WHERE ticket_id = :t"),
                     {"m": minutos, "t": tid})


def test_encerra_quando_o_cliente_fica_10_min_sem_responder(client):
    tid = _conversa(client)
    _responder(client, tid)
    _envelhecer(tid, 11)

    assert inatividade.encerrar_inativos() == [tid]

    t = client.get(f"/tickets/{tid}", headers=CHAVE).json()
    assert t["encerrado"] is True and t["encerrado_por"] == inatividade.AUTOR
    rel = client.get(f"/tickets/{tid}/relatorio", headers=CHAVE).json()
    assert rel["desfecho"] == "sem_retorno"
    ultima = tickets.mensagens(tid)[-1]
    assert ultima["direcao"] == "saida" and ultima["texto"] == inatividade.AVISO["pt"]


def test_nao_encerra_antes_dos_10_min(client):
    tid = _conversa(client)
    _responder(client, tid)
    _envelhecer(tid, 9)

    assert inatividade.encerrar_inativos() == []


def test_nao_encerra_quando_quem_espera_e_o_cliente(client):
    tid = _conversa(client)  # sem resposta nossa: o cliente está esperando
    _responder(client, tid)
    client.post("/webhook/mensagens", headers=CHAVE,
                json={"canal": "chat", "texto": "Meu CPF é 123", "conversa_id": "cli-1", "cliente": "Ana"})
    _envelhecer(tid, 30)

    assert inatividade.encerrar_inativos() == []


def test_nao_encerra_logo_apos_a_ia_transferir_para_um_atendente(client):
    tid = _conversa(client)
    tickets.responder_chat(tid, "Vou te transferir para um atendente.", tickets.AUTOR_IA)
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE tickets SET modo = 'humano' WHERE id = :t"), {"t": tid})
    _envelhecer(tid, 30)

    assert inatividade.encerrar_inativos() == []


def test_zero_desliga(client):
    tid = _conversa(client)
    _responder(client, tid)
    _envelhecer(tid, 30)
    with get_engine().begin() as conn:
        conn.execute(text("REPLACE INTO app_config (chave, valor) VALUES ('encerrar_inativo_min', '0')"))

    assert inatividade.encerrar_inativos(utcnow() + timedelta(hours=1)) == []
