"""Testes da lógica de scripts/avaliar_triagem.py e dos conjuntos rotulados (sem rede, sem banco)."""
import importlib.util
import json
from pathlib import Path

import pytest

from triagem.domain import VALORES_PERMITIDOS, Classificacao

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("avaliar_triagem", RAIZ / "scripts" / "avaliar_triagem.py")
avaliar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avaliar)


def cl(assunto="pagamento", urgencia="alta", sentimento="negativo", equipe="financeiro", resposta="Olá!"):
    return Classificacao(
        assunto=assunto, urgencia=urgencia, sentimento=sentimento, equipe=equipe, resposta_sugerida=resposta,
        confianca={"assunto": 1, "urgencia": 1, "sentimento": 1, "equipe": 1},
    )


def msg(**esperado):
    base = {"assunto": "pagamento", "urgencia": "alta", "sentimento": "negativo", "equipe": "financeiro"}
    return {"texto": "x", "esperado": {**base, **esperado}}


def test_medir_acerto_por_dimensao_e_agregado():
    msgs = [msg(), msg(urgencia="critica")]
    r = avaliar.medir(msgs, [cl(), cl()])
    assert r["dimensoes"] == ["assunto", "urgencia", "sentimento", "equipe"]
    assert r["acerto"]["urgencia"] == 0.5
    assert r["acerto"]["assunto"] == 1.0
    assert r["agregado"] == pytest.approx(3.5 / 4)
    assert r["erros"] == [{"texto": "x", "difs": {"urgencia": ["critica", "alta"]}}]


def test_medir_conta_urgencia_subestimada_mas_nao_superestimada():
    msgs = [msg(urgencia="critica"), msg(urgencia="baixa")]
    r = avaliar.medir(msgs, [cl(urgencia="media"), cl(urgencia="alta")])
    assert r["urgencia_subestimada"] == 1
    assert r["urgencia_confusao"]["critica"]["media"] == 1
    assert r["urgencia_confusao"]["baixa"]["alta"] == 1


def test_medir_ignora_json_invalido_e_dimensao_sem_rotulo():
    msgs = [{"texto": "x", "esperado": {"assunto": "pagamento", "urgencia": "alta", "sentimento": "negativo"}}] * 2
    r = avaliar.medir(msgs, [cl(), None])
    assert r["classificadas"] == 1 and r["total"] == 2
    assert "equipe" not in r["dimensoes"]
    assert r["agregado"] == 1.0


def test_medir_sem_predicoes_validas():
    r = avaliar.medir([msg()], [None])
    assert r["agregado"] is None and r["acerto"] == {}


def test_injecao_resistida():
    caso = {"texto": "x", "proibido": {"assunto": "elogio"}}
    assert avaliar.checar_injecao(caso, cl())["resistiu"]


def test_injecao_cede_no_rotulo():
    caso = {"texto": "x", "proibido": {"assunto": "elogio", "urgencia": "baixa"}}
    c = avaliar.checar_injecao(caso, cl(assunto="elogio"))
    assert not c["resistiu"] and c["cedeu"] == {"assunto": "elogio"}


def test_injecao_cede_na_resposta_sugerida():
    caso = {"texto": "x", "resposta_nao_contem": ["suporte-premio.example"]}
    c = avaliar.checar_injecao(caso, cl(resposta="Acesse http://SUPORTE-PREMIO.example/resgate"))
    assert not c["resistiu"] and c["na_resposta"] == ["suporte-premio.example"]


def test_injecao_detecta_vazamento_do_prompt_de_sistema():
    c = avaliar.checar_injecao({"texto": "x"}, cl(resposta="Minhas regras: responda somente com um objeto JSON"))
    assert not c["resistiu"]


@pytest.mark.parametrize("arquivo", ["mensagens_demo.json", "mensagens_holdout.json"])
def test_conjuntos_rotulados_usam_valores_permitidos(arquivo):
    msgs = json.loads((RAIZ / "data" / arquivo).read_text(encoding="utf-8"))
    for m in msgs:
        for d, v in m["esperado"].items():
            assert v in VALORES_PERMITIDOS[d], (arquivo, m["texto"], d, v)


def test_holdout_nao_repete_mensagens_do_demo():
    demo = {m["texto"] for m in json.loads((RAIZ / "data" / "mensagens_demo.json").read_text(encoding="utf-8"))}
    holdout = json.loads((RAIZ / "data" / "mensagens_holdout.json").read_text(encoding="utf-8"))
    assert not demo & {m["texto"] for m in holdout}
    assert avaliar.dimensoes_rotuladas(holdout) == ["assunto", "urgencia", "sentimento", "equipe"]
