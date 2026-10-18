"""Atendimento automático (ADR-022): a IA resolve ou encaminha para a equipe, sempre avisando o cliente."""
from datetime import timedelta

import pytest
from sqlalchemy import text

from conftest import CHAVE
from triagem import atendimento_ia, pipeline, tickets
from triagem.classifier import LLMError
from triagem.db import utcnow
from triagem.domain import Classificacao

IA = tickets.AUTOR_IA


def _classificacao(urgencia, origem="llm"):
    return Classificacao(assunto="duvida", urgencia=urgencia, sentimento="neutro", equipe="atendimento",
                         resposta_sugerida=f"Olá! Resposta da triagem ({urgencia}).", idioma="pt",
                         confianca={"assunto": 0.9, "urgencia": 0.9, "sentimento": 0.9, "equipe": 0.9}, origem=origem)


@pytest.fixture
def ia(monkeypatch, db):
    """Atendimento automático ligado, com triagem e decisões da IA simuladas: `acao` diz se ela resolve ou encaminha."""
    with db.begin() as conn:
        conn.execute(text("UPDATE app_config SET valor = '1' WHERE chave = 'ia_auto_ativo'"))
    estado = {"urgencia": "baixa", "origem": "llm", "falhar": False, "chamadas": 0, "acao": "resolver"}

    def classificar(texto, exemplos=()):
        return _classificacao(estado["urgencia"], estado["origem"])

    def atender(conversa, triagem=None):
        estado["chamadas"] += 1
        if estado["falhar"]:
            raise LLMError("fora do ar")
        if estado["acao"] == "encaminhar":
            return "encaminhar", "", estado.get("equipe")
        return "resolver", f"Resposta da IA para: {conversa[-1][1]}", None
    monkeypatch.setattr(pipeline, "classificar", classificar)
    monkeypatch.setattr(atendimento_ia, "atender", atender)
    return estado


def _post(client, texto, conversa="5511900000001", **kw):
    corpo = {"canal": "whatsapp", "cliente": "Cliente IA", "conversa_id": conversa, "texto": texto, **kw}
    return client.post("/webhook/mensagens", headers=CHAVE, json=corpo).json()


def _conversa(tid):
    return [(m["direcao"], m["autor"], m["texto"]) for m in tickets.mensagens(tid)]


def _encaminhado(tid):
    """A última fala é o aviso automático de encaminhamento e o prazo segue até uma pessoa responder."""
    direcao, autor, texto = _conversa(tid)[-1]
    return direcao == "saida" and autor == IA and ("Encaminhei" in texto or "forwarded" in texto)


def test_urgencia_baixa_a_ia_responde_sozinha(client, ia):
    tid = _post(client, "como faço para trocar meu e-mail de cadastro?")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "ia" and t["ia_atendendo"] and not t["aguardando"]
    assert _conversa(tid)[-1] == ("saida", IA, "Resposta da IA para: como faço para trocar meu e-mail de cadastro?")
    assert t["first_response_at"] is not None  # o cliente foi respondido


@pytest.mark.parametrize("urgencia", ["alta", "critica"])
def test_urgencia_alta_e_critica_sao_encaminhadas_para_a_equipe(client, ia, urgencia):
    ia["urgencia"] = urgencia
    tid = _post(client, "o sistema caiu e não consigo vender")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["aguardando"] and not t["ia_atendendo"]
    assert _encaminhado(tid) and "com prioridade" in _conversa(tid)[-1][2] and "equipe de atendimento" in _conversa(tid)[-1][2]
    assert t["first_response_at"] is None and ia["chamadas"] == 0  # o prazo segue correndo; nem perguntou ao modelo


def test_triagem_pelo_plano_b_vai_para_um_atendente(client, ia):
    ia["origem"] = "fallback"
    tid = _post(client, "dúvida simples")["ticket_id"]
    assert tickets.obter(tid)["modo"] == "humano"


def test_ia_responde_cada_nova_mensagem_com_a_conversa(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    _post(client, "e onde fica esse menu?")
    assert _conversa(tid)[-1] == ("saida", IA, "Resposta da IA para: e onde fica esse menu?")
    assert tickets.obter(tid)["ia_atendendo"]


@pytest.mark.parametrize("pedido", ["quero falar com um atendente", "prefiro uma pessoa de verdade", "can I talk to a human?"])
def test_cliente_que_pede_uma_pessoa_vai_para_o_atendente(client, ia, pedido):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    _post(client, pedido)
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["escalado_em"] and "pessoa" in t["motivo_escalada"]
    assert t["aguardando"]  # volta para Em espera até uma pessoa responder
    assert _encaminhado(tid)
    # a pessoa responde e o atendimento sai da fila
    client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={"texto": "Oi, sou a Joana, vou te ajudar.", "autor": "Joana"})
    assert not tickets.obter(tid)["aguardando"]


def test_atendimento_longo_da_ia_vai_para_o_atendente(client, ia, db):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    with db.begin() as conn:  # a conversa começou há 20 minutos (limite padrão: 15)
        conn.execute(text("UPDATE tickets SET received_at = :q WHERE id = :id"), {"q": utcnow() - timedelta(minutes=20), "id": tid})
    _post(client, "ainda não consegui")
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and "15 min" in t["motivo_escalada"]


def test_muitas_respostas_da_ia_vao_para_o_atendente(client, ia, db):
    with db.begin() as conn:
        conn.execute(text("INSERT INTO app_config (chave, valor) VALUES ('ia_max_respostas', '2') "
                          "ON DUPLICATE KEY UPDATE valor = VALUES(valor)"))
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]   # resposta 1 (triagem)
    _post(client, "não achei")                                                # resposta 2
    _post(client, "continua sem aparecer")                                    # limite: vai para a pessoa
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and "2 vezes" in t["motivo_escalada"]


def test_ia_que_falha_passa_para_o_atendente(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    ia["falhar"] = True
    _post(client, "e agora?")
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and "não conseguiu" in t["motivo_escalada"] and t["aguardando"]
    assert ia["chamadas"] == 3  # 1ª resposta + duas tentativas antes de encaminhar


def test_atendente_que_responde_assume_a_conversa_da_ia(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={"texto": "Deixa comigo!", "autor": "Joana"})
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["motivo_escalada"] == "assumido por Joana"
    chamadas = ia["chamadas"]
    _post(client, "obrigado!")
    assert ia["chamadas"] == chamadas or _conversa(tid)[-1][1] != IA  # a IA não responde mais


def test_ninguem_assina_como_a_ia(client, ia):
    ia["urgencia"] = "alta"
    tid = _post(client, "sistema fora do ar")["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", headers=CHAVE, json={"texto": "oi", "autor": IA})
    assert _conversa(tid)[-1][1] == "Atendente" and not tickets.obter(tid)["aguardando"]


def test_desligado_na_configuracao_tudo_vai_para_atendente(client, ia, db):
    with db.begin() as conn:
        conn.execute(text("INSERT INTO app_config (chave, valor) VALUES ('ia_auto_ativo', '0') "
                          "ON DUPLICATE KEY UPDATE valor = VALUES(valor)"))
    tid = _post(client, "dúvida simples")["ticket_id"]
    assert tickets.obter(tid)["modo"] == "humano"


def test_correcao_da_urgencia_para_alta_tira_a_conversa_da_ia(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    assert tickets.obter(tid)["modo"] == "ia"
    r = client.post(f"/tickets/{tid}/correcoes", headers=CHAVE, json={"urgencia": "alta", "equipe": "financeiro"})
    assert r.status_code == 201 and r.json()["escalado"] is True
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and "corrigida para alta" in t["motivo_escalada"] and t["aguardando"]
    assert t["urgencia"] == "alta" and t["equipe"] == "financeiro"


def test_correcao_que_mantem_urgencia_baixa_nao_muda_quem_atende(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    r = client.post(f"/tickets/{tid}/correcoes", headers=CHAVE, json={"assunto": "cobranca", "urgencia": "media"})
    assert r.json()["escalado"] is False and tickets.obter(tid)["modo"] == "ia"


@pytest.mark.parametrize("mensagem", ["tudo parou de funcionar, não estou aguentando mais e quero cancelar",
                                      "vou reclamar no Procon", "resolvam isso imediatamente"])
def test_cliente_ameacando_sair_vai_direto_para_um_atendente(client, ia, mensagem):
    tid = _post(client, mensagem)["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["aguardando"] and t["motivo_escalada"]
    assert _encaminhado(tid) and ia["chamadas"] == 0  # avisa e encaminha, sem tentar contornar


@pytest.mark.parametrize("mensagem", ["eu quero que vocês consertem isso agora", "I'm going to cancel everything"])
def test_cliente_que_exige_solucao_ou_ameaca_cancelar_no_meio_da_conversa_vai_para_o_atendente(client, ia, mensagem):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]
    _post(client, mensagem)
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["aguardando"] and t["motivo_escalada"].startswith("o cliente")
    assert _encaminhado(tid)  # avisou o cliente em vez de pedir mais detalhes
    assert _conversa(tid)[-2][2] == mensagem  # logo depois da ameaça, só o aviso: não contornou o pedido


def test_pedido_de_cancelamento_e_retencao_e_fica_com_uma_pessoa(client, ia, monkeypatch):
    def classificar(texto, exemplos=()):
        return _classificacao("media").model_copy(update={"assunto": "cancelamento", "equipe": "retencao"})
    monkeypatch.setattr(pipeline, "classificar", classificar)
    tid = _post(client, "gostaria de encerrar o meu plano no fim do mês")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["motivo_escalada"] == "pedido de cancelamento"


@pytest.mark.parametrize("mensagem", ["agora funcionou, obrigado", "e onde fica esse menu?", "já resolvi, valeu"])
def test_mensagens_comuns_continuam_com_a_ia(client, ia, mensagem):
    assert atendimento_ia.risco_de_perder_cliente(mensagem) is None


def test_ia_que_nao_consegue_resolver_encaminha_para_a_equipe_da_triagem(client, ia, monkeypatch):
    def classificar(texto, exemplos=()):
        return _classificacao("media").model_copy(update={"assunto": "cobranca", "equipe": "financeiro"})
    monkeypatch.setattr(pipeline, "classificar", classificar)
    ia["acao"] = "encaminhar"
    tid = _post(client, "fui cobrado duas vezes este mês")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["aguardando"] and t["equipe"] == "financeiro"
    assert _encaminhado(tid) and "equipe financeira" in _conversa(tid)[-1][2]
    assert "precisa da equipe" in t["motivo_escalada"] and t["first_response_at"] is None
    _post(client, "alguma novidade?")  # já está com a equipe: a IA não responde mais
    assert _conversa(tid)[-1][0] == "entrada" and ia["chamadas"] == 1


def test_aviso_de_encaminhamento_sai_no_idioma_do_cliente():
    assert "billing team" in atendimento_ia.aviso_encaminhado("financeiro", "en")
    assert "soporte técnico" in atendimento_ia.aviso_encaminhado("suporte_tecnico", "es", urgente=True)
    assert "engineering team" in atendimento_ia.aviso_encaminhado("engenharia", "fr")  # sem texto pronto: inglês
    assert "nossa equipe de relacionamento" in atendimento_ia.aviso_encaminhado("retencao", "pt")


def test_problema_que_muda_na_conversa_vai_para_a_equipe_certa(client, ia):
    tid = _post(client, "como emito a segunda via do boleto?")["ticket_id"]   # dúvida: a IA resolve
    ia.update(acao="encaminhar", equipe="engenharia")
    _post(client, "fiz isso e dá erro 500 na tela")
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["equipe"] == "engenharia"
    assert _encaminhado(tid) and "equipe técnica" in _conversa(tid)[-1][2]
