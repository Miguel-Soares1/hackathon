"""Embeddings locais (ADR-008). 'sbert' = modelo multilíngue; 'hash' = leve, determinístico, para testes/offline."""
import re
import zlib
from functools import lru_cache
from typing import Protocol, Sequence

import numpy as np

from .config import get_settings
from .domain import normalizar


class Embedder(Protocol):
    nome: str

    def encode(self, textos: Sequence[str]) -> np.ndarray: ...


def _normalizar_linhas(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (m / n).astype(np.float32)


class HashEmbedder:
    """Bag de palavras e n-gramas de caracteres projetados por hashing. Sem rede, sem modelo."""

    nome = "hash-512"
    dim = 512

    def encode(self, textos: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(textos), self.dim), dtype=np.float32)
        for i, t in enumerate(textos):
            palavras = re.sub(r"[^a-z0-9]+", " ", normalizar(t)).split()
            feats = list(palavras)
            for p in palavras:
                s = f"#{p}#"
                feats += [s[j:j + 4] for j in range(max(1, len(s) - 3))]
            for f in feats:
                h = zlib.crc32(f.encode("utf-8"))
                out[i, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        return _normalizar_linhas(out)


class SbertEmbedder:
    def __init__(self, modelo: str):
        from sentence_transformers import SentenceTransformer  # import tardio: pesado

        self.nome = modelo.split("/")[-1]
        self._modelo = SentenceTransformer(modelo)

    def encode(self, textos: Sequence[str]) -> np.ndarray:
        v = self._modelo.encode(list(textos), normalize_embeddings=True, show_progress_bar=False)
        return _normalizar_linhas(np.asarray(v, dtype=np.float32))


@lru_cache(maxsize=2)
def _criar(backend: str, modelo: str) -> Embedder:
    if backend == "hash":
        return HashEmbedder()
    if backend == "sbert":
        return SbertEmbedder(modelo)
    raise ValueError(f"EMBEDDING_BACKEND inválido: {backend!r} (use 'sbert' ou 'hash')")


def get_embedder() -> Embedder:
    s = get_settings()
    return _criar(s.embedding_backend, s.embedding_model)


def para_bytes(vetor: np.ndarray) -> bytes:
    return np.asarray(vetor, dtype="<f4").tobytes()


def de_bytes(dados: bytes) -> np.ndarray:
    return np.frombuffer(dados, dtype="<f4").copy()
