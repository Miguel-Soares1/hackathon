from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import text

from conftest import CHAVE
from triagem import incidents
from triagem.embeddings import HashEmbedder, de_bytes, para_bytes

T0 = datetime(2026, 10, 17, 12, 0, 0)


def unit(*v):
    a = np.array(v, dtype=np.float32)
    return a / np.linalg.norm(a)


# ---------- lógica pura ----------
def test_escolhe_o_grupo_mais_parecido_acima_do_limiar():
    grupos = [(1, unit(1, 0, 0)), (2, unit(0, 1, 0))]
    gid, sim = incidents.escolher_grupo(unit(0.9, 0.1, 0), grupos, 0.70)
    assert gid == 1 and sim > 0.9


def test_nao_agrupa_quando_nenhum_passa_do_limiar():
    gid, sim = incidents.escolher_grupo(unit(0, 0, 1), [(1, unit(1, 0, 0))], 0.70)
    assert gid is None and sim < 0.1


def test_sem_grupos_abertos_nao_agrupa():
    assert incidents.escolher_grupo(unit(1, 0, 0), [], 0.7)[0] is None


def test_centroide_e_a_media_normalizada():
    c = incidents.atualizar_centroide(unit(1, 0), 1, unit(0, 1))
    assert np.allclose(c, unit(1, 1)) and abs(np.linalg.norm(c) - 1) < 1e-6


def test_janela_atingida_com_tres_em_30_minutos():
    ts = [T0, T0 + timedelta(minutes=10), T0 + timedelta(minutes=30)]
    assert incidents.janela_atingida(ts, 3, 30) is True


def test_janela_nao_atingida_se_estoura_a_janela():
    ts = [T0, T0 + timedelta(minutes=10), T0 + timedelta(minutes=31)]
    assert incidents.janela_atingida(ts, 3, 30) is False


def test_janela_nao_atingida_com_menos_que_o_minimo():
    assert incidents.janela_atingida([T0, T0], 3, 30) is False


def test_janela_desliza_sobre_mensagens_antigas():
    ts = [T0, T0 + timedelta(hours=5), T0 + timedelta(hours=5, minutes=5), T0 + timedelta(hours=5, minutes=9)]
    assert incidents.janela_atingida(ts, 3, 30) is True


def test_serializacao_do_vetor_e_reversivel():
    v = HashEmbedder().encode(["teste de serialização"])[0]
    assert np.allclose(de_bytes(para_bytes(v)), v)


def test_hash_embedder_e_deterministico_e_normalizado():
    e = HashEmbedder()
    a, b = e.encode(["Pix fora do ar"])[0], e.encode(["Pix fora do ar"])[0]
    assert np.array_equal(a, b) and abs(np.linalg.norm(a) - 1) < 1e-5


# ---------- integração com o banco (embeddings controlados) ----------
def inserir_ticket(db, minutos_atras, texto="mensagem"):
    with db.begin() as conn:
        res = conn.execute(
            text("INSERT INTO tickets (canal, texto, status, received_at) VALUES ('chat', :t, 'classificado', :r)"),
            {"t": texto, "r": datetime(2026, 10, 17, 12, 0, 0) - timedelta(minutes=minutos_atras)},
        )
        return int(res.lastrowid)


class EmbedderFixo:
    """Devolve vetores pré-definidos por texto, para controlar a similaridade."""
    nome = "fixo"
    VETORES = {
        "pix1": unit(1, 0.05, 0), "pix2": unit(1, 0.1, 0), "pix3": unit(1, 0.0, 0.1), "pix4": unit(1, 0.2, 0),
        "login": unit(0, 1, 0), "login2": unit(0.05, 1, 0),
    }

    def encode(self, textos):
        return np.stack([self.VETORES[t] for t in textos])


def com_embedder(monkeypatch):
    monkeypatch.setattr(incidents, "get_embedder", lambda: EmbedderFixo())


def test_tres_mensagens_semelhantes_em_30_min_abrem_incidente(db, monkeypatch):
    com_embedder(monkeypatch)
    ids = [inserir_ticket(db, m, t) for m, t in [(20, "pix1"), (12, "pix2"), (3, "pix3")]]
    resultados = [incidents.registrar(i) for i in ids]
    assert [r["acao"] for r in resultados] == ["novo_grupo", "entrou_no_grupo", "entrou_no_grupo"]
    assert [r["incidente"] for r in resultados] == [False, False, True]

    inc = incidents.listar_incidentes()
    assert len(inc) == 1 and inc[0]["size"] == 3 and len(inc[0]["tickets"]) == 3
    assert "3 mensagens semelhantes" in inc[0]["justificativa"]  # justificativa com evidência


def test_duas_mensagens_semelhantes_nao_abrem_incidente(db, monkeypatch):
    com_embedder(monkeypatch)
    for m, t in [(10, "pix1"), (5, "pix2")]:
        incidents.registrar(inserir_ticket(db, m, t))
    assert incidents.listar_incidentes() == []
    assert len(incidents.listar_incidentes(apenas_incidentes=False)) == 1


def test_mensagens_diferentes_formam_grupos_separados(db, monkeypatch):
    com_embedder(monkeypatch)
    incidents.registrar(inserir_ticket(db, 10, "pix1"))
    r = incidents.registrar(inserir_ticket(db, 5, "login"))
    assert r["acao"] == "novo_grupo"


def test_tres_mensagens_fora_da_janela_nao_abrem_incidente(db, monkeypatch):
    com_embedder(monkeypatch)
    for m, t in [(300, "pix1"), (170, "pix2"), (0, "pix3")]:  # espaçadas por horas
        incidents.registrar(inserir_ticket(db, m, t))
    assert incidents.listar_incidentes() == []


def test_limiar_e_janela_sao_configuraveis(db, monkeypatch):
    com_embedder(monkeypatch)
    with db.begin() as conn:
        conn.execute(text("UPDATE app_config SET valor = '0.9999' WHERE chave = 'similarity_threshold'"))
    incidents.registrar(inserir_ticket(db, 10, "pix1"))
    r = incidents.registrar(inserir_ticket(db, 5, "pix4"))
    assert r["acao"] == "novo_grupo"  # com limiar altíssimo, não agrupa


def test_volume_minimo_e_configuravel(db, monkeypatch):
    com_embedder(monkeypatch)
    with db.begin() as conn:
        conn.execute(text("UPDATE app_config SET valor = '2' WHERE chave = 'min_group_size'"))
    incidents.registrar(inserir_ticket(db, 10, "pix1"))
    r = incidents.registrar(inserir_ticket(db, 5, "pix2"))
    assert r["incidente"] is True


def test_registrar_e_idempotente(db, monkeypatch):
    com_embedder(monkeypatch)
    tid = inserir_ticket(db, 5, "pix1")
    incidents.registrar(tid)
    assert incidents.registrar(tid)["acao"] == "ja_agrupado"


def test_incidente_aparece_nas_metricas_e_no_endpoint(client, db, monkeypatch):
    com_embedder(monkeypatch)
    for m, t in [(20, "pix1"), (12, "pix2"), (3, "pix3")]:
        incidents.registrar(inserir_ticket(db, m, t))
    r = client.get("/incidentes", headers=CHAVE).json()
    assert len(r) == 1 and r[0]["status"] == "incidente"
    assert client.get("/metricas", headers=CHAVE).json()["incidentes"] == 1
