"""Relatório de problemas, alertas críticos e plantão (ADR-020)."""
from conftest import CHAVE
from triagem import tickets, usuarios


def _sessao(client, usuario="ana", nome="Ana"):
    usuarios.criar(usuario, nome, "senha-forte-1", "atendente")
    token = client.post("/auth/login", json={"usuario": usuario, "senha": "senha-forte-1"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_problema_com_ocorrencias_conta_as_vezes_e_os_clientes(client):
    s = _sessao(client)
    p = client.post("/problemas", headers=s, json={"titulo": "Pix não cai no Banco X",
                                                   "caracteristicas": "Pix aparece concluído mas não chega; só Banco X."}).json()
    assert p["status"] == "aberto" and p["total"] == 0 and p["criado_por"] == "Ana"
    tid = client.post("/webhook/mensagens", headers=CHAVE, json={"canal": "whatsapp", "texto": "meu pix não caiu",
                                                                  "cliente": "Mariana (5511987654321)"}).json()["ticket_id"]
    for cliente, ticket in (("5511987654321", tid), ("5511987654321", None), ("5521998761234", None)):
        r = client.post(f"/problemas/{p['id']}/ocorrencias", headers=s, json={"cliente_id": cliente, "ticket_id": ticket})
        assert r.status_code == 201
    p = client.get("/problemas", headers=s).json()[0]
    assert p["total"] == 3 and p["clientes_distintos"] == 2
    assert p["ocorrencias"][-1]["ticket_id"] == tid and p["ocorrencias"][0]["registrado_por"] == "Ana"


def test_problema_resolvido_vai_para_o_fim_e_ocorrencia_pode_ser_removida(client):
    s = _sessao(client)
    a = client.post("/problemas", headers=s, json={"titulo": "Problema A", "caracteristicas": "detalhes A"}).json()
    b = client.post("/problemas", headers=s, json={"titulo": "Problema B", "caracteristicas": "detalhes B"}).json()
    o = client.post(f"/problemas/{a['id']}/ocorrencias", headers=s, json={"cliente_id": "cliente-1"}).json()["ocorrencias"][0]
    r = client.patch(f"/problemas/{a['id']}", headers=s, json={"status": "resolvido"}).json()
    assert r["status"] == "resolvido" and r["resolvido_em"]
    assert [x["id"] for x in client.get("/problemas", headers=s).json()] == [b["id"], a["id"]]
    assert client.delete(f"/problemas/{a['id']}/ocorrencias/{o['id']}", headers=s).json()["total"] == 0


def test_problema_valida_dados_e_exige_acesso(client):
    s = _sessao(client)
    assert client.post("/problemas", headers=s, json={"titulo": "ab", "caracteristicas": "x"}).status_code == 400
    assert client.post("/problemas/999/ocorrencias", headers=s, json={"cliente_id": "123"}).status_code == 404
    pid = client.post("/problemas", headers=s, json={"titulo": "Problema", "caracteristicas": "descrição"}).json()["id"]
    assert client.post(f"/problemas/{pid}/ocorrencias", headers=s, json={"cliente_id": "123", "ticket_id": 999999}).status_code == 400
    assert client.get("/problemas").status_code == 401


def test_alertas_mostram_criticos_esperando_e_quem_esta_de_plantao(client, monkeypatch):
    s = _sessao(client)
    _sessao(client, "bia", "Bia")
    tid = client.post("/webhook/mensagens", headers=CHAVE, json={"canal": "whatsapp", "texto": "sistema fora do ar", "cliente": "Loja (5511900000000)"}).json()["ticket_id"]
    original = tickets.listar

    def listar(limite=200, **kw):  # o plano B não marca crítico com esse texto: força a urgência no teste
        return [{**t, "urgencia": "critica"} if t["ticket_id"] == tid else t for t in original(limite=limite, **kw)]
    monkeypatch.setattr(tickets, "listar", listar)
    r = client.get("/alertas", headers=s).json()
    assert [c["ticket_id"] for c in r["criticos"]] == [tid] and r["plantao"] == ["Ana", "Bia"]
    client.post("/auth/plantao", headers=s, json={"de_plantao": False})
    assert client.get("/alertas", headers=s).json()["plantao"] == ["Bia"]
    assert client.get("/auth/eu", headers=s).json()["de_plantao"] is False
    client.post(f"/tickets/{tid}/mensagens", headers=s, json={"texto": "Já estou vendo!"})
    assert client.get("/alertas", headers=s).json()["criticos"] == []  # respondido: sai do alerta
