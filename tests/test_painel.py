"""O painel (HTML/CSS/JS estáticos) é servido pela própria API."""
from conftest import CHAVE


def test_raiz_entrega_o_painel_sem_exigir_chave(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Triagem IA" in r.text


def test_arquivos_estaticos_do_painel(client):
    assert "text/css" in client.get("/styles.css").headers["content-type"]
    assert "javascript" in client.get("/app.js").headers["content-type"]


def test_rotas_da_api_nao_sao_sombreadas_pelo_painel(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/health").json() == {"status": "ok"}


def test_dominio_exige_chave_e_lista_valores_permitidos(client):
    assert client.get("/dominio").status_code == 401
    d = client.get("/dominio", headers=CHAVE).json()
    assert d["urgencias"] == ["baixa", "media", "alta", "critica"]
    assert "pagamento" in d["assuntos"] and "retencao" in d["equipes"]
