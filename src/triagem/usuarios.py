"""Usuários do painel e sessões de login (ADR-018).

O painel entra com usuário e senha; a chave de API (X-API-Key) continua só para integrações (webhook, canais,
scripts). A senha é guardada com PBKDF2-SHA256 e sal aleatório (nunca em texto). A sessão é um token aleatório
entregue ao navegador; no banco fica só o hash dele, então um vazamento do banco não dá acesso ao painel.
"""
import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .db import get_engine, utcnow

PAPEIS = ("admin", "atendente")
ITERACOES = 390_000
SENHA_MIN = 8
DURACAO_SESSAO = timedelta(hours=12)
DURACAO_LEMBRAR = timedelta(days=30)


class UsuarioInvalido(ValueError):
    pass


class UsuarioDuplicado(ValueError):
    pass


class UsuarioNaoEncontrado(LookupError):
    pass


# ---------------------------------------------------------------- senha
def gerar_hash(senha: str, iteracoes: int = ITERACOES) -> str:
    sal = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), iteracoes)
    return f"pbkdf2_sha256${iteracoes}${sal}${dk.hex()}"


def senha_confere(senha: str, guardado: str) -> bool:
    try:
        algoritmo, iteracoes, sal, esperado = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(iteracoes))
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(dk.hex(), esperado)


# Hash calculado uma vez para gastar o mesmo tempo quando o usuário não existe (não revela quais usuários existem).
_HASH_FALSO = gerar_hash(secrets.token_hex(8))


def validar_senha(senha: str) -> None:
    if len(senha or "") < SENHA_MIN:
        raise UsuarioInvalido(f"a senha precisa ter pelo menos {SENHA_MIN} caracteres")
    if len(senha) > 200:
        raise UsuarioInvalido("senha longa demais")


def _normalizar_usuario(usuario: str) -> str:
    u = (usuario or "").strip().lower()
    if not (3 <= len(u) <= 60) or not all(c.isalnum() or c in "._-@" for c in u):
        raise UsuarioInvalido("usuário deve ter de 3 a 60 caracteres (letras, números, ponto, hífen, _ ou @)")
    return u


def _publico(r) -> dict:
    return {"id": r.id, "usuario": r.usuario, "nome": r.nome, "papel": r.papel, "ativo": bool(r.ativo),
            "created_at": r.created_at, "ultimo_login": r.ultimo_login}


_CAMPOS = "id, usuario, nome, papel, ativo, created_at, ultimo_login"


# ---------------------------------------------------------------- usuários
def existe_algum() -> bool:
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT EXISTS (SELECT 1 FROM usuarios)")).scalar() == 1


def criar(usuario: str, nome: str, senha: str, papel: str = "atendente") -> dict:
    usuario = _normalizar_usuario(usuario)
    nome = (nome or "").strip()[:120] or usuario
    if papel not in PAPEIS:
        raise UsuarioInvalido(f"papel deve ser um de {PAPEIS}")
    validar_senha(senha)
    try:
        with get_engine().begin() as conn:
            res = conn.execute(
                text("INSERT INTO usuarios (usuario, nome, senha_hash, papel, ativo, created_at) "
                     "VALUES (:u, :n, :h, :p, 1, :q)"),
                {"u": usuario, "n": nome, "h": gerar_hash(senha), "p": papel, "q": utcnow()},
            )
            novo = int(res.lastrowid)
    except IntegrityError:
        raise UsuarioDuplicado(f"o usuário {usuario!r} já existe") from None
    return obter(novo)


def obter(usuario_id: int) -> dict:
    with get_engine().connect() as conn:
        r = conn.execute(text(f"SELECT {_CAMPOS} FROM usuarios WHERE id = :i"), {"i": usuario_id}).fetchone()
    if r is None:
        raise UsuarioNaoEncontrado(usuario_id)
    return _publico(r)


def listar() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(text(f"SELECT {_CAMPOS} FROM usuarios ORDER BY ativo DESC, nome")).fetchall()
    return [_publico(r) for r in rows]


def _admins_ativos(conn, exceto: Optional[int] = None) -> int:
    return conn.execute(
        text("SELECT COUNT(*) FROM usuarios WHERE papel = 'admin' AND ativo = 1 AND id <> :e"), {"e": exceto or 0}
    ).scalar()


def alterar(usuario_id: int, nome: Optional[str] = None, papel: Optional[str] = None,
            ativo: Optional[bool] = None, senha: Optional[str] = None) -> dict:
    """Alteração feita pelo administrador. Nunca deixa o sistema sem um administrador ativo."""
    if papel is not None and papel not in PAPEIS:
        raise UsuarioInvalido(f"papel deve ser um de {PAPEIS}")
    if senha is not None:
        validar_senha(senha)
    with get_engine().begin() as conn:
        atual = conn.execute(text("SELECT id, papel, ativo FROM usuarios WHERE id = :i FOR UPDATE"),
                             {"i": usuario_id}).fetchone()
        if atual is None:
            raise UsuarioNaoEncontrado(usuario_id)
        perde_admin = atual.papel == "admin" and atual.ativo and (papel == "atendente" or ativo is False)
        if perde_admin and _admins_ativos(conn, exceto=usuario_id) == 0:
            raise UsuarioInvalido("o sistema precisa de pelo menos um administrador ativo")
        campos, params = [], {"i": usuario_id}
        if nome is not None:
            campos.append("nome = :n"); params["n"] = nome.strip()[:120] or "sem nome"
        if papel is not None:
            campos.append("papel = :p"); params["p"] = papel
        if ativo is not None:
            campos.append("ativo = :a"); params["a"] = 1 if ativo else 0
        if senha is not None:
            campos.append("senha_hash = :h"); params["h"] = gerar_hash(senha)
        if campos:
            conn.execute(text(f"UPDATE usuarios SET {', '.join(campos)} WHERE id = :i"), params)
        if ativo is False or senha is not None:  # desativado ou senha redefinida: derruba as sessões abertas
            conn.execute(text("DELETE FROM sessoes WHERE usuario_id = :i"), {"i": usuario_id})
    return obter(usuario_id)


def trocar_propria_senha(usuario_id: int, senha_atual: str, nova: str, manter_token_hash: Optional[str] = None) -> None:
    validar_senha(nova)
    with get_engine().begin() as conn:
        r = conn.execute(text("SELECT senha_hash FROM usuarios WHERE id = :i"), {"i": usuario_id}).fetchone()
        if r is None or not senha_confere(senha_atual or "", r.senha_hash):
            raise UsuarioInvalido("senha atual incorreta")
        conn.execute(text("UPDATE usuarios SET senha_hash = :h WHERE id = :i"), {"h": gerar_hash(nova), "i": usuario_id})
        # As outras sessões (outros navegadores) caem; a atual continua.
        conn.execute(text("DELETE FROM sessoes WHERE usuario_id = :i AND token_hash <> :t"),
                     {"i": usuario_id, "t": manter_token_hash or ""})


# ---------------------------------------------------------------- sessões
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def autenticar(usuario: str, senha: str) -> Optional[dict]:
    """Confere usuário e senha. Devolve o usuário (sem a senha) ou None, sempre no mesmo tempo."""
    with get_engine().connect() as conn:
        r = conn.execute(text(f"SELECT {_CAMPOS}, senha_hash FROM usuarios WHERE usuario = :u"),
                         {"u": (usuario or "").strip().lower()}).fetchone()
    if r is None:
        senha_confere(senha or "", _HASH_FALSO)
        return None
    if not senha_confere(senha or "", r.senha_hash) or not r.ativo:
        return None
    return _publico(r)


def abrir_sessao(usuario_id: int, lembrar: bool) -> tuple[str, object]:
    token = secrets.token_urlsafe(32)
    agora = utcnow()
    expira = agora + (DURACAO_LEMBRAR if lembrar else DURACAO_SESSAO)
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sessoes WHERE expira_em < :q"), {"q": agora})  # faxina das vencidas
        conn.execute(
            text("INSERT INTO sessoes (token_hash, usuario_id, created_at, expira_em) VALUES (:t, :u, :q, :e)"),
            {"t": _hash_token(token), "u": usuario_id, "q": agora, "e": expira},
        )
        conn.execute(text("UPDATE usuarios SET ultimo_login = :q WHERE id = :u"), {"q": agora, "u": usuario_id})
    return token, expira


def usuario_da_sessao(token: str) -> Optional[dict]:
    if not token:
        return None
    with get_engine().connect() as conn:
        r = conn.execute(
            text(f"SELECT u.{', u.'.join(_CAMPOS.split(', '))}, s.token_hash FROM sessoes s "
                 "JOIN usuarios u ON u.id = s.usuario_id WHERE s.token_hash = :t AND s.expira_em > :q AND u.ativo = 1"),
            {"t": _hash_token(token), "q": utcnow()},
        ).fetchone()
    if r is None:
        return None
    d = _publico(r)
    d["token_hash"] = r.token_hash
    return d


def encerrar_sessao(token: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM sessoes WHERE token_hash = :t"), {"t": _hash_token(token or "")})
