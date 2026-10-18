"""Mensagens internas: chat direto entre atendentes."""
import base64
from datetime import timedelta

from conftest import CHAVE
from triagem import equipe
from triagem.db import utcnow


def _env(client, de="Ana", para="Bruno", **kw):
    return client.post("/equipe/mensagens", json={"de": de, "para": para, **kw}, headers=CHAVE)


def test_presenca_cria_o_atendente_e_mostra_online_para_os_colegas(client):
    client.post("/equipe/presenca", json={"nome": "Ana"}, headers=CHAVE)
    client.post("/equipe/presenca", json={"nome": "Bruno"}, headers=CHAVE)
    lista = client.get("/equipe", params={"eu": "Ana"}, headers=CHAVE).json()
    assert [(c["nome"], c["online"]) for c in lista] == [("Bruno", True)]


def test_quem_sumiu_ha_mais_de_2_min_aparece_offline(client):
    equipe.presenca("Carla", agora=utcnow() - timedelta(minutes=5))
    lista = client.get("/equipe", params={"eu": "Ana"}, headers=CHAVE).json()
    assert lista[0]["nome"] == "Carla" and lista[0]["online"] is False and lista[0]["ultima_atividade"]


def test_conversa_entre_dois_atendentes_e_contagem_de_nao_lidas(client):
    # Arrange
    client.post("/equipe", json={"nome": "Bruno"}, headers=CHAVE)
    # Act
    assert _env(client, texto="Oi Bruno, pode olhar o ticket 12?").status_code == 201
    _env(client, de="Bruno", para="Ana", texto="Já vejo!")
    # Assert: Ana tem 1 não lida de Bruno, com prévia
    lista = client.get("/equipe", params={"eu": "Ana"}, headers=CHAVE).json()
    assert lista[0]["nao_lidas"] == 1 and lista[0]["ultima_mensagem"]["texto"] == "Já vejo!"
    conv = client.get("/equipe/conversa", params={"eu": "Ana", "com": "Bruno"}, headers=CHAVE).json()
    assert [(m["minha"], m["texto"]) for m in conv] == [(True, "Oi Bruno, pode olhar o ticket 12?"), (False, "Já vejo!")]
    # abrir a conversa marca como lida
    assert client.get("/equipe", params={"eu": "Ana"}, headers=CHAVE).json()[0]["nao_lidas"] == 0


def test_polling_com_depois_de_traz_so_as_novas(client):
    client.post("/equipe", json={"nome": "Bruno"}, headers=CHAVE)
    primeira = _env(client, texto="um").json()
    _env(client, texto="dois")
    novas = client.get("/equipe/conversa", params={"eu": "Ana", "com": "Bruno", "depois_de": primeira["id"]}, headers=CHAVE).json()
    assert [m["texto"] for m in novas] == ["dois"]


def test_anexo_de_audio_e_baixado_so_por_quem_participa(client):
    client.post("/equipe", json={"nome": "Bruno"}, headers=CHAVE)
    client.post("/equipe", json={"nome": "Carla"}, headers=CHAVE)
    audio = base64.b64encode(b"\x1aE\xdf\xa3audio-falso").decode()
    m = _env(client, anexo_nome="audio.webm", anexo_tipo="audio/webm;codecs=opus", anexo_base64=audio).json()
    assert m["anexo"] == {"nome": "audio.webm", "tipo": "audio/webm", "tamanho": 15}
    r = client.get(f"/equipe/anexos/{m['id']}", params={"eu": "Bruno"}, headers=CHAVE)
    assert r.status_code == 200 and r.content == b"\x1aE\xdf\xa3audio-falso" and r.headers["content-type"] == "audio/webm"
    assert client.get(f"/equipe/anexos/{m['id']}", params={"eu": "Carla"}, headers=CHAVE).status_code == 404


def test_anexo_com_tipo_proibido_ou_grande_demais_e_recusado(client):
    client.post("/equipe", json={"nome": "Bruno"}, headers=CHAVE)
    html = base64.b64encode(b"<script>alert(1)</script>").decode()
    assert _env(client, anexo_nome="x.html", anexo_tipo="text/html", anexo_base64=html).status_code == 400
    grande = base64.b64encode(b"0" * (equipe.MAX_ANEXO + 1)).decode()
    assert _env(client, anexo_nome="a.pdf", anexo_tipo="application/pdf", anexo_base64=grande).status_code == 400


def test_validacoes(client):
    client.post("/equipe", json={"nome": "Bruno"}, headers=CHAVE)
    assert _env(client, texto="   ").status_code == 400                      # vazia
    assert _env(client, para="Ninguém", texto="oi").status_code == 404        # destinatário inexistente
    assert _env(client, para="Ana", texto="oi").status_code == 400            # para si mesmo
    assert client.get("/equipe", params={"eu": "Ana"}).status_code == 401     # sem chave
