from datetime import datetime, timedelta, timezone

from conftest import CHAVE

MSG = {"canal": "whatsapp", "cliente": "Loja Aurora", "texto": "Meu Pix não funciona, estou perdendo vendas!"}


def test_webhook_sem_chave_retorna_401(client):
    r = client.post("/webhook/mensagens", json=MSG)
    assert r.status_code == 401


def test_webhook_com_chave_errada_retorna_401(client):
    r = client.post("/webhook/mensagens", json=MSG, headers={"X-API-Key": "errada"})
    assert r.status_code == 401


def test_webhook_valido_retorna_202_e_o_ticket_fica_classificado(client):
    r = client.post("/webhook/mensagens", json=MSG, headers=CHAVE)
    assert r.status_code == 202
    ticket_id = r.json()["ticket_id"]

    t = client.get(f"/tickets/{ticket_id}", headers=CHAVE).json()  # background já rodou no TestClient
    assert t["status"] == "classificado"
    assert t["assunto"] == "pagamento" and t["urgencia"] == "critica"
    assert t["origem"] == "fallback"  # sem chave do LLM no teste
    assert t["sla"]["prazo_minutos"] == 15
    assert 0 <= float(t["conf_assunto"]) <= 1
    assert t["resposta_sugerida"]


def test_webhook_texto_curto_retorna_400(client):
    r = client.post("/webhook/mensagens", json={**MSG, "texto": "a"}, headers=CHAVE)
    assert r.status_code == 400


def test_webhook_sem_campo_obrigatorio_retorna_400(client):
    r = client.post("/webhook/mensagens", json={"texto": "mensagem ok"}, headers=CHAVE)
    assert r.status_code == 400


def test_webhook_data_no_futuro_retorna_400(client):
    futuro = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r = client.post("/webhook/mensagens", json={**MSG, "received_at": futuro}, headers=CHAVE)
    assert r.status_code == 400


def test_ticket_inexistente_retorna_404(client):
    assert client.get("/tickets/999999", headers=CHAVE).status_code == 404
    assert client.post("/tickets/999999/resposta", headers=CHAVE).status_code == 404
    assert client.post("/tickets/999999/revisao", headers=CHAVE).status_code == 404
    assert client.post("/tickets/999999/correcoes", json={"urgencia": "alta"}, headers=CHAVE).status_code == 404


def test_texto_com_sql_injection_e_tratado_como_dado(client):
    malicioso = "'; DROP TABLE tickets; -- preciso de ajuda com a fatura"
    r = client.post("/webhook/mensagens", json={**MSG, "texto": malicioso}, headers=CHAVE)
    assert r.status_code == 202
    assert client.get("/tickets", headers=CHAVE).status_code == 200  # a tabela continua existindo
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["texto"] == malicioso


def test_received_at_antigo_gera_prazo_estourado(client):
    antigo = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    r = client.post("/webhook/mensagens", json={**MSG, "received_at": antigo}, headers=CHAVE)
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["sla"]["estado"] == "estourado"  # crítica: 15 min


def test_marcar_respondido_registra_primeira_resposta_e_e_idempotente(client):
    tid = client.post("/webhook/mensagens", json=MSG, headers=CHAVE).json()["ticket_id"]
    primeiro = client.post(f"/tickets/{tid}/resposta", headers=CHAVE).json()
    segundo = client.post(f"/tickets/{tid}/resposta", headers=CHAVE).json()
    assert primeiro["sla"]["estado"] == "respondido"
    assert primeiro["first_response_at"] == segundo["first_response_at"]


def test_health_nao_exige_chave(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_endpoints_protegidos_sem_chave(client):
    for caminho in ("/tickets", "/incidentes", "/metricas", "/correcoes"):
        assert client.get(caminho).status_code == 401, caminho


def test_resposta_com_data_retroativa_e_validada(client):
    antigo = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
    tid = client.post("/webhook/mensagens", json={**MSG, "received_at": antigo}, headers=CHAVE).json()["ticket_id"]

    ok = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    r = client.post(f"/tickets/{tid}/resposta", json={"respondido_em": ok}, headers=CHAVE)
    assert r.status_code == 200 and r.json()["sla"]["cumpriu"] is True  # 10 min < 15 min

    outro = client.post("/webhook/mensagens", json={**MSG, "received_at": antigo}, headers=CHAVE).json()["ticket_id"]
    antes_do_recebimento = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    r = client.post(f"/tickets/{outro}/resposta", json={"respondido_em": antes_do_recebimento}, headers=CHAVE)
    assert r.status_code == 400

    futuro = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert client.post(f"/tickets/{outro}/resposta", json={"respondido_em": futuro}, headers=CHAVE).status_code == 400


def test_docs_podem_ser_desligados(db, monkeypatch):
    from fastapi.testclient import TestClient

    from triagem.api import create_app

    monkeypatch.setenv("DOCS_ENABLED", "0")
    c = TestClient(create_app())
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404


def test_cabecalhos_de_seguranca_presentes(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"


def test_producao_recusa_segredos_fracos(db, monkeypatch):
    import pytest

    from triagem.api import create_app

    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="insegura"):
        create_app()  # API_KEY de teste é curta e de exemplo


def test_producao_aceita_segredos_fortes(db, monkeypatch):
    from triagem.api import create_app

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("API_KEY", "k" * 32)
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://app:Segredo-Forte@127.0.0.1:3306/hackathon_test")
    assert create_app() is not None
