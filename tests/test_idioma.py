"""Idioma do cliente (ADR-015): detecção, resposta no mesmo idioma, plano B multilíngue e persistência."""
import json

import pytest

from conftest import CHAVE
from test_classifier import VALIDO, cliente_http, ok, settings
from triagem import classifier, metrics
from triagem.domain import Classificacao
from triagem.fallback import classificar_por_regras
from triagem.idioma import detectar, normalizar_codigo

EN = "My card payments are all being declined and I am losing sales!"
RESPOSTA_EN = "Hello! We are already checking the problem with your payment and will get back to you soon."
RESPOSTA_PT = "Olá! Já estamos verificando o problema com o seu pagamento e retornaremos em breve."


# ---------- detecção local ----------
@pytest.mark.parametrize("texto, codigo", [
    ("Meu Pix não funciona, estou perdendo vendas!", "pt"),
    ("My payment is not working and I am losing sales", "en"),
    ("Mi pago no funciona, estoy perdiendo ventas", "es"),
    ("Mon paiement ne fonctionne pas, je suis bloqué", "fr"),
    ("Il pagamento non funziona, non riesco a vendere", "it"),
    ("Meine Zahlung funktioniert nicht", "de"),
])
def test_detecta_os_idiomas_suportados_com_sinal_forte(texto, codigo):
    d = detectar(texto)
    assert d.codigo == codigo and d.forte


def test_texto_sem_sinais_assume_portugues_sem_forca():
    for texto in ("ok", "???", "123"):
        d = detectar(texto)
        assert (d.codigo, d.forte) == ("pt", False)


def test_mensagens_rotuladas_em_portugues_nao_viram_outro_idioma():
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / "data"
    msgs = json.loads((raiz / "avaliacao.json").read_text(encoding="utf-8"))
    msgs += json.loads((raiz / "mensagens_demo.json").read_text(encoding="utf-8"))
    assert [m["texto"] for m in msgs if detectar(m["texto"]).codigo != "pt"] == []


@pytest.mark.parametrize("valor, esperado", [
    ("pt-BR", "pt"), ("EN", "en"), ("es_419", "es"), ("Português", "pt"), ("english", "en"),
    ("klingon", ""), ("", ""), (None, ""), ("e", ""),
])
def test_normaliza_o_codigo_do_idioma(valor, esperado):
    assert normalizar_codigo(valor) == esperado


def test_idioma_ilegivel_nao_invalida_a_classificacao():
    c = Classificacao.model_validate({**VALIDO, "idioma": "???"})
    assert c.idioma == ""


# ---------- LLM ----------
def test_cliente_em_ingles_recebe_resposta_em_ingles():
    http, chamadas = cliente_http(ok({**VALIDO, "idioma": "en", "resposta_sugerida": RESPOSTA_EN}))
    c = classifier.classificar(EN, settings(), http)
    assert (c.origem, c.idioma, c.prompt_version) == ("llm", "en", classifier.PROMPT_VERSION)
    sistema = json.loads(chamadas[0].content)["messages"][0]["content"]
    assert '"idioma"' in sistema and "MESMO IDIOMA" in sistema


def test_resposta_em_outro_idioma_e_recusada_e_cai_no_plano_b_no_idioma_certo():
    errada = ok({**VALIDO, "idioma": "en", "resposta_sugerida": RESPOSTA_PT})
    http, chamadas = cliente_http(errada, errada)
    c = classifier.classificar(EN, settings(), http)
    assert len(chamadas) == 2  # tentou de novo antes de desistir
    assert c.origem == "fallback" and c.idioma == "en"
    assert detectar(c.resposta_sugerida).codigo == "en"


def test_sem_idioma_na_resposta_do_llm_usa_a_deteccao_local():
    http, _ = cliente_http(ok({**VALIDO, "resposta_sugerida": RESPOSTA_EN}))
    assert classifier.classificar(EN, settings(), http).idioma == "en"


def test_deteccao_local_forte_corrige_idioma_errado_do_llm():
    http, _ = cliente_http(ok({**VALIDO, "idioma": "pt", "resposta_sugerida": RESPOSTA_EN}))
    assert classifier.classificar(EN, settings(), http).idioma == "en"


def test_texto_curto_mantem_o_idioma_dito_pelo_llm():
    http, _ = cliente_http(ok({**VALIDO, "idioma": "en", "resposta_sugerida": "Hello! Glad to hear it, thank you!"}))
    assert classifier.classificar("thx!", settings(), http).idioma == "en"


# ---------- plano B ----------
@pytest.mark.parametrize("texto, idioma, assunto", [
    ("I forgot my password and cannot log in", "en", "acesso"),
    ("No puedo pagar con mi tarjeta, el pago no funciona", "es", "pagamento"),
    ("Meu Pix não funciona, estou perdendo vendas!", "pt", "pagamento"),
])
def test_plano_b_responde_no_idioma_do_cliente(texto, idioma, assunto):
    c = classificar_por_regras(texto)
    assert (c.idioma, c.assunto) == (idioma, assunto)
    assert detectar(c.resposta_sugerida).codigo == idioma


def test_plano_b_usa_ingles_para_idioma_sem_resposta_pronta():
    c = classificar_por_regras("Meine Zahlung funktioniert nicht, bitte helfen Sie mir")
    assert c.idioma == "de" and detectar(c.resposta_sugerida).codigo == "en"


# ---------- persistência, API e métricas ----------
def test_idioma_e_salvo_exposto_e_contado(client):
    r = client.post("/webhook/mensagens", json={"canal": "chat", "texto": "I forgot my password and cannot log in"},
                    headers=CHAVE)
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["idioma"] == "en" and detectar(t["resposta_sugerida"]).codigo == "en"
    client.post("/webhook/mensagens", json={"canal": "chat", "texto": "Meu Pix não funciona!"}, headers=CHAVE)
    assert {i["idioma"]: i["total"] for i in metrics.idiomas()} == {"en": 1, "pt": 1}
    assert client.get("/dominio", headers=CHAVE).json()["idiomas"]["en"] == "inglês"
