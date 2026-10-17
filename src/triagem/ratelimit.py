"""Limitador de taxa por janela deslizante (em memória), por chave e global."""
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Optional


class LimitadorJanela:
    """Permite até `por_chave` eventos por chave e `global_` no total, em `janela_s` segundos.

    Em memória e por processo: suficiente para um único container (ver docs/deploy.md).
    """

    MAX_CHAVES = 10_000

    def __init__(self, por_chave: int, global_: int, janela_s: float = 60.0, relogio: Callable[[], float] = time.monotonic):
        self.por_chave, self.global_, self.janela_s, self._relogio = por_chave, global_, janela_s, relogio
        self._eventos: dict[str, deque] = defaultdict(deque)
        self._todos: deque = deque()
        self._lock = threading.Lock()

    @staticmethod
    def _limpar(fila: deque, limite: float) -> None:
        while fila and fila[0] <= limite:
            fila.popleft()

    def permitir(self, chave: str) -> tuple[bool, Optional[int]]:
        """Retorna (permitido, segundos_para_tentar_de_novo). Só registra o evento quando permitido."""
        agora = self._relogio()
        limite = agora - self.janela_s
        with self._lock:
            self._limpar(self._todos, limite)
            fila = self._eventos[chave]
            self._limpar(fila, limite)
            if len(self._eventos) > self.MAX_CHAVES:
                for k in [k for k, v in self._eventos.items() if not v]:
                    del self._eventos[k]
            if len(self._todos) >= self.global_:
                return False, max(1, int(self._todos[0] + self.janela_s - agora) + 1)
            if len(fila) >= self.por_chave:
                return False, max(1, int(fila[0] + self.janela_s - agora) + 1)
            fila.append(agora)
            self._todos.append(agora)
            return True, None
