"""Mensagens internas: chat direto entre os atendentes (página "Mensagens internas" do painel).

Identidade: o painel usa uma chave única; cada atendente se identifica pelo nome ("Seu nome no chat").
Presença: o painel avisa a cada ~30 s; quem deu sinal nos últimos 2 min aparece como online.
Anexos (arquivo ou áudio gravado) ficam no banco, até MAX_ANEXO bytes, com tipos permitidos.
"""
import base64
import binascii
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from .db import get_engine, utcnow

ONLINE_JANELA = timedelta(minutes=2)
MAX_ANEXO = 3 * 1024 * 1024  # 3 MB
MAX_TEXTO = 4000
TIPOS_PERMITIDOS = ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain",
                    "audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav")


class MembroNaoEncontrado(Exception):
    pass


class MensagemInvalida(ValueError):
    pass


def _nome(nome: str) -> str:
    n = " ".join((nome or "").split())[:60]
    if len(n) < 2:
        raise MensagemInvalida("nome do atendente muito curto")
    return n


def _garantir(conn, nome: str) -> int:
    nome = _nome(nome)
    conn.execute(text("INSERT IGNORE INTO team_members (nome) VALUES (:n)"), {"n": nome})
    return int(conn.execute(text("SELECT id FROM team_members WHERE nome = :n"), {"n": nome}).scalar())


def _id(conn, nome: str) -> int:
    mid = conn.execute(text("SELECT id FROM team_members WHERE nome = :n"), {"n": _nome(nome)}).scalar()
    if mid is None:
        raise MembroNaoEncontrado(nome)
    return int(mid)


def adicionar(nome: str) -> dict:
    with get_engine().begin() as conn:
        mid = _garantir(conn, nome)
    return {"id": mid, "nome": _nome(nome)}


def presenca(nome: str, agora: Optional[datetime] = None) -> dict:
    """Registra que o atendente está com o painel aberto (cria o cadastro na 1ª vez)."""
    with get_engine().begin() as conn:
        mid = _garantir(conn, nome)
        conn.execute(text("UPDATE team_members SET ultima_atividade = :a WHERE id = :i"), {"a": agora or utcnow(), "i": mid})
    return {"id": mid, "nome": _nome(nome)}


def listar(eu: str, agora: Optional[datetime] = None) -> list[dict]:
    """Colegas com status, última mensagem trocada comigo e quantas não li. Conversas recentes primeiro."""
    agora = agora or utcnow()
    with get_engine().begin() as conn:
        meu = _garantir(conn, eu)
        rows = conn.execute(text(
            "SELECT t.id, t.nome, t.ultima_atividade, "
            " (SELECT m.id FROM internal_messages m WHERE (m.de_id = t.id AND m.para_id = :eu) OR (m.de_id = :eu AND m.para_id = t.id) "
            "  ORDER BY m.id DESC LIMIT 1) AS ultima_id, "
            " (SELECT COUNT(*) FROM internal_messages m WHERE m.de_id = t.id AND m.para_id = :eu AND m.lida_em IS NULL) AS nao_lidas "
            "FROM team_members t WHERE t.id <> :eu"
        ), {"eu": meu}).fetchall()
        ids = [r.ultima_id for r in rows if r.ultima_id]
        ultimas = {}
        if ids:
            marcadores = ", ".join(f":m{i}" for i in range(len(ids)))
            for m in conn.execute(text(
                f"SELECT id, de_id, texto, anexo_nome, anexo_tipo, created_at FROM internal_messages WHERE id IN ({marcadores})"
            ), {f"m{i}": v for i, v in enumerate(ids)}):
                ultimas[m.id] = m
    saida = []
    for r in rows:
        u = ultimas.get(r.ultima_id)
        resumo = None
        if u is not None:
            corpo = u.texto or ("🎤 Áudio" if (u.anexo_tipo or "").startswith("audio/") else f"📎 {u.anexo_nome}")
            resumo = {"texto": corpo[:140], "minha": u.de_id == meu, "created_at": u.created_at}
        saida.append({
            "id": r.id, "nome": r.nome, "ultima_atividade": r.ultima_atividade,
            "online": bool(r.ultima_atividade and agora - r.ultima_atividade <= ONLINE_JANELA),
            "ultima_mensagem": resumo, "nao_lidas": int(r.nao_lidas or 0),
        })
    saida.sort(key=lambda x: (x["ultima_mensagem"]["created_at"] if x["ultima_mensagem"] else datetime.min), reverse=True)
    return saida


def _linha(m, meu: int) -> dict:
    return {"id": m.id, "minha": m.de_id == meu, "texto": m.texto, "created_at": m.created_at, "lida_em": m.lida_em,
            "anexo": {"nome": m.anexo_nome, "tipo": m.anexo_tipo, "tamanho": m.tamanho} if m.anexo_tipo else None}


def conversa(eu: str, com: str, depois_de: int = 0, limite: int = 200) -> list[dict]:
    """Mensagens entre os dois (sem o conteúdo dos anexos). Marca como lidas as que recebi."""
    with get_engine().begin() as conn:
        meu, outro = _garantir(conn, eu), _id(conn, com)
        rows = conn.execute(text(
            "SELECT id, de_id, texto, anexo_nome, anexo_tipo, OCTET_LENGTH(anexo_dados) AS tamanho, created_at, lida_em "
            "FROM internal_messages WHERE ((de_id = :a AND para_id = :b) OR (de_id = :b AND para_id = :a)) AND id > :d "
            "ORDER BY id DESC LIMIT :l"
        ), {"a": meu, "b": outro, "d": depois_de, "l": limite}).fetchall()
        conn.execute(text(
            "UPDATE internal_messages SET lida_em = :q WHERE de_id = :b AND para_id = :a AND lida_em IS NULL"
        ), {"q": utcnow(), "a": meu, "b": outro})
    return [_linha(m, meu) for m in reversed(rows)]


def enviar(de: str, para: str, texto: Optional[str] = None, anexo_nome: Optional[str] = None,
           anexo_tipo: Optional[str] = None, anexo_base64: Optional[str] = None) -> dict:
    texto = (texto or "").strip()[:MAX_TEXTO] or None
    dados = None
    if anexo_base64:
        tipo = (anexo_tipo or "").split(";")[0].strip().lower()
        if tipo not in TIPOS_PERMITIDOS:
            raise MensagemInvalida("tipo de arquivo não permitido")
        try:
            dados = base64.b64decode(anexo_base64, validate=True)
        except (binascii.Error, ValueError):
            raise MensagemInvalida("anexo inválido") from None
        if not dados or len(dados) > MAX_ANEXO:
            raise MensagemInvalida(f"anexo vazio ou maior que {MAX_ANEXO // (1024 * 1024)} MB")
        anexo_tipo = tipo
        anexo_nome = " ".join((anexo_nome or "arquivo").replace("/", "_").replace("\\", "_").split())[:160] or "arquivo"
    else:
        anexo_nome = anexo_tipo = None
    if not texto and dados is None:
        raise MensagemInvalida("mensagem vazia")
    if _nome(de) == _nome(para):
        raise MensagemInvalida("escolha outro atendente")
    with get_engine().begin() as conn:
        meu, outro = _garantir(conn, de), _id(conn, para)
        agora = utcnow()
        res = conn.execute(text(
            "INSERT INTO internal_messages (de_id, para_id, texto, anexo_nome, anexo_tipo, anexo_dados, created_at) "
            "VALUES (:de, :para, :t, :an, :at, :ad, :q)"
        ), {"de": meu, "para": outro, "t": texto, "an": anexo_nome, "at": anexo_tipo, "ad": dados, "q": agora})
        conn.execute(text("UPDATE team_members SET ultima_atividade = :q WHERE id = :i"), {"q": agora, "i": meu})
        mid = int(res.lastrowid)
        m = conn.execute(text(
            "SELECT id, de_id, texto, anexo_nome, anexo_tipo, OCTET_LENGTH(anexo_dados) AS tamanho, created_at, lida_em "
            "FROM internal_messages WHERE id = :i"
        ), {"i": mid}).one()
    return _linha(m, meu)


def anexo(mensagem_id: int, eu: str) -> tuple[str, str, bytes]:
    """Conteúdo do anexo, só para quem participa da conversa."""
    with get_engine().connect() as conn:
        meu = _id(conn, eu)
        m = conn.execute(text(
            "SELECT anexo_nome, anexo_tipo, anexo_dados FROM internal_messages "
            "WHERE id = :i AND anexo_dados IS NOT NULL AND (de_id = :eu OR para_id = :eu)"
        ), {"i": mensagem_id, "eu": meu}).fetchone()
    if m is None:
        raise MembroNaoEncontrado(mensagem_id)
    return m.anexo_nome, m.anexo_tipo, bytes(m.anexo_dados)
