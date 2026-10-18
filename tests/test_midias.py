import base64
import json
from dataclasses import replace

import httpx
import pytest

from conftest import CHAVE
from triagem import midias, tickets
from triagem.config import get_settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
OGG = b"OggS" + b"\x00" * 32
WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 32


def b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode()


def settings(chave="k"):
    return replace(get_settings(), gemini_api_key=chave, gemini_base_url="https://gemini.exemplo.test",
                   gemini_model="modelo", midia_timeout=5.0)


def cliente_http(*respostas):
    """Cliente httpx falso que devolve as respostas na ordem (sem rede)."""
    fila = list(respostas)
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return fila.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler)), chamadas


def ok(texto):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": texto}]}}]})


# ---------- validação ----------
def test_validar_aceita_audio_do_navegador_com_codec_no_mime():
    m = midias.validar("audio", "audio/webm;codecs=opus", b64(WEBM))
    assert m.mime == "audio/webm" and m.dados == WEBM


@pytest.mark.parametrize("tipo, mime, dados, erro", [
    ("video", "video/mp4", b64(PNG), "tipo de mídia"),
    ("imagem", "image/gif", b64(PNG), "formato não aceito"),
    ("imagem", "image/png", "não é base64!", "base64 inválido"),
    ("imagem", "image/png", "", "vazio"),
    ("imagem", "image/jpeg", b64(PNG), "não é image/jpeg"),   # extensão trocada
    ("audio", "audio/ogg", b64(b"<script>alert(1)</script>"), "não é audio/ogg"),
])
def test_validar_recusa_midia_invalida(tipo, mime, dados, erro):
    with pytest.raises(midias.MidiaInvalida, match=erro):
        midias.validar(tipo, mime, dados)


def test_validar_recusa_arquivo_grande(monkeypatch):
    monkeypatch.setattr(midias, "MAX_BYTES", 10)
    with pytest.raises(midias.MidiaInvalida, match="maior que"):
        midias.validar("imagem", "image/png", b64(PNG))


# ---------- leitura com o Gemini ----------
def test_ler_com_ia_envia_a_midia_e_devolve_o_texto():
    client, chamadas = cliente_http(ok("  Meu Pix não está funcionando.  "))
    texto = midias.ler_com_ia(midias.Midia("audio", "audio/ogg", OGG), settings(), client)

    assert texto == "Meu Pix não está funcionando."
    req = chamadas[0]
    assert req.url == "https://gemini.exemplo.test/models/modelo:generateContent"
    assert req.headers["x-goog-api-key"] == "k"
    partes = json.loads(req.content)["contents"][0]["parts"]
    assert "Transcreva" in partes[0]["text"]
    assert partes[1]["inline_data"] == {"mime_type": "audio/ogg", "data": b64(OGG)}


def test_ler_com_ia_ignora_partes_de_raciocinio():
    resp = httpx.Response(200, json={"candidates": [{"content": {"parts": [
        {"text": "pensando...", "thought": True}, {"text": "Tela com erro 500."}]}}]})
    client, _ = cliente_http(resp)
    assert midias.ler_com_ia(midias.Midia("imagem", "image/png", PNG), settings(), client) == "Tela com erro 500."


@pytest.mark.parametrize("resposta", [
    httpx.Response(500, json={}),
    httpx.Response(200, json={"candidates": []}),
    ok("   "),
])
def test_ler_com_ia_levanta_erro_na_falha(resposta):
    client, _ = cliente_http(resposta)
    with pytest.raises(midias.MidiaErro):
        midias.ler_com_ia(midias.Midia("imagem", "image/png", PNG), settings(), client, esperas=())


def test_ler_com_ia_tenta_de_novo_quando_o_gemini_esta_sobrecarregado():
    client, chamadas = cliente_http(httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}}),
                                    httpx.Response(429, json={}), ok("Transcrição depois da sobrecarga."))
    r = midias.ler_com_ia(midias.Midia("audio", "audio/ogg", OGG), settings(), client, esperas=(0, 0))
    assert r == "Transcrição depois da sobrecarga." and len(chamadas) == 3


def test_ler_com_ia_desiste_depois_das_tentativas_e_nao_insiste_em_erro_definitivo():
    client, chamadas = cliente_http(*[httpx.Response(503, json={})] * 3)
    with pytest.raises(midias.MidiaErro):
        midias.ler_com_ia(midias.Midia("audio", "audio/ogg", OGG), settings(), client, esperas=(0, 0))
    assert len(chamadas) == 3
    client, chamadas = cliente_http(httpx.Response(400, json={}))
    with pytest.raises(midias.MidiaErro):
        midias.ler_com_ia(midias.Midia("audio", "audio/ogg", OGG), settings(), client, esperas=(0, 0))
    assert len(chamadas) == 1


def test_ler_com_ia_sem_chave_nao_chama_a_rede():
    client, chamadas = cliente_http()
    with pytest.raises(midias.MidiaErro, match="GEMINI_API_KEY"):
        midias.ler_com_ia(midias.Midia("imagem", "image/png", PNG), settings(chave=""), client)
    assert chamadas == []


# ---------- webhook + pipeline ----------
def test_webhook_so_com_audio_transcreve_e_classifica(client, monkeypatch):
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: "Meu Pix não funciona, estou perdendo vendas!")
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "midias": [{"tipo": "audio", "mime": "audio/ogg", "dados_base64": b64(OGG)}],
    })
    assert r.status_code == 202

    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["status"] == "classificado"
    assert t["texto"] == "[Áudio transcrito pela IA]: Meu Pix não funciona, estou perdendo vendas!"
    assert t["assunto"] == "pagamento"  # a triagem leu a transcrição
    [m] = t["midias"]
    assert m["tipo"] == "audio" and m["status"] == "lido" and m["conteudo"].startswith("Meu Pix")
    assert "dados" not in m  # os bytes não vão na listagem


def test_webhook_texto_e_foto_juntam_os_dois(client, monkeypatch):
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: "Print da tela com 'erro no pagamento'.")
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "chat", "texto": "Olha o que aparece:",
        "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)}],
    })
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["texto"] == "Olha o que aparece:\n\n[Foto descrita pela IA]: Print da tela com 'erro no pagamento'."


def test_webhook_com_falha_da_ia_ainda_classifica_e_avisa(client):
    # Sem GEMINI_API_KEY no teste: a mídia não é lida, mas o ticket não trava.
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "texto": "Mandei um áudio explicando",
        "midias": [{"tipo": "audio", "mime": "audio/ogg", "dados_base64": b64(OGG)}],
    })
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["status"] == "classificado"
    assert "[Áudio enviado: não foi possível transcrever]" in t["texto"]
    assert t["midias"][0]["status"] == "erro"


def test_reprocessar_nao_duplica_o_texto(client, monkeypatch):
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: "transcrição")
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "midias": [{"tipo": "audio", "mime": "audio/ogg", "dados_base64": b64(OGG)}],
    })
    tid = r.json()["ticket_id"]
    assert midias.processar(tid, "qualquer") is None  # mídia já lida: nada muda
    assert client.get(f"/tickets/{tid}", headers=CHAVE).json()["texto"] == "[Áudio transcrito pela IA]: transcrição"


def test_webhook_sem_texto_e_sem_midia_retorna_400(client):
    r = client.post("/webhook/mensagens", headers=CHAVE, json={"canal": "whatsapp"})
    assert r.status_code == 400


def test_webhook_midia_invalida_retorna_400_e_nao_cria_ticket(client):
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "texto": "segue foto",
        "midias": [{"tipo": "imagem", "mime": "image/jpeg", "dados_base64": b64(PNG)}],
    })
    assert r.status_code == 400 and "não é image/jpeg" in r.json()["detail"]
    assert client.get("/tickets", headers=CHAVE).json() == []


def test_webhook_mais_midias_que_o_limite_retorna_400(client):
    m = {"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)}
    r = client.post("/webhook/mensagens", headers=CHAVE,
                    json={"canal": "chat", "midias": [m] * (midias.MAX_MIDIAS + 1)})
    assert r.status_code == 400


# ---------- download para o painel ----------
def test_baixar_midia_exige_chave_e_devolve_o_arquivo(client):
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "chat", "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)}],
    })
    tid = r.json()["ticket_id"]
    mid = client.get(f"/tickets/{tid}", headers=CHAVE).json()["midias"][0]["id"]

    assert client.get(f"/tickets/{tid}/midias/{mid}").status_code == 401
    arq = client.get(f"/tickets/{tid}/midias/{mid}", headers=CHAVE)
    assert arq.status_code == 200 and arq.content == PNG
    assert arq.headers["content-type"] == "image/png"
    assert "sandbox" in arq.headers["content-security-policy"]
    assert client.get(f"/tickets/{tid + 1}/midias/{mid}", headers=CHAVE).status_code == 404  # mídia de outro ticket


# ---------- mídia + conversa (ADR-016 e ADR-017) ----------
def test_audio_que_abre_o_ticket_aparece_transcrito_na_conversa(client, monkeypatch):
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: "Meu boleto não gera.")
    r = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "conversa_id": "5511999990001",
        "midias": [{"tipo": "audio", "mime": "audio/ogg", "dados_base64": b64(OGG)}],
    }).json()
    [msg] = client.get(f"/tickets/{r['ticket_id']}/mensagens", headers=CHAVE).json()
    assert msg["texto"] == "[Áudio transcrito pela IA]: Meu boleto não gera."


def test_foto_na_continuacao_da_conversa_fica_no_ticket_e_na_mensagem(client, monkeypatch):
    # Arrange: a conversa já existe e foi classificada pelo texto
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: "Print com 'cartão recusado'.")
    a = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "conversa_id": "5511999990002", "texto": "meu cartão foi recusado"}).json()
    triagem_antes = client.get(f"/tickets/{a['ticket_id']}", headers=CHAVE).json()
    # Act: o cliente manda uma foto na mesma conversa
    b = client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "whatsapp", "conversa_id": "5511999990002", "texto": "olha o erro",
        "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)}]}).json()
    # Assert: anexada ao mesmo ticket, a foto lida vai para a mensagem e a triagem não muda
    assert b == {"ticket_id": a["ticket_id"], "status": "anexada"}
    t = client.get(f"/tickets/{a['ticket_id']}", headers=CHAVE).json()
    assert [m["status"] for m in t["midias"]] == ["lido"]
    assert t["texto"] == "meu cartão foi recusado" and t["assunto"] == triagem_antes["assunto"]
    conversa = client.get(f"/tickets/{a['ticket_id']}/mensagens", headers=CHAVE).json()
    assert conversa[-1]["texto"] == "olha o erro\n\n[Foto descrita pela IA]: Print com 'cartão recusado'."


# ---------- imagem e áudio na resposta do atendente (chat) ----------
def _ticket_do_chat(client):
    return client.post("/webhook/mensagens", headers=CHAVE, json={
        "canal": "chat", "texto": "Meu Pix não caiu", "conversa_id": "cli-resp"}).json()["ticket_id"]


def test_atendente_envia_imagem_e_audio_no_chat(client, monkeypatch):
    chamou_ia = []
    monkeypatch.setattr(midias, "ler_com_ia", lambda m, s=None, c=None: chamou_ia.append(m) or "x")
    tid = _ticket_do_chat(client)
    r = client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={
        "texto": "Veja o passo a passo", "autor": "Bia",
        "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)},
                   {"tipo": "audio", "mime": "audio/webm", "dados_base64": b64(WEBM)}],
    })
    assert r.status_code == 201
    assert [m["tipo"] for m in r.json()["midias"]] == ["imagem", "audio"]

    msgs = client.get(f"/tickets/{tid}/mensagens", headers=CHAVE).json()
    saida = msgs[-1]
    assert saida["direcao"] == "saida" and saida["texto"] == "Veja o passo a passo"
    img, aud = saida["midias"]
    arq = client.get(f"/tickets/{tid}/midias/{img['id']}", headers=CHAVE)
    assert arq.status_code == 200 and arq.content == PNG
    assert msgs[0]["midias"] == []  # a mensagem do cliente não tem mídia

    t = client.get(f"/tickets/{tid}", headers=CHAVE).json()
    assert t["midias"] == []  # mídia do atendente não aparece como mídia do cliente nem vai para a IA
    assert t["first_response_at"] is not None  # conta como 1ª resposta (SLA)
    assert not chamou_ia


def test_atendente_envia_so_imagem_e_a_mensagem_ganha_rotulo(client):
    tid = _ticket_do_chat(client)
    r = client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={
        "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(PNG)}]})
    assert r.status_code == 201 and r.json()["texto"] == "📷 Imagem"


def test_resposta_sem_texto_e_sem_midia_retorna_400(client):
    tid = _ticket_do_chat(client)
    assert client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={"texto": "  "}).status_code == 400


def test_resposta_com_midia_invalida_retorna_400_e_nao_grava(client):
    tid = _ticket_do_chat(client)
    r = client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={
        "midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": b64(OGG)}]})
    assert r.status_code == 400
    msgs = client.get(f"/tickets/{tid}/mensagens", headers=CHAVE).json()
    assert [m for m in msgs if m["direcao"] == "saida" and m["autor"] != tickets.AUTOR_IA] == []  # só o aviso automático
