"""Ingestão e consulta de tickets (Specs 1 e 5)."""
import re
from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import midias as midias_mod
from . import sla
from .db import com_retry_deadlock, get_engine, utcnow


class TicketNaoEncontrado(Exception):
    pass


class TicketDuplicado(Exception):
    """Mensagem de canal já recebida (mesmo canal + external_id); reenvios do provedor são idempotentes."""

    def __init__(self, ticket_id: int):
        super().__init__(f"mensagem já recebida (ticket {ticket_id})")
        self.ticket_id = ticket_id


class RespostaAnteriorAoRecebimento(ValueError):
    pass


JANELA_CONVERSA = timedelta(hours=24)
_TELEFONE_NO_NOME = re.compile(r"\((\+?\d{8,15})\)\s*$")


def chave_conversa(canal: str, cliente: Optional[str]) -> Optional[str]:
    """Identifica o cliente quando a mensagem chega sem `conversa_id` (ADR-016).

    Usa a mesma chave dos conversores dos canais: telefone no WhatsApp ("Nome (5511...)" -> "5511..."), usuário no
    Instagram ("instagram:fulano" -> "fulano") e o próprio contato nos demais (e-mail, nome no chat). Sem cliente,
    não há como agrupar e cada mensagem vira um ticket.
    """
    c = (cliente or "").strip()
    if not c:
        return None
    telefone = _TELEFONE_NO_NOME.search(c)
    if telefone:
        return telefone.group(1).lstrip("+")
    if c.lower().startswith("instagram:"):
        return c[10:].strip().lower()[:190] or None
    return c.lower()[:190]


def _chave_msg(canal: str, external_id: Optional[str]) -> Optional[str]:
    return f"{canal}:{external_id}"[:220] if external_id else None


def _inserir_mensagem(conn, ticket_id: int, direcao: str, texto: str, autor: Optional[str],
                      quando: datetime, chave: Optional[str] = None) -> int:
    res = conn.execute(
        text(
            "INSERT INTO messages (ticket_id, direcao, autor, texto, external_id, created_at) "
            "VALUES (:t, :d, :a, :x, :e, :q)"
        ),
        {"t": ticket_id, "d": direcao, "a": autor, "x": texto, "e": chave, "q": quando},
    )
    return int(res.lastrowid)


def _ticket_do_externo(canal: str, external_id: str) -> Optional[int]:
    with get_engine().connect() as conn:
        return conn.execute(
            text("SELECT ticket_id FROM messages WHERE external_id = :e"), {"e": _chave_msg(canal, external_id)}
        ).scalar()


def criar_ticket(canal: str, texto: str, cliente: Optional[str] = None, received_at: Optional[datetime] = None,
                 external_id: Optional[str] = None, conversa_id: Optional[str] = None,
                 midias: Sequence[midias_mod.Midia] = ()) -> int:
    """Persiste o ticket como 'pendente' (ADR-009) e a 1ª mensagem da conversa. Classificação é em background.

    Com `external_id` (id da mensagem no WhatsApp, Message-ID do e-mail) a criação é idempotente:
    repetir (canal, external_id) levanta TicketDuplicado com o ticket já existente.
    As `midias` (áudio/foto, ADR-017) são gravadas na mesma transação e lidas pela IA no background.
    """
    agora = utcnow()
    quando = received_at or agora
    try:
        with get_engine().begin() as conn:
            res = conn.execute(
                text(
                    "INSERT INTO tickets (canal, cliente, texto, external_id, conversa_id, status, received_at) "
                    "VALUES (:canal, :cliente, :texto, :external_id, :conversa_id, 'pendente', :received_at)"
                ),
                {"canal": canal, "cliente": cliente, "texto": texto, "external_id": external_id,
                 "conversa_id": conversa_id, "received_at": quando},
            )
            ticket_id = int(res.lastrowid)
            _inserir_mensagem(conn, ticket_id, "entrada", texto, cliente, quando, _chave_msg(canal, external_id))
            midias_mod.salvar(conn, ticket_id, list(midias))
            return ticket_id
    except IntegrityError:
        if external_id is None:
            raise
        with get_engine().connect() as conn:
            existente = conn.execute(
                text("SELECT id FROM tickets WHERE canal = :canal AND external_id = :e"),
                {"canal": canal, "e": external_id},
            ).scalar()
        if existente is None:
            raise
        raise TicketDuplicado(int(existente)) from None


def receber_mensagem(canal: str, texto: str, cliente: Optional[str] = None, received_at: Optional[datetime] = None,
                     external_id: Optional[str] = None, conversa_id: Optional[str] = None,
                     midias: Sequence[midias_mod.Midia] = ()) -> tuple[int, bool, Optional[int]]:
    """Entrada de mensagem de um canal. Retorna (ticket_id, novo, id da mensagem anexada ou None).

    Com `conversa_id`, a mensagem entra na conversa já existente do cliente (mesmo canal) enquanto ela está
    aberta ou foi respondida há menos de 24 h; fora disso (ou sem `conversa_id`) nasce um ticket novo.
    As mídias de uma mensagem anexada ficam no ticket e são lidas pela IA depois (`midias.processar` com o id da
    mensagem); a triagem do ticket não muda (ADR-016).
    """
    conversa_id = conversa_id or chave_conversa(canal, cliente)
    if conversa_id:
        if external_id and _ticket_do_externo(canal, external_id) is not None:
            raise TicketDuplicado(int(_ticket_do_externo(canal, external_id)))
        agora = utcnow()
        quando = received_at or agora
        try:
            with get_engine().begin() as conn:
                ultimo = conn.execute(
                    text(
                        "SELECT t.id, t.first_response_at, "
                        "(SELECT MAX(m.created_at) FROM messages m WHERE m.ticket_id = t.id AND m.direcao = 'saida') AS ultima_saida "
                        "FROM tickets t WHERE t.canal = :c AND t.conversa_id = :v ORDER BY t.id DESC LIMIT 1"
                    ),
                    {"c": canal, "v": conversa_id},
                ).fetchone()
                if ultimo is not None:
                    ref = max([x for x in (ultimo.first_response_at, ultimo.ultima_saida) if x is not None], default=None)
                    if ref is None or agora - ref <= JANELA_CONVERSA:
                        msg_id = _inserir_mensagem(conn, int(ultimo.id), "entrada", texto, cliente, quando,
                                                   _chave_msg(canal, external_id))
                        midias_mod.salvar(conn, int(ultimo.id), list(midias))
                        return int(ultimo.id), False, msg_id
        except IntegrityError:
            existente = _ticket_do_externo(canal, external_id) if external_id else None
            if existente is None:
                raise
            raise TicketDuplicado(int(existente)) from None
    return criar_ticket(canal, texto, cliente, received_at, external_id, conversa_id, midias), True, None


def _linha_para_dict(row, prazos, risco_pct, agora, midias: list[dict]) -> dict:
    d = dict(row._mapping)
    d["revisado"] = bool(d.get("revisado"))
    d["midias"] = midias
    est = sla.avaliar(d["received_at"], d.get("urgencia"), prazos, d["first_response_at"], agora, risco_pct)
    d["sla"] = {
        "estado": est.estado,
        "prazo_minutos": est.prazo_minutos,
        "vence_em": est.vence_em,
        "consumido_pct": est.consumido_pct,
        "cumpriu": est.cumpriu,
    }
    if d["first_response_at"] is None:
        d["aguardando"] = True
    elif d.get("ultima_saida_id"):  # compara por id: o DATETIME só tem precisão de segundos
        d["aguardando"] = bool(d.get("ultima_entrada_id") and d["ultima_entrada_id"] > d["ultima_saida_id"])
    else:  # respondido por fora do chat (botão "marcar respondido")
        d["aguardando"] = bool(d.get("ultima_entrada_at") and d["ultima_entrada_at"] > d["first_response_at"])
    d["ultima_texto"] = d.get("ultima_texto") or d["texto"]
    return d


_SQL_CONVERSA = (
    "SELECT v.*, m.ultima_entrada_at, m.ultima_saida_at, m.ultima_entrada_id, m.ultima_saida_id, m.total_mensagens, "
    "(SELECT x.texto FROM messages x WHERE x.ticket_id = v.ticket_id ORDER BY x.id DESC LIMIT 1) AS ultima_texto "
    "FROM vw_tickets v LEFT JOIN ("
    "SELECT ticket_id, MAX(CASE WHEN direcao = 'entrada' THEN created_at END) AS ultima_entrada_at, "
    "MAX(CASE WHEN direcao = 'saida' THEN created_at END) AS ultima_saida_at, "
    "MAX(CASE WHEN direcao = 'entrada' THEN id END) AS ultima_entrada_id, "
    "MAX(CASE WHEN direcao = 'saida' THEN id END) AS ultima_saida_id, COUNT(*) AS total_mensagens "
    "FROM messages GROUP BY ticket_id) m ON m.ticket_id = v.ticket_id "
)


def listar(limite: int = 200, apenas_abertos: bool = False, agora: Optional[datetime] = None) -> list[dict]:
    agora = agora or utcnow()
    with get_engine().connect() as conn:
        prazos = sla.carregar_prazos(conn)
        risco = sla.carregar_config(conn)["sla_risco_pct"]
        rows = conn.execute(
            text(
                _SQL_CONVERSA + "WHERE (:so_abertos = 0 OR v.first_response_at IS NULL) "
                "ORDER BY v.received_at DESC, v.ticket_id DESC LIMIT :limite"
            ),
            {"limite": limite, "so_abertos": 1 if apenas_abertos else 0},
        ).fetchall()
        midias = midias_mod.por_ticket(conn, [r.ticket_id for r in rows])
    return [_linha_para_dict(r, prazos, risco, agora, midias.get(r.ticket_id, [])) for r in rows]


def obter(ticket_id: int, agora: Optional[datetime] = None) -> dict:
    agora = agora or utcnow()
    with get_engine().connect() as conn:
        prazos = sla.carregar_prazos(conn)
        risco = sla.carregar_config(conn)["sla_risco_pct"]
        row = conn.execute(text(_SQL_CONVERSA + "WHERE v.ticket_id = :id"), {"id": ticket_id}).fetchone()
        midias = midias_mod.por_ticket(conn, [ticket_id])
    if row is None:
        raise TicketNaoEncontrado(ticket_id)
    return _linha_para_dict(row, prazos, risco, agora, midias.get(ticket_id, []))


@com_retry_deadlock()
def _registrar_resposta(ticket_id: int, quando: datetime) -> None:
    with get_engine().begin() as conn:
        existe = conn.execute(text("SELECT received_at FROM tickets WHERE id = :id"), {"id": ticket_id}).fetchone()
        if existe is None:
            raise TicketNaoEncontrado(ticket_id)
        if quando < existe.received_at:
            raise RespostaAnteriorAoRecebimento(ticket_id)
        conn.execute(
            text("UPDATE tickets SET first_response_at = :q WHERE id = :id AND first_response_at IS NULL"),
            {"q": quando, "id": ticket_id},
        )


def marcar_respondido(ticket_id: int, quando: Optional[datetime] = None) -> dict:
    """Registra a primeira resposta. Se já houver uma, a original é preservada (idempotente)."""
    _registrar_resposta(ticket_id, quando or utcnow())
    return obter(ticket_id)


def mensagens(ticket_id: int, depois_de: int = 0) -> list[dict]:
    """Conversa do ticket em ordem cronológica. `depois_de` (id da última mensagem vista) permite polling."""
    with get_engine().connect() as conn:
        t = conn.execute(
            text("SELECT id, cliente, texto, received_at FROM tickets WHERE id = :id"), {"id": ticket_id}
        ).fetchone()
        if t is None:
            raise TicketNaoEncontrado(ticket_id)
        rows = conn.execute(
            text(
                "SELECT id, direcao, autor, texto, created_at FROM messages "
                "WHERE ticket_id = :t AND id > :d ORDER BY id"
            ),
            {"t": ticket_id, "d": depois_de},
        ).fetchall()
    if not rows and depois_de == 0:  # ticket anterior ao chat: usa o texto original
        return [{"id": 0, "direcao": "entrada", "autor": t.cliente, "texto": t.texto, "created_at": t.received_at}]
    return [dict(r._mapping) for r in rows]


@com_retry_deadlock()
def _gravar_resposta_chat(ticket_id: int, texto: str, autor: Optional[str], agora: datetime) -> int:
    with get_engine().begin() as conn:
        existe = conn.execute(text("SELECT id FROM tickets WHERE id = :id"), {"id": ticket_id}).fetchone()
        if existe is None:
            raise TicketNaoEncontrado(ticket_id)
        conn.execute(  # tickets primeiro, depois a mensagem filha (ordem que evita deadlock com o pipeline)
            text("UPDATE tickets SET first_response_at = :q WHERE id = :id AND first_response_at IS NULL"),
            {"q": agora, "id": ticket_id},
        )
        return _inserir_mensagem(conn, ticket_id, "saida", texto, autor, agora)


def responder_chat(ticket_id: int, texto: str, autor: Optional[str] = None) -> dict:
    """Resposta do atendente no chat. Grava a mensagem e registra a 1ª resposta (SLA) se ainda não havia.

    Não envia nada ao cliente: o canal de entrega é integrado depois (ver docs/chat.md).
    """
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("mensagem vazia")
    agora = utcnow()
    msg_id = _gravar_resposta_chat(ticket_id, texto[:2000], (autor or None) and autor[:120], agora)
    return {"id": msg_id, "ticket_id": ticket_id, "direcao": "saida", "autor": autor, "texto": texto[:2000], "created_at": agora}


def unificar_conversas(aplicar: bool = False) -> list[dict]:
    """Junta tickets duplicados do mesmo cliente (mesmo canal e conversa) criados antes do agrupamento (ADR-016).

    1. Tickets sem `conversa_id` (ou do antigo modo "IA como cliente", `demo:...`) ganham a chave de `chave_conversa`.
    2. Em cada conversa, em ordem de chegada, um ticket entra no anterior enquanto a conversa está aberta (sem
       resposta, ou respondida há menos de 24 h), como faria `receber_mensagem`. Mensagens e mídias passam para o
       ticket principal (o mais antigo, que tem a triagem da 1ª mensagem); a 1ª resposta mais antiga é mantida;
       o duplicado é apagado (classificação, revisões e vínculos com incidentes dele vão junto).
    Sem `aplicar`, só devolve o plano: [{"principal", "canal", "cliente", "unidos": [ids]}].
    """
    plano: list[dict] = []
    with get_engine().begin() as conn:
        sem_chave = conn.execute(text(
            "SELECT id, canal, cliente FROM tickets WHERE conversa_id IS NULL OR conversa_id LIKE 'demo:%'")).fetchall()
        for r in sem_chave:
            chave = chave_conversa(r.canal, r.cliente)
            if chave and aplicar:
                conn.execute(text("UPDATE tickets SET conversa_id = :c WHERE id = :i"), {"c": chave, "i": r.id})
        chaves = {r.id: chave_conversa(r.canal, r.cliente) for r in sem_chave}

        linhas = conn.execute(text(
            "SELECT t.id, t.canal, t.cliente, t.conversa_id, t.received_at, t.first_response_at, "
            "(SELECT MAX(m.created_at) FROM messages m WHERE m.ticket_id = t.id AND m.direcao = 'saida') AS ultima_saida "
            "FROM tickets t ORDER BY t.received_at, t.id")).fetchall()
        conversas: dict[tuple, list] = {}
        for r in linhas:
            chave = chaves.get(r.id, r.conversa_id)
            if chave:
                conversas.setdefault(((r.canal or "").lower(), chave), []).append(r)

        for (_, _), itens in conversas.items():
            principal, ref, grupo = itens[0], None, None
            ref = max([x for x in (principal.first_response_at, principal.ultima_saida) if x], default=None)
            for r in itens[1:]:
                if ref is not None and r.received_at - ref > JANELA_CONVERSA:  # conversa encerrada: começa outra
                    principal, grupo = r, None
                    ref = max([x for x in (r.first_response_at, r.ultima_saida) if x], default=None)
                    continue
                if grupo is None:
                    grupo = {"principal": principal.id, "canal": principal.canal, "cliente": principal.cliente, "unidos": []}
                    plano.append(grupo)
                grupo["unidos"].append(r.id)
                ref = max([x for x in (ref, r.first_response_at, r.ultima_saida) if x], default=None)
                if aplicar:
                    conn.execute(text("UPDATE messages SET ticket_id = :p WHERE ticket_id = :d"), {"p": principal.id, "d": r.id})
                    conn.execute(text("UPDATE ticket_midias SET ticket_id = :p WHERE ticket_id = :d"), {"p": principal.id, "d": r.id})
                    if r.first_response_at:
                        conn.execute(text(
                            "UPDATE tickets SET first_response_at = :q WHERE id = :p "
                            "AND (first_response_at IS NULL OR first_response_at > :q)"), {"q": r.first_response_at, "p": principal.id})
                    conn.execute(text("DELETE FROM tickets WHERE id = :d"), {"d": r.id})
        if aplicar and plano:
            # Os grupos de incidente perdem os duplicados apagados: recalcula o tamanho de cada um.
            conn.execute(text("UPDATE incident_groups g SET size = (SELECT COUNT(*) FROM group_members m WHERE m.group_id = g.id)"))
    return plano
