"""Central de Triagem: justificativa da urgência, números do dia, resumo da IA e nome do incidente."""
import json
from dataclasses import replace
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import bindparam, text

from conftest import CHAVE
from test_incidents import com_embedder, inserir_ticket
from triagem import incidents, metrics, pipeline, resumo_ia
from triagem.config import get_settings
from triagem.domain import Classificacao
from triagem.fallback import classificar_por_regras


def settings(chave="k"):
    return replace(get_settings(), deepseek_api_key=chave, deepseek_base_url="https://api.exemplo.test",
                   deepseek_model="modelo", llm_timeout=5.0)


def cliente_http(*conteudos):
    """Cliente httpx falso: cada chamada devolve o próximo conteúdo (dict vira JSON; int vira status de erro)."""
    fila, chamadas = list(conteudos), []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(json.loads(request.content))
        c = fila.pop(0)
        if isinstance(c, int):
            return httpx.Response(c)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(c)}}]})

    return httpx.Client(transport=httpx.MockTransport(handler)), chamadas


@pytest.fixture(autouse=True)
def _sem_cache():
    resumo_ia.limpar_cache()
    yield
    resumo_ia.limpar_cache()


# ---------- "Por que essa prioridade?" ----------
def test_plano_b_explica_a_urgencia_pelo_termo_encontrado():
    c = classificar_por_regras("Meu Pix não funciona, estou perdendo vendas!")
    assert c.urgencia == "critica" and "“perdendo”" in c.justificativa and c.justificativa.startswith("Plano B")


def test_plano_b_sem_sinal_de_urgencia_diz_isso():
    assert "nenhum sinal" in classificar_por_regras("bom dia, tudo bem com vocês?").justificativa


def test_justificativa_do_llm_e_tolerante():
    base = {"assunto": "pagamento", "urgencia": "alta", "sentimento": "negativo", "equipe": "financeiro",
            "resposta_sugerida": "Olá!", "confianca": {"assunto": 1, "urgencia": 1, "sentimento": 1, "equipe": 1}}
    assert Classificacao.model_validate(base).justificativa == ""  # ausente: não invalida a classificação
    assert Classificacao.model_validate({**base, "justificativa": 42}).justificativa == ""
    longa = Classificacao.model_validate({**base, "justificativa": "palavra " * 100}).justificativa
    assert len(longa) == 300 and longa.endswith("…")


def test_justificativa_vai_para_o_ticket(client):
    r = client.post("/webhook/mensagens", headers=CHAVE,
                    json={"canal": "chat", "cliente": "Loja", "texto": "Pix fora do ar, estou perdendo vendas agora"})
    t = client.get(f"/tickets/{r.json()['ticket_id']}", headers=CHAVE).json()
    assert t["origem"] == "fallback" and t["justificativa"].startswith("Plano B") and t["classified_at"]


# ---------- números do dia ----------
def test_triagem_hoje_conta_ia_e_plano_b_e_mede_o_tempo(db):
    agora = datetime(2026, 10, 18, 15, 0, 0)  # 12h em Brasília
    with db.begin() as conn:
        for i, (origem, atraso, quando) in enumerate([("llm", 2, agora), ("llm", 4, agora), ("fallback", 6, agora),
                                                     ("llm", 9, agora - timedelta(days=1))]):
            tid = conn.execute(text(
                "INSERT INTO tickets (canal, texto, status, received_at, created_at) "
                "VALUES ('chat', 'x', 'classificado', :q, :q)"), {"q": quando}).lastrowid
            conn.execute(text(
                "INSERT INTO classifications (ticket_id, assunto, urgencia, sentimento, equipe, resposta_sugerida, "
                "conf_assunto, conf_urgencia, conf_sentimento, conf_equipe, origem, classified_at) "
                "VALUES (:t, 'duvida', 'baixa', 'neutro', 'atendimento', 'ok', 1, 1, 1, 1, :o, :c)"),
                {"t": tid, "o": origem, "c": quando + timedelta(seconds=atraso)})
    r = metrics.triagem_hoje(agora)
    assert r == {"triadas_hoje": 3, "triadas_ia_hoje": 2, "plano_b_hoje": 1, "tempo_medio_s": 4.0}


def test_hoje_comeca_a_meia_noite_de_brasilia():
    assert metrics.inicio_do_dia(datetime(2026, 10, 18, 2, 0)) == datetime(2026, 10, 17, 3, 0)
    assert metrics.inicio_do_dia(datetime(2026, 10, 18, 3, 0)) == datetime(2026, 10, 18, 3, 0)


# ---------- resumo da IA ----------
def test_resumo_sem_chave_usa_regras_com_os_numeros(client):
    client.post("/webhook/mensagens", headers=CHAVE,
                json={"canal": "chat", "cliente": "Loja", "texto": "Pix fora do ar, estou perdendo vendas agora"})
    r = client.get("/resumo-ia", headers=CHAVE)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["origem"] == "regras" and "1 crítica(s) aguardando resposta" in corpo["texto"]
    assert "1 mensagem(ns) triada(s) hoje" in corpo["texto"]


def test_resumo_exige_chave(client):
    assert client.get("/resumo-ia").status_code == 401


def test_resumo_pelo_llm_fica_em_cache(db):
    http, chamadas = cliente_http({"resumo": "Tudo calmo por aqui."})
    s = settings()
    primeiro = resumo_ia.resumo_do_dia(s, http)
    segundo = resumo_ia.resumo_do_dia(s, http)
    assert primeiro["origem"] == "llm" and primeiro["texto"] == "Tudo calmo por aqui."
    assert segundo == primeiro and len(chamadas) == 1
    assert "<mensagem_do_cliente>" in chamadas[0]["messages"][1]["content"]  # números enviados como dado


def test_resumo_com_llm_fora_do_ar_cai_nas_regras(db):
    http, _ = cliente_http(500)
    r = resumo_ia.resumo_do_dia(settings(), http)
    assert r["origem"] == "regras" and "Fila zerada" in r["texto"]


def test_regras_comecam_pelo_incidente():
    f = {"incidentes_em_andamento": [{"titulo": "Falha no Pix", "clientes": 12, "desde": "14h00"}],
         "criticas_aguardando": 3, "altas_aguardando": 0, "prazos_estourados": 1, "aguardando_resposta": 9,
         "triadas_hoje": 40, "triadas_pela_ia_hoje": 38, "tempo_medio_triagem_segundos": 2.6}
    assert resumo_ia.resumo_por_regras(f) == (
        "12 clientes relatam falha no Pix desde 14h00. 3 crítica(s) aguardando resposta, 1 com prazo estourado. "
        "40 mensagem(ns) triada(s) hoje, 38 pela IA, em 3 s em média.")


# ---------- incidente: nome e "em andamento" ----------
def abrir_incidente(db, monkeypatch):
    com_embedder(monkeypatch)
    ids = [inserir_ticket(db, m, t) for m, t in [(20, "pix1"), (12, "pix2"), (3, "pix3")]]
    resultado = [incidents.registrar(i) for i in ids][-1]
    assert resultado["incidente"]
    return resultado["grupo_id"], ids


def test_incidente_com_cliente_em_aberto_esta_em_andamento(db, monkeypatch):
    gid, ids = abrir_incidente(db, monkeypatch)
    inc = incidents.listar_incidentes()[0]
    assert inc["ativo"] and inc["abertos"] == 3 and inc["titulo_ia"] is None
    with db.begin() as conn:
        conn.execute(text("UPDATE tickets SET desfecho = 'encerrado' WHERE id IN :ids")
                     .bindparams(bindparam("ids", expanding=True)), {"ids": ids})
    assert incidents.listar_incidentes()[0]["ativo"] is False


def test_ia_nomeia_o_incidente_uma_vez(db, monkeypatch):
    gid, _ = abrir_incidente(db, monkeypatch)
    http, chamadas = cliente_http({"titulo": "Falha no Pix", "resumo": "Clientes sem receber por Pix."})
    assert resumo_ia.nomear_incidente(gid, settings(), http) is True
    assert resumo_ia.nomear_incidente(gid, settings(), http) is False  # já tem nome: não chama de novo
    inc = incidents.listar_incidentes()[0]
    assert (inc["titulo_ia"], inc["resumo_ia"]) == ("Falha no Pix", "Clientes sem receber por Pix.")
    assert len(chamadas) == 1


def test_sem_chave_ou_com_erro_o_incidente_fica_sem_nome(db, monkeypatch):
    gid, _ = abrir_incidente(db, monkeypatch)
    assert resumo_ia.nomear_incidente(gid, settings(chave="")) is False
    http, _ = cliente_http(503)
    assert resumo_ia.nomear_incidente(gid, settings(), http) is False
    assert incidents.listar_incidentes()[0]["titulo_ia"] is None


def test_pipeline_nomeia_quando_o_incidente_abre(db, monkeypatch):
    nomeados = []
    monkeypatch.setattr(pipeline.incidents, "registrar", lambda tid: {"incidente": True, "grupo_id": 7})
    monkeypatch.setattr(pipeline.resumo_ia, "nomear_incidente", nomeados.append)
    with db.begin() as conn:
        tid = conn.execute(text("INSERT INTO tickets (canal, texto, received_at) VALUES ('chat', 'Pix caiu', NOW())")).lastrowid
    assert pipeline.processar_ticket(tid) == "classificado" and nomeados == [7]


def test_incidente_antigo_sem_nome_e_tentado_uma_vez_so():
    grupos = [{"id": 1, "ativo": True, "titulo_ia": None}, {"id": 2, "ativo": True, "titulo_ia": "Pix"},
              {"id": 3, "ativo": False, "titulo_ia": None}]
    assert resumo_ia.sem_nome(grupos) == [1]
    assert resumo_ia.sem_nome(grupos) == []  # falhou ou não: não chama o LLM a cada atualização do painel
