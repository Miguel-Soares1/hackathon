"""Desfecho do atendimento: encerrar, cancelar e reabrir (cartões do Dashboard)."""
from conftest import CHAVE


def _post(client, **kw):
    corpo = {"canal": "chat", "texto": "Meu pix não caiu e preciso resolver", "conversa_id": "cli-1", "cliente": "Ana"}
    corpo.update(kw)
    return client.post("/webhook/mensagens", json=corpo, headers=CHAVE)


def _ticket(client, tid):
    return client.get(f"/tickets/{tid}", headers=CHAVE).json()


def test_encerrar_tira_da_fila_de_espera_e_registra_o_desfecho(client):
    # Arrange
    tid = _post(client).json()["ticket_id"]
    assert _ticket(client, tid)["aguardando"] is True
    # Act
    r = client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE)
    # Assert
    assert r.status_code == 200
    t = _ticket(client, tid)
    assert t["desfecho"] == "encerrado" and t["encerrado_em"] is not None and t["aguardando"] is False


def test_cancelar_e_reabrir(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "cancelado"}, headers=CHAVE)
    assert _ticket(client, tid)["desfecho"] == "cancelado"
    r = client.post(f"/tickets/{tid}/reabrir", headers=CHAVE)
    assert r.status_code == 200 and r.json()["desfecho"] is None and r.json()["aguardando"] is True


def test_cliente_que_escreve_depois_de_encerrado_abre_ticket_novo(client):
    # Arrange
    t1 = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{t1}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE)
    # Act
    r = _post(client, texto="Voltou a dar erro no pix hoje")
    # Assert
    assert r.json()["ticket_id"] != t1 and r.json()["status"] == "pendente"


def test_desfecho_invalido_ou_ticket_inexistente(client):
    tid = _post(client).json()["ticket_id"]
    assert client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "arquivado"}, headers=CHAVE).status_code == 400
    assert client.post("/tickets/999999/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE).status_code == 404
    assert client.post("/tickets/999999/reabrir", headers=CHAVE).status_code == 404


def test_encerrar_exige_chave(client):
    tid = _post(client).json()["ticket_id"]
    assert client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}).status_code == 401
