"""Acesso ao MySQL via SQLAlchemy Core. Todas as consultas usam parâmetros nomeados (:param)."""
import functools
import random
import ssl
import time
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from .config import get_settings


def _contexto_ssl(ca: str) -> ssl.SSLContext:
    """MYSQL_SSL_CA: 'sistema' (CAs do sistema), o conteúdo PEM do certificado ou o caminho do arquivo."""
    if ca == "sistema":
        return ssl.create_default_context()
    if ca.lstrip().startswith("-----BEGIN"):
        return ssl.create_default_context(cadata=ca.replace("\\n", "\n"))
    return ssl.create_default_context(cafile=ca)


@lru_cache(maxsize=4)
def _engine(url: str, ssl_ca: str) -> Engine:
    # Bancos gerenciados (Aiven, TiDB Cloud) exigem TLS; o MySQL local do docker compose não.
    args = {"ssl": _contexto_ssl(ssl_ca)} if ssl_ca else {}
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args=args)


def get_engine() -> Engine:
    s = get_settings()
    return _engine(s.database_url, s.mysql_ssl_ca)


def utcnow() -> datetime:
    """Data/hora atual em UTC, sem fuso (como gravamos no banco)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


# 1213 = deadlock; 1205 = lock wait timeout. Ambos são transitórios: basta repetir a transação.
_ERROS_TRANSITORIOS = {1213, 1205}


def com_retry_deadlock(tentativas: int = 4):
    """Repete a função (que deve abrir a própria transação) se o MySQL abortar por deadlock."""

    def decorador(fn):
        @functools.wraps(fn)
        def interno(*args, **kwargs):
            for n in range(1, tentativas + 1):
                try:
                    return fn(*args, **kwargs)
                except OperationalError as exc:
                    codigo = getattr(getattr(exc, "orig", None), "args", [None])[0]
                    if codigo not in _ERROS_TRANSITORIOS or n == tentativas:
                        raise
                    time.sleep(0.05 * n + random.random() * 0.05)

        return interno

    return decorador
