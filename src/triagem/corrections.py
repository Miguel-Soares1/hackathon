"""Correções do atendente e taxa de acerto da triagem (Spec 3)."""
from typing import Optional

from sqlalchemy import text

from .db import get_engine, utcnow
from .domain import DIMENSOES, DIMENSOES_CLASSIFICACAO, MAX_RESPOSTA, VALORES_PERMITIDOS, normalizar
from .tickets import TicketNaoEncontrado


class TicketNaoClassificado(Exception):
    pass


class CorrecaoInvalida(ValueError):
    pass


def _validar(dimensao: str, valor: str) -> str:
    if dimensao not in DIMENSOES:
        raise CorrecaoInvalida(f"dimensão desconhecida: {dimensao!r}")
    if dimensao == "resposta_sugerida":
        v = str(valor).strip()
        if not v or len(v) > MAX_RESPOSTA:
            raise CorrecaoInvalida(f"resposta_sugerida deve ter de 1 a {MAX_RESPOSTA} caracteres")
        return v
    v = normalizar(valor)
    if v not in VALORES_PERMITIDOS[dimensao]:
        raise CorrecaoInvalida(f"valor inválido para {dimensao}: {valor!r}")
    return v


def registrar_correcoes(ticket_id: int, correcoes: dict[str, str]) -> list[dict]:
    """Registra correções (histórico append-only) e marca o ticket como revisado."""
    if not correcoes:
        raise CorrecaoInvalida("nenhuma correção informada")
    validadas = {dim: _validar(dim, val) for dim, val in correcoes.items()}

    with get_engine().begin() as conn:
        ticket = conn.execute(text("SELECT id FROM tickets WHERE id = :id"), {"id": ticket_id}).fetchone()
        if ticket is None:
            raise TicketNaoEncontrado(ticket_id)
        row = conn.execute(
            text(
                "SELECT assunto, urgencia, sentimento, equipe, resposta_sugerida "
                "FROM classifications WHERE ticket_id = :id"
            ),
            {"id": ticket_id},
        ).fetchone()
        if row is None:
            raise TicketNaoClassificado(ticket_id)
        original = dict(row._mapping)

        registradas = []
        for dim, novo in validadas.items():
            atual = conn.execute(
                text(
                    "SELECT valor_corrigido FROM corrections WHERE ticket_id = :id AND dimensao = :d "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"id": ticket_id, "d": dim},
            ).scalar()
            vigente = atual if atual is not None else original[dim]
            if novo == vigente:
                continue
            conn.execute(
                text(
                    "INSERT INTO corrections (ticket_id, dimensao, valor_original, valor_corrigido, created_at) "
                    "VALUES (:id, :d, :o, :n, :q)"
                ),
                {"id": ticket_id, "d": dim, "o": original[dim], "n": novo, "q": utcnow()},
            )
            registradas.append({"dimensao": dim, "valor_original": original[dim], "valor_corrigido": novo})

        conn.execute(
            text("INSERT IGNORE INTO reviews (ticket_id, reviewed_at) VALUES (:id, :q)"),
            {"id": ticket_id, "q": utcnow()},
        )
    return registradas


def confirmar_revisao(ticket_id: int) -> None:
    """O atendente confirma que a triagem estava correta (conta como acerto)."""
    with get_engine().begin() as conn:
        existe = conn.execute(text("SELECT id FROM tickets WHERE id = :id"), {"id": ticket_id}).fetchone()
        if existe is None:
            raise TicketNaoEncontrado(ticket_id)
        classificado = conn.execute(
            text("SELECT 1 FROM classifications WHERE ticket_id = :id"), {"id": ticket_id}
        ).fetchone()
        if classificado is None:
            raise TicketNaoClassificado(ticket_id)
        conn.execute(
            text("INSERT IGNORE INTO reviews (ticket_id, reviewed_at) VALUES (:id, :q)"),
            {"id": ticket_id, "q": utcnow()},
        )


def historico(ticket_id: Optional[int] = None, limite: int = 200) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, ticket_id, dimensao, valor_original, valor_corrigido, created_at FROM corrections "
                "WHERE (:t IS NULL OR ticket_id = :t) ORDER BY id DESC LIMIT :l"
            ),
            {"t": ticket_id, "l": limite},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def calcular_precisao(revisados: int, erros_por_dimensao: dict[str, int]) -> dict:
    """Taxa de acerto por dimensão = 1 - erros/revisados. O agregado cobre as 4 dimensões de classificação."""
    if revisados == 0:
        return {"revisados": 0, "por_dimensao": {}, "agregado": None}
    por_dim = {
        d: round((1 - erros_por_dimensao.get(d, 0) / revisados) * 100, 1) for d in DIMENSOES
    }
    erros_cls = sum(erros_por_dimensao.get(d, 0) for d in DIMENSOES_CLASSIFICACAO)
    agregado = round((1 - erros_cls / (revisados * len(DIMENSOES_CLASSIFICACAO))) * 100, 1)
    return {"revisados": revisados, "por_dimensao": por_dim, "agregado": agregado}


def precisao(origem: Optional[str] = None, prompt_version: Optional[str] = None) -> dict:
    """Precisão da triagem. `origem` ('llm' ou 'fallback') separa o plano B da IA (ADR-009);
    `prompt_version` separa as versões do prompt (ex.: 'v1' contra 'v1+fewshot', ADR-014)."""
    filtros = {"o": origem, "pv": prompt_version}
    with get_engine().connect() as conn:
        revisados = conn.execute(
            text(
                "SELECT COUNT(*) FROM reviews rv JOIN classifications cl ON cl.ticket_id = rv.ticket_id "
                "WHERE (:o IS NULL OR cl.origem = :o) AND (:pv IS NULL OR cl.prompt_version = :pv)"
            ),
            filtros,
        ).scalar() or 0
        rows = conn.execute(
            text(
                "SELECT c.dimensao, COUNT(*) AS erros FROM corrections c "
                "JOIN (SELECT ticket_id, dimensao, MAX(id) AS mid FROM corrections GROUP BY ticket_id, dimensao) m "
                "  ON c.id = m.mid "
                "JOIN reviews rv ON rv.ticket_id = c.ticket_id "
                "JOIN classifications cl ON cl.ticket_id = c.ticket_id "
                "WHERE c.valor_corrigido <> c.valor_original AND (:o IS NULL OR cl.origem = :o) "
                "AND (:pv IS NULL OR cl.prompt_version = :pv) "
                "GROUP BY c.dimensao"
            ),
            filtros,
        ).fetchall()
    resultado = calcular_precisao(int(revisados), {r.dimensao: int(r.erros) for r in rows})
    resultado["origem"] = origem or "todas"
    if prompt_version:
        resultado["prompt_version"] = prompt_version
    return resultado


def precisao_por_versao() -> list[dict]:
    """Taxa de acerto de cada versão do prompt que já tem tickets revisados, da mais antiga para a mais nova."""
    with get_engine().connect() as conn:
        versoes = conn.execute(
            text(
                "SELECT cl.prompt_version, MIN(cl.classified_at) AS desde FROM classifications cl "
                "JOIN reviews rv ON rv.ticket_id = cl.ticket_id GROUP BY cl.prompt_version ORDER BY desde"
            )
        ).fetchall()
    return [precisao(prompt_version=v.prompt_version) for v in versoes]
