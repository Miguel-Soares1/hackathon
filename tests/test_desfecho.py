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


# ---------- junção com o relatório final (encerrar pelo painel gera o relatório; reabrir descarta) ----------
def test_encerrar_pelo_painel_grava_resultado_observacao_e_relatorio(client):
    tid = _post(client).json()["ticket_id"]
    r = client.post(f"/tickets/{tid}/encerrar", headers=CHAVE,
                    json={"desfecho": "encerrado", "resultado": "encaminhado", "observacao": "Foi para o financeiro."})
    assert r.status_code == 200
    rel = r.json()["relatorio"]
    assert (rel["desfecho"], rel["desfecho_rotulo"], rel["observacao"]) == ("encaminhado", "encaminhado a outra equipe",
                                                                          "Foi para o financeiro.")
    assert client.get(f"/tickets/{tid}/relatorio", headers=CHAVE).json()["desfecho"] == "encaminhado"
    assert _ticket(client, tid)["encerrado"] is True


def test_cancelar_tambem_gera_relatorio(client):
    tid = _post(client).json()["ticket_id"]
    rel = client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "cancelado"}, headers=CHAVE).json()["relatorio"]
    assert rel["desfecho"] == "cancelado" and rel["proximos_passos"] is None
    assert _ticket(client, tid)["desfecho"] == "cancelado"


def test_reabrir_descarta_o_relatorio_e_o_prazo_volta_a_correr(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE)
    assert _ticket(client, tid)["first_response_at"] is not None  # encerrar sem responder conta para o prazo
    t = client.post(f"/tickets/{tid}/reabrir", headers=CHAVE).json()
    assert t["first_response_at"] is None and t["aguardando"] is True and t["encerrado_por"] is None
    assert client.get(f"/tickets/{tid}/relatorio", headers=CHAVE).status_code == 404
    # e dá para encerrar de novo, com um relatório novo
    assert client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE).status_code == 200


def test_reabrir_mantem_a_resposta_que_ja_tinha_sido_dada(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "Já estou vendo!"}, headers=CHAVE)
    client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE)
    assert client.post(f"/tickets/{tid}/reabrir", headers=CHAVE).json()["first_response_at"] is not None


def test_finalizado_nao_aceita_resposta_nem_novo_encerramento(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "cancelado"}, headers=CHAVE)
    assert client.post(f"/tickets/{tid}/mensagens", json={"texto": "oi"}, headers=CHAVE).status_code == 409
    assert client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado"}, headers=CHAVE).status_code == 409
    assert client.post(f"/tickets/{tid}/encerramento", json={"desfecho": "resolvido"}, headers=CHAVE).status_code == 409


def test_resultado_invalido_retorna_400(client):
    tid = _post(client).json()["ticket_id"]
    r = client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado", "resultado": "talvez"}, headers=CHAVE)
    assert r.status_code == 400
    r = client.post(f"/tickets/{tid}/encerrar", json={"desfecho": "encerrado", "resultado": "cancelado"}, headers=CHAVE)
    assert r.status_code == 400
