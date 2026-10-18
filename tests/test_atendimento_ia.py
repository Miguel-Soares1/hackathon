"""Atendimento pela IA (ADR-019): baixa e média a IA responde sozinha; alta e crítica vão para um atendente."""
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
def ia(monkeypatch):
    """Triagem e respostas da IA simuladas: a urgência vem do texto ("[alta] ...")."""
    estado = {"urgencia": "baixa", "origem": "llm", "falhar": False, "chamadas": 0}

    def classificar(texto, exemplos=()):
        return _classificacao(estado["urgencia"], estado["origem"])

    def sugerir(conversa, triagem=None):
        estado["chamadas"] += 1
        if estado["falhar"]:
            raise LLMError("fora do ar")
        return f"Resposta da IA para: {conversa[-1][1]}"
    monkeypatch.setattr(pipeline, "classificar", classificar)
    monkeypatch.setattr(pipeline, "sugerir_resposta", sugerir)
    monkeypatch.setattr(atendimento_ia, "sugerir_resposta", sugerir)
    return estado


def _post(client, texto, conversa="5511900000001", **kw):
    corpo = {"canal": "whatsapp", "cliente": "Cliente IA", "conversa_id": conversa, "texto": texto, **kw}
    return client.post("/webhook/mensagens", headers=CHAVE, json=corpo).json()


def _conversa(tid):
    return [(m["direcao"], m["autor"], m["texto"]) for m in tickets.mensagens(tid)]


def test_urgencia_baixa_a_ia_responde_sozinha(client, ia):
    tid = _post(client, "como faço para trocar meu e-mail de cadastro?")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "ia" and t["ia_atendendo"] and not t["aguardando"]
    assert _conversa(tid)[-1] == ("saida", IA, "Olá! Resposta da triagem (baixa).")
    assert t["first_response_at"] is not None  # o cliente foi respondido


@pytest.mark.parametrize("urgencia", ["alta", "critica"])
def test_urgencia_alta_e_critica_vao_para_um_atendente(client, ia, urgencia):
    ia["urgencia"] = urgencia
    tid = _post(client, "o sistema caiu e não consigo vender")["ticket_id"]
    t = tickets.obter(tid)
    assert t["modo"] == "humano" and t["aguardando"] and not t["ia_atendendo"]
    # A IA só avisa da transferência; o aviso não conta como 1ª resposta (o prazo segue para a pessoa).
    assert _conversa(tid) == [("entrada", "Cliente IA", "o sistema caiu e não consigo vender"),
                              ("saida", IA, atendimento_ia.TRANSFERENCIA_URGENTE["pt"])]
    assert t["first_response_at"] is None and t["sla"]["estado"] != "respondido"
    assert ia["chamadas"] == 0  # não gerou resposta pelo LLM


def test_atendente_responde_depois_do_aviso_de_transferencia(client, ia):
    ia["urgencia"] = "critica"
    tid = _post(client, "o sistema caiu e não consigo vender")["ticket_id"]
    client.post(f"/tickets/{tid}/mensagens", json={"texto": "Oi, sou a Bruna e já estou vendo.", "autor": "Bruna"},
                headers=CHAVE)
    t = tickets.obter(tid)
    assert not t["aguardando"] and t["first_response_at"] is not None


def test_triagem_pelo_plano_b_vai_para_um_atendente(client, ia):
    ia["origem"] = "fallback"
    tid = _post(client, "dúvida simples")["ticket_id"]
    assert tickets.obter(tid)["modo"] == "humano"
    assert [d for d, _, _ in _conversa(tid)] == ["entrada"]  # urgência baixa: sem aviso de transferência


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
    assert _conversa(tid)[-1][1] == IA and "transfer" in _conversa(tid)[-1][2].lower()
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
