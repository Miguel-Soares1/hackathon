"""Cliente simulado pela IA nas telas /demo (sem rede: o LLM é simulado com httpx.MockTransport)."""
import json
from dataclasses import replace

import httpx

from triagem import cliente_simulado as cs
from triagem.config import get_settings


def _settings():
    return replace(get_settings(), deepseek_api_key="chave-de-teste")


def _llm(conteudo, chamadas=None, status=200):
    def handler(request):
        if chamadas is not None:
            chamadas.append(json.loads(request.content))
        corpo = {"choices": [{"message": {"content": conteudo}}]}
        return httpx.Response(status, json=corpo)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_primeira_fala_do_email_vem_do_llm_com_assunto():
    # Arrange
    conv = cs.Conversa("email", "pix", "Mariana Souza", "mariana@exemplo.com")
    chamadas = []
    resposta = json.dumps({"mensagem": "Olá, meu Pix não caiu.", "assunto": "Pix pendente", "encerrou": False})
    # Act
    fala = cs.proxima_fala(conv, _settings(), _llm(resposta, chamadas))
    # Assert
    assert fala == {"mensagem": "Olá, meu Pix não caiu.", "assunto": "Pix pendente", "encerrou": False}
    sistema = chamadas[0]["messages"][0]["content"]
    assert "Mariana Souza" in sistema and "e-mail" in sistema


def test_fala_seguinte_leva_a_conversa_e_ignora_assunto_fora_do_primeiro_email():
    conv = cs.Conversa("whatsapp", "cobranca", "Carlos Lima", "5521998761234",
                       historico=[("cliente", "fui cobrado 2x"), ("atendente", "Qual o final do cartão?")])
    chamadas = []
    fala = cs.proxima_fala(conv, _settings(), _llm(json.dumps({"mensagem": "4321", "assunto": "x", "encerrou": True}), chamadas))
    assert fala == {"mensagem": "4321", "assunto": None, "encerrou": True}
    usuario = chamadas[0]["messages"][1]["content"]
    assert "CLIENTE: fui cobrado 2x" in usuario and "ATENDENTE: Qual o final do cartão?" in usuario


def test_llm_fora_do_ar_ou_json_invalido_cai_no_roteiro():
    conv = cs.Conversa("instagram", "app", "@joaop", "joaop")
    assert cs.proxima_fala(conv, _settings(), _llm("", status=500))["mensagem"] == cs.CENARIOS["app"][2][0]
    assert cs.proxima_fala(conv, _settings(), _llm("não é json"))["mensagem"] == cs.CENARIOS["app"][2][0]
    assert cs.proxima_fala(conv, _settings(), _llm(json.dumps({"mensagem": ""})))["mensagem"] == cs.CENARIOS["app"][2][0]


def test_conversa_longa_e_encerrada_pelo_cliente():
    conv = cs.Conversa("whatsapp", "pix", "Ana", "5531991234567",
                       historico=[("cliente", "msg")] * cs.MAX_MENSAGENS_CLIENTE)
    assert cs.proxima_fala(conv, _settings(), _llm("{}")) == {"mensagem": cs.DESPEDIDA, "assunto": None, "encerrou": True}


def test_cenario_desconhecido_e_sorteado_e_clientes_ativos_nao_se_repetem():
    conversas = cs.Conversas()
    contatos = set()
    for _ in range(len(cs.PESSOAS["whatsapp"])):
        _, conv = conversas.nova("whatsapp", "nao-existe")
        assert conv.cenario in cs.CENARIOS
        contatos.add(conv.contato)
    assert len(contatos) == len(cs.PESSOAS["whatsapp"])
