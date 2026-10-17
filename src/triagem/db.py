"""Acesso ao MySQL via SQLAlchemy Core. Todas as consultas usam parâmetros nomeados (:param)."""
import functools
import random
import time
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from .config import get_settings


@lru_cache(maxsize=4)
def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def get_engine() -> Engine:
    return _engine(get_settings().database_url)


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
