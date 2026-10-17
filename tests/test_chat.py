"""Chat do atendimento: conversa por cliente, resposta do atendente e integração por API."""
from datetime import timedelta

from sqlalchemy import text

from conftest import CHAVE
from triagem import tickets
from triagem.db import utcnow


def _post(client, **kw):
    corpo = {"canal": "chat", "texto": "Meu pix não caiu e preciso resolver", "conversa_id": "cli-1", "cliente": "Ana"}
    corpo.update(kw)
    return client.post("/webhook/mensagens", json=corpo, headers=CHAVE)


def test_primeira_mensagem_cria_ticket_e_a_primeira_mensagem_da_conversa(client):
    r = _post(client)
    assert r.json()["status"] == "pendente"
    msgs = client.get(f"/tickets/{r.json()['ticket_id']}/mensagens", headers=CHAVE).json()
    assert [(m["direcao"], m["texto"]) for m in msgs] == [("entrada", "Meu pix não caiu e preciso resolver")]


def test_nova_mensagem_do_mesmo_cliente_entra_na_mesma_conversa(client, db):
    t1 = _post(client).json()["ticket_id"]
    r2 = _post(client, texto="Alguma novidade? Continua sem funcionar")
    assert r2.json() == {"ticket_id": t1, "status": "anexada"}
    with db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM messages")).scalar() == 2


def test_clientes_diferentes_ou_sem_identificacao_geram_tickets_separados(client, db):
    a = _post(client).json()["ticket_id"]
    b = _post(client, conversa_id="cli-2").json()["ticket_id"]
    c = _post(client, conversa_id=None, cliente=None).json()["ticket_id"]
    d = _post(client, conversa_id=None, cliente=None).json()["ticket_id"]
    assert len({a, b, c, d}) == 4


def test_sem_conversa_id_o_mesmo_cliente_fica_na_mesma_conversa(client):
    # Integrações que não mandam conversa_id: o cliente é reconhecido pelo contato (telefone, e-mail, usuário ou nome).
    a = _post(client, canal="whatsapp", conversa_id=None, cliente="Mariana Souza (5511987654321)").json()
    b = _post(client, canal="WhatsApp", conversa_id=None, cliente="Mariana Souza (5511987654321)").json()
    c = _post(client, canal="whatsapp", conversa_id="5511987654321", cliente="Mariana").json()  # vindo da Meta
    assert a["status"] == "pendente" and b == c == {"ticket_id": a["ticket_id"], "status": "anexada"}
    assert tickets.chave_conversa("instagram", "instagram:Ana.Ribeiro") == "ana.ribeiro"


def test_unificar_junta_duplicados_antigos_do_mesmo_cliente(client, db):
    # Arrange: tickets antigos, um por mensagem e sem conversa_id (antes do chat)
    ids = [tickets.criar_ticket("whatsapp", f"mensagem {n}", "Mariana Souza (5511987654321)") for n in range(3)]
    outro = tickets.criar_ticket("whatsapp", "outra pessoa", "Carlos Lima (5521998761234)")
    tickets.marcar_respondido(ids[1])
    # Act: o plano não altera nada; aplicar une
    assert tickets.unificar_conversas() == [{"principal": ids[0], "canal": "whatsapp",
                                             "cliente": "Mariana Souza (5511987654321)", "unidos": ids[1:]}]
    tickets.unificar_conversas(aplicar=True)
    # Assert: um ticket só, com as 3 mensagens e a 1ª resposta; o outro cliente não muda
    with db.connect() as conn:
        restantes = [r.id for r in conn.execute(text("SELECT id FROM tickets ORDER BY id"))]
    assert restantes == [ids[0], outro]
    assert [m["texto"] for m in tickets.mensagens(ids[0])] == ["mensagem 0", "mensagem 1", "mensagem 2"]
    assert tickets.obter(ids[0])["first_response_at"] is not None
    # e a próxima mensagem dela entra nessa conversa
    assert _post(client, canal="whatsapp", conversa_id="5511987654321").json()["ticket_id"] == ids[0]
    assert tickets.unificar_conversas() == []


def test_unificar_respeita_conversa_encerrada_ha_mais_de_24h(db):
    antigo = tickets.criar_ticket("email", "pedido antigo", "ana@exemplo.com", utcnow() - timedelta(days=3))
    tickets.marcar_respondido(antigo, utcnow() - timedelta(days=3) + timedelta(hours=1))
    novo = tickets.criar_ticket("email", "assunto novo", "ana@exemplo.com")
    assert tickets.unificar_conversas() == []
    assert novo != antigo


def test_canais_diferentes_nao_misturam_a_conversa(client):
    a = _post(client, canal="whatsapp").json()["ticket_id"]
    b = _post(client, canal="email").json()["ticket_id"]
    assert a != b


def test_resposta_do_atendente_aparece_no_chat_e_registra_o_sla(client):
    tid = _post(client).json()["ticket_id"]
    r = client.post(f"/tickets/{tid}/mensagens", json={"texto": "Olá! Já estamos verificando.", "autor": "Bia"}, headers=CHAVE)
    assert r.status_code == 201 and r.json()["direcao"] == "saida"
    msgs = client.get(f"/tickets/{tid}/mensagens", headers=CHAVE).json()
    assert [m["direcao"] for m in msgs] == ["entrada", "saida"] and msgs[1]["autor"] == "Bia"
    assert tickets.obter(tid)["first_response_at"] is not None


def test_segunda_resposta_nao_altera_a_primeira_resposta_do_sla(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "primeira"}, headers=CHAVE)
    primeira = tickets.obter(tid)["first_response_at"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "segunda"}, headers=CHAVE)
    assert tickets.obter(tid)["first_response_at"] == primeira


def test_mensagem_vazia_ou_ticket_inexistente(client):
    tid = _post(client).json()["ticket_id"]
    assert client.post(f"/tickets/{tid}/mensagens", json={"texto": "   "}, headers=CHAVE).status_code == 400
    assert client.post(f"/tickets/{tid}/mensagens", json={}, headers=CHAVE).status_code == 400
    assert client.post("/tickets/9999/mensagens", json={"texto": "oi"}, headers=CHAVE).status_code == 404
    assert client.get("/tickets/9999/mensagens", headers=CHAVE).status_code == 404


def test_endpoints_do_chat_exigem_chave(client):
    tid = _post(client).json()["ticket_id"]
    assert client.get(f"/tickets/{tid}/mensagens").status_code == 401
    assert client.post(f"/tickets/{tid}/mensagens", json={"texto": "oi"}).status_code == 401


def test_polling_com_depois_de_devolve_so_as_novas(client):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "resposta"}, headers=CHAVE)
    todas = client.get(f"/tickets/{tid}/mensagens", headers=CHAVE).json()
    _post(client, texto="obrigado, mas ainda não resolveu")
    novas = client.get(f"/tickets/{tid}/mensagens", params={"depois_de": todas[-1]["id"]}, headers=CHAVE).json()
    assert [m["texto"] for m in novas] == ["obrigado, mas ainda não resolveu"]


def test_cliente_que_responde_apos_o_atendente_volta_para_a_fila_de_espera(client):
    tid = _post(client).json()["ticket_id"]
    assert tickets.obter(tid)["aguardando"] is True
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "resposta"}, headers=CHAVE)
    assert tickets.obter(tid)["aguardando"] is False
    _post(client, texto="ainda estou com o problema")
    assert tickets.obter(tid)["aguardando"] is True
    assert tickets.obter(tid)["ultima_texto"] == "ainda estou com o problema"


def test_apos_24h_da_resposta_a_nova_mensagem_abre_novo_ticket(client, db):
    tid = _post(client).json()["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "resposta"}, headers=CHAVE)
    antigo = utcnow() - timedelta(hours=25)
    with db.begin() as conn:
        conn.execute(text("UPDATE tickets SET first_response_at = :q WHERE id = :i"), {"q": antigo, "i": tid})
        conn.execute(text("UPDATE messages SET created_at = :q WHERE ticket_id = :i AND direcao = 'saida'"), {"q": antigo, "i": tid})
    novo = _post(client, texto="voltei, outro problema agora").json()
    assert novo["status"] == "pendente" and novo["ticket_id"] != tid


def test_external_id_repetido_na_conversa_nao_duplica_a_mensagem(client, db):
    _post(client, external_id="m1")
    _post(client, external_id="m2", texto="segunda mensagem do cliente")
    r = _post(client, external_id="m2", texto="segunda mensagem do cliente")
    assert r.json()["status"] == "duplicado"
    with db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM messages")).scalar() == 2


def test_ticket_antigo_sem_mensagens_mostra_o_texto_original(client, db):
    tid = _post(client).json()["ticket_id"]
    with db.begin() as conn:
        conn.execute(text("DELETE FROM messages"))
    msgs = tickets.mensagens(tid)
    assert len(msgs) == 1 and msgs[0]["direcao"] == "entrada"


def test_whatsapp_usa_o_numero_como_conversa(client, monkeypatch, db):
    import hashlib, hmac, json
    from test_canais import _client, _payload, SEGREDO
    c = _client(client, monkeypatch)
    for mid, txt in (("w1", "Meu pix não caiu hoje"), ("w2", "E então, alguma novidade?")):
        corpo = json.dumps(_payload(mid=mid, texto=txt)).encode()
        sig = "sha256=" + hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
        r = c.post("/webhooks/whatsapp", content=corpo, headers={"X-Hub-Signature-256": sig})
        assert r.status_code == 200
    with db.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM messages")).scalar() == 2
