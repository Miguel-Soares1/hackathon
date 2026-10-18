"""Relatório de problemas (ADR-020).

O atendente registra um problema (título e características) e, cada vez que ele acontece, uma ocorrência com o número
de identificação do cliente (telefone, e-mail ou protocolo). A aba Relatórios mostra quantas vezes cada problema
aconteceu e quais clientes foram afetados, para a equipe priorizar a solução.
"""
from typing import Optional

from sqlalchemy import text

from .db import get_engine, utcnow

STATUS = ("aberto", "resolvido")


class ProblemaInvalido(ValueError):
    pass


class ProblemaNaoEncontrado(LookupError):
    pass


def _limpo(valor: Optional[str], minimo: int, maximo: int, campo: str) -> str:
    v = " ".join((valor or "").split())
    if len(v) < minimo:
        raise ProblemaInvalido(f"{campo}: escreva pelo menos {minimo} caracteres")
    return v[:maximo]


def criar(titulo: str, caracteristicas: str, por: Optional[str] = None) -> dict:
    titulo = _limpo(titulo, 3, 160, "título")
    caracteristicas = (caracteristicas or "").strip()[:4000]
    if len(caracteristicas) < 3:
        raise ProblemaInvalido("características: descreva o problema (pelo menos 3 caracteres)")
    with get_engine().begin() as conn:
        res = conn.execute(
            text("INSERT INTO problemas (titulo, caracteristicas, status, criado_por, created_at) "
                 "VALUES (:t, :c, 'aberto', :p, :q)"),
            {"t": titulo, "c": caracteristicas, "p": por, "q": utcnow()},
        )
        return obter(int(res.lastrowid), conn)


def registrar_ocorrencia(problema_id: int, cliente_id: str, ticket_id: Optional[int] = None,
                         observacao: Optional[str] = None, por: Optional[str] = None) -> dict:
    cliente_id = _limpo(cliente_id, 3, 190, "identificação do cliente")
    with get_engine().begin() as conn:
        if conn.execute(text("SELECT id FROM problemas WHERE id = :i"), {"i": problema_id}).fetchone() is None:
            raise ProblemaNaoEncontrado(problema_id)
        if ticket_id is not None and conn.execute(text("SELECT id FROM tickets WHERE id = :i"), {"i": ticket_id}).fetchone() is None:
            raise ProblemaInvalido(f"atendimento #{ticket_id} não existe")
        conn.execute(
            text("INSERT INTO problema_ocorrencias (problema_id, cliente_id, ticket_id, observacao, registrado_por, created_at) "
                 "VALUES (:p, :c, :t, :o, :r, :q)"),
            {"p": problema_id, "c": cliente_id, "t": ticket_id, "o": (observacao or "").strip()[:500] or None,
             "r": por, "q": utcnow()},
        )
        return obter(problema_id, conn)


def remover_ocorrencia(problema_id: int, ocorrencia_id: int) -> dict:
    with get_engine().begin() as conn:
        res = conn.execute(text("DELETE FROM problema_ocorrencias WHERE id = :o AND problema_id = :p"),
                           {"o": ocorrencia_id, "p": problema_id})
        if res.rowcount == 0:
            raise ProblemaNaoEncontrado(ocorrencia_id)
        return obter(problema_id, conn)


def alterar(problema_id: int, status: Optional[str] = None, titulo: Optional[str] = None,
            caracteristicas: Optional[str] = None) -> dict:
    if status is not None and status not in STATUS:
        raise ProblemaInvalido(f"status deve ser um de {STATUS}")
    campos, params = [], {"i": problema_id}
    if status is not None:
        campos.append("status = :s"); params["s"] = status
        campos.append("resolvido_em = :r"); params["r"] = utcnow() if status == "resolvido" else None
    if titulo is not None:
        campos.append("titulo = :t"); params["t"] = _limpo(titulo, 3, 160, "título")
    if caracteristicas is not None:
        campos.append("caracteristicas = :c"); params["c"] = caracteristicas.strip()[:4000]
    with get_engine().begin() as conn:
        if conn.execute(text("SELECT id FROM problemas WHERE id = :i"), {"i": problema_id}).fetchone() is None:
            raise ProblemaNaoEncontrado(problema_id)
        if campos:
            conn.execute(text(f"UPDATE problemas SET {', '.join(campos)} WHERE id = :i"), params)
        return obter(problema_id, conn)


def _montar(p, ocorrencias: list) -> dict:
    return {"id": p.id, "titulo": p.titulo, "caracteristicas": p.caracteristicas, "status": p.status,
            "criado_por": p.criado_por, "created_at": p.created_at, "resolvido_em": p.resolvido_em,
            "total": len(ocorrencias), "clientes_distintos": len({o["cliente_id"] for o in ocorrencias}),
            "ultima_em": max((o["created_at"] for o in ocorrencias), default=None), "ocorrencias": ocorrencias}


def _ocorrencias(conn, ids: list[int]) -> dict[int, list[dict]]:
    if not ids:
        return {}
    marcadores = ", ".join(f":i{n}" for n in range(len(ids)))
    rows = conn.execute(
        text(f"SELECT id, problema_id, cliente_id, ticket_id, observacao, registrado_por, created_at "
             f"FROM problema_ocorrencias WHERE problema_id IN ({marcadores}) ORDER BY id DESC"),
        {f"i{n}": i for n, i in enumerate(ids)},
    ).fetchall()
    saida: dict[int, list[dict]] = {}
    for r in rows:
        d = dict(r._mapping)
        saida.setdefault(d.pop("problema_id"), []).append(d)
    return saida


def obter(problema_id: int, conn=None) -> dict:
    if conn is None:
        with get_engine().connect() as c:
            return obter(problema_id, c)
    p = conn.execute(text("SELECT * FROM problemas WHERE id = :i"), {"i": problema_id}).fetchone()
    if p is None:
        raise ProblemaNaoEncontrado(problema_id)
    return _montar(p, _ocorrencias(conn, [p.id]).get(p.id, []))


def listar() -> list[dict]:
    """Problemas abertos primeiro, depois os que mais aconteceram."""
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT * FROM problemas")).fetchall()
        ocorr = _ocorrencias(conn, [r.id for r in rows])
    lista = [_montar(r, ocorr.get(r.id, [])) for r in rows]
    lista.sort(key=lambda p: (p["status"] != "aberto", -p["total"], -p["id"]))
    return lista
