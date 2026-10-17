"""Agrupamento por embeddings e detecção de incidentes (Spec 2, ADR-004/008)."""
import logging
import threading
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import text

from . import sla
from .db import get_engine
from .embeddings import de_bytes, get_embedder, para_bytes

logger = logging.getLogger(__name__)

# O agrupamento lê e atualiza centroides; serializamos para evitar corrida entre tarefas em background.
_lock = threading.Lock()


def escolher_grupo(vetor: np.ndarray, grupos: Sequence[tuple[int, np.ndarray]], limiar: float):
    """Retorna (id_do_grupo, similaridade) do centroide mais parecido que passa do limiar, ou (None, melhor)."""
    melhor_id, melhor_sim = None, -1.0
    for gid, centroide in grupos:
        sim = float(np.dot(vetor, centroide))
        if sim > melhor_sim:
            melhor_id, melhor_sim = gid, sim
    if melhor_id is not None and melhor_sim >= limiar:
        return melhor_id, melhor_sim
    return None, melhor_sim


def atualizar_centroide(centroide: np.ndarray, tamanho: int, vetor: np.ndarray) -> np.ndarray:
    novo = (centroide * tamanho + vetor) / (tamanho + 1)
    norma = np.linalg.norm(novo)
    return (novo / norma).astype(np.float32) if norma else novo.astype(np.float32)


def janela_atingida(instantes: Sequence[datetime], minimo: int, janela_min: float) -> bool:
    """True se existem `minimo` ou mais instantes dentro de uma janela de `janela_min` minutos."""
    ordenados = sorted(instantes)
    janela = timedelta(minutes=janela_min)
    for i in range(len(ordenados) - minimo + 1):
        if ordenados[i + minimo - 1] - ordenados[i] <= janela:
            return True
    return False


_NOME_TRAVA = "triagem_agrupamento"


def registrar(ticket_id: int) -> dict:
    """Gera o embedding do ticket, o encaixa em um grupo e abre incidente se a regra for atingida.

    Duas travas: uma por processo (threading) e um GET_LOCK do MySQL, que vale entre processos/instâncias
    (necessário se a API rodar com mais de um worker).
    """
    with _lock:
        with get_engine().connect() as trava:
            obtida = trava.execute(text("SELECT GET_LOCK(:n, 30)"), {"n": _NOME_TRAVA}).scalar()
            if obtida != 1:
                raise RuntimeError("não foi possível obter a trava de agrupamento em 30 s")
            try:
                return _registrar(ticket_id)
            finally:
                trava.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": _NOME_TRAVA})


def _registrar(ticket_id: int) -> dict:
    eng = get_engine()
    with eng.connect() as conn:
        t = conn.execute(
            text("SELECT id, texto, received_at FROM tickets WHERE id = :id"), {"id": ticket_id}
        ).fetchone()
        if t is None:
            return {"acao": "ticket_inexistente"}
        ja = conn.execute(
            text("SELECT 1 FROM group_members WHERE ticket_id = :id"), {"id": ticket_id}
        ).fetchone()
        if ja:
            return {"acao": "ja_agrupado"}
        cfg = sla.carregar_config(conn)

    embedder = get_embedder()
    vetor = embedder.encode([t.texto])[0]
    limiar = cfg["similarity_threshold"]
    janela = cfg["window_minutes"]
    minimo = int(cfg["min_group_size"])
    ref: datetime = t.received_at

    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ticket_embeddings (ticket_id, modelo, vetor) VALUES (:id, :m, :v) "
                "ON DUPLICATE KEY UPDATE modelo = VALUES(modelo), vetor = VALUES(vetor)"
            ),
            {"id": ticket_id, "m": embedder.nome, "v": para_bytes(vetor)},
        )
        candidatos = conn.execute(
            text(
                "SELECT id, centroid, size FROM incident_groups "
                "WHERE last_at >= :ini AND first_at <= :fim"
            ),
            {"ini": ref - timedelta(minutes=janela), "fim": ref + timedelta(minutes=janela)},
        ).fetchall()
        grupos = [(g.id, de_bytes(g.centroid)) for g in candidatos]
        tamanhos = {g.id: g.size for g in candidatos}
        gid, sim = escolher_grupo(vetor, grupos, limiar)

        if gid is None:
            res = conn.execute(
                text(
                    "INSERT INTO incident_groups (centroid, size, first_at, last_at, status) "
                    "VALUES (:c, 1, :t, :t, 'grupo')"
                ),
                {"c": para_bytes(vetor), "t": ref},
            )
            gid = int(res.lastrowid)
            sim = 1.0
            acao = "novo_grupo"
        else:
            centroide = dict(grupos)[gid]
            novo = atualizar_centroide(centroide, tamanhos[gid], vetor)
            conn.execute(
                text(
                    "UPDATE incident_groups SET centroid = :c, size = size + 1, "
                    "first_at = LEAST(first_at, :t), last_at = GREATEST(last_at, :t) WHERE id = :id"
                ),
                {"c": para_bytes(novo), "t": ref, "id": gid},
            )
            acao = "entrou_no_grupo"
        conn.execute(
            text(
                "INSERT INTO group_members (ticket_id, group_id, similarity, joined_at) "
                "VALUES (:t, :g, :s, :j)"
            ),
            {"t": ticket_id, "g": gid, "s": round(sim, 4), "j": ref},
        )

        incidente = _avaliar_incidente(conn, gid, minimo, janela, limiar)
    return {"acao": acao, "grupo_id": gid, "similaridade": round(sim, 4), "incidente": incidente}


def _avaliar_incidente(conn, gid: int, minimo: int, janela: float, limiar: float) -> bool:
    membros = conn.execute(
        text(
            "SELECT t.received_at, gm.similarity, cl.assunto "
            "FROM group_members gm JOIN tickets t ON t.id = gm.ticket_id "
            "LEFT JOIN classifications cl ON cl.ticket_id = t.id WHERE gm.group_id = :g"
        ),
        {"g": gid},
    ).fetchall()
    instantes = [m.received_at for m in membros]
    if not janela_atingida(instantes, minimo, janela):
        return False

    assuntos = Counter(m.assunto for m in membros if m.assunto)
    predominante = assuntos.most_common(1)[0][0] if assuntos else None
    sims = [float(m.similarity) for m in membros]
    span = (max(instantes) - min(instantes)).total_seconds() / 60.0
    justificativa = (
        f"{len(membros)} mensagens semelhantes (similaridade média {sum(sims) / len(sims):.2f} com o grupo, "
        f"limiar {limiar:.2f}) em {span:.0f} min; assunto predominante: {predominante or 'indefinido'}."
    )
    conn.execute(
        text(
            "UPDATE incident_groups SET status = 'incidente', "
            "incident_opened_at = COALESCE(incident_opened_at, :agora), "
            "justificativa = :j, assunto_predominante = :a WHERE id = :g"
        ),
        {"agora": max(instantes), "j": justificativa, "a": predominante, "g": gid},
    )
    return True


def listar_incidentes(apenas_incidentes: bool = True) -> list[dict]:
    with get_engine().connect() as conn:
        grupos = conn.execute(
            text(
                "SELECT id, size, first_at, last_at, status, incident_opened_at, justificativa, assunto_predominante "
                "FROM incident_groups WHERE (:so_inc = 0 OR status = 'incidente') ORDER BY last_at DESC"
            ),
            {"so_inc": 1 if apenas_incidentes else 0},
        ).fetchall()
        saida = []
        for g in grupos:
            tickets = conn.execute(
                text(
                    "SELECT t.id, t.cliente, t.canal, t.texto, t.received_at FROM group_members gm "
                    "JOIN tickets t ON t.id = gm.ticket_id WHERE gm.group_id = :g ORDER BY t.received_at"
                ),
                {"g": g.id},
            ).fetchall()
            d = dict(g._mapping)
            d["tickets"] = [dict(t._mapping) for t in tickets]
            saida.append(d)
    return saida
