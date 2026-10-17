import pytest

from conftest import CHAVE
from triagem import corrections

MSG = {"canal": "chat", "texto": "Meu Pix não funciona, estou perdendo vendas!"}


def novo_ticket(client, **extra):
    return client.post("/webhook/mensagens", json={**MSG, **extra}, headers=CHAVE).json()["ticket_id"]


def test_correcao_atualiza_valor_efetivo_e_preserva_a_predicao_original(client):
    tid = novo_ticket(client)
    r = client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "Média"}, headers=CHAVE)
    assert r.status_code == 201
    t = client.get(f"/tickets/{tid}", headers=CHAVE).json()
    assert t["urgencia"] == "media" and t["urgencia_original"] == "critica"
    assert t["revisado"] is True


def test_correcao_de_urgencia_recalcula_o_prazo(client):
    tid = novo_ticket(client)
    antes = client.get(f"/tickets/{tid}", headers=CHAVE).json()["sla"]["prazo_minutos"]
    client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "baixa"}, headers=CHAVE)
    depois = client.get(f"/tickets/{tid}", headers=CHAVE).json()["sla"]["prazo_minutos"]
    assert (antes, depois) == (15, 1440)


def test_valor_invalido_retorna_400_e_nao_grava(client):
    tid = novo_ticket(client)
    r = client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "urgentíssima"}, headers=CHAVE)
    assert r.status_code == 400
    assert client.get("/correcoes", headers=CHAVE).json() == []


def test_correcao_vazia_retorna_400(client):
    tid = novo_ticket(client)
    assert client.post(f"/tickets/{tid}/correcoes", json={}, headers=CHAVE).status_code == 400


def test_correcao_para_o_mesmo_valor_nao_gera_registro(client):
    tid = novo_ticket(client)
    r = client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "critica"}, headers=CHAVE)
    assert r.status_code == 201 and r.json()["correcoes_registradas"] == []


def test_historico_registra_original_e_corrigido(client):
    tid = novo_ticket(client)
    client.post(f"/tickets/{tid}/correcoes", json={"assunto": "instabilidade"}, headers=CHAVE)
    h = client.get("/correcoes", params={"ticket_id": tid}, headers=CHAVE).json()
    assert len(h) == 1
    assert (h[0]["dimensao"], h[0]["valor_original"], h[0]["valor_corrigido"]) == ("assunto", "pagamento", "instabilidade")


def test_confirmar_revisao_conta_como_acerto(client):
    tid = novo_ticket(client)
    assert client.post(f"/tickets/{tid}/revisao", headers=CHAVE).status_code == 204
    p = corrections.precisao()
    assert p["revisados"] == 1 and p["agregado"] == 100.0


def test_taxa_de_acerto_por_dimensao_e_agregado(client):
    # 4 tickets revisados: 1 confirmado, 3 com correções
    ids = [novo_ticket(client) for _ in range(4)]
    client.post(f"/tickets/{ids[0]}/revisao", headers=CHAVE)
    client.post(f"/tickets/{ids[1]}/correcoes", json={"urgencia": "alta"}, headers=CHAVE)
    client.post(f"/tickets/{ids[2]}/correcoes", json={"urgencia": "alta", "assunto": "cobranca"}, headers=CHAVE)
    client.post(f"/tickets/{ids[3]}/correcoes", json={"sentimento": "neutro"}, headers=CHAVE)

    p = corrections.precisao()

    assert p["revisados"] == 4
    assert p["por_dimensao"]["urgencia"] == 50.0   # 2 erros em 4
    assert p["por_dimensao"]["assunto"] == 75.0    # 1 erro em 4
    assert p["por_dimensao"]["sentimento"] == 75.0
    assert p["por_dimensao"]["equipe"] == 100.0
    assert p["agregado"] == 75.0                   # 4 erros em 16 verificações (4 tickets x 4 dimensões)


def test_corrigir_de_volta_ao_valor_original_deixa_de_contar_como_erro(client):
    tid = novo_ticket(client)
    client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "alta"}, headers=CHAVE)
    client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "critica"}, headers=CHAVE)
    assert corrections.precisao()["por_dimensao"]["urgencia"] == 100.0


def test_precisao_separa_llm_de_fallback(client):
    tid = novo_ticket(client)  # origem fallback (sem chave do LLM)
    client.post(f"/tickets/{tid}/correcoes", json={"urgencia": "alta"}, headers=CHAVE)
    assert corrections.precisao("fallback")["revisados"] == 1
    assert corrections.precisao("llm")["revisados"] == 0
    assert corrections.precisao("llm")["agregado"] is None


def test_sem_revisoes_a_precisao_e_nula(client):
    assert corrections.precisao()["agregado"] is None


def test_calcular_precisao_pura():
    r = corrections.calcular_precisao(10, {"urgencia": 2, "assunto": 1})
    assert r["por_dimensao"]["urgencia"] == 80.0
    assert r["agregado"] == 92.5  # 1 - 3/(10*4)


def test_resposta_sugerida_editada_nao_entra_no_agregado(client):
    tid = novo_ticket(client)
    client.post(f"/tickets/{tid}/correcoes", json={"resposta_sugerida": "Resposta nova e melhor."}, headers=CHAVE)
    p = corrections.precisao()
    assert p["por_dimensao"]["resposta_sugerida"] == 0.0
    assert p["agregado"] == 100.0


@pytest.mark.parametrize("dim", ["assunto", "urgencia", "sentimento", "equipe"])
def test_valor_fora_do_conjunto_e_rejeitado_em_cada_dimensao(client, dim):
    tid = novo_ticket(client)
    assert client.post(f"/tickets/{tid}/correcoes", json={dim: "inexistente"}, headers=CHAVE).status_code == 400
