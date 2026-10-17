"""Embeddings locais (ADR-008, ADR-011). 'onnx' = modelo multilíngue int8 sem PyTorch (padrão); 'sbert' = o mesmo modelo via PyTorch (opcional); 'hash' = leve, determinístico, para testes/offline."""
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
    """Modelo original via sentence-transformers (exige PyTorch, ~800 MB de RAM). Opcional."""

    def __init__(self, modelo: str):
        from sentence_transformers import SentenceTransformer  # import tardio: pesado

        self.nome = modelo.split("/")[-1]
        self._modelo = SentenceTransformer(modelo)

    def encode(self, textos: Sequence[str]) -> np.ndarray:
        v = self._modelo.encode(list(textos), normalize_embeddings=True, show_progress_bar=False)
        return _normalizar_linhas(np.asarray(v, dtype=np.float32))


class OnnxEmbedder:
    """Mesmo modelo multilíngue exportado para ONNX e quantizado em int8 (ADR-011).

    Roda com onnxruntime, sem PyTorch: a API inteira usa menos de 400 MB de RAM.
    Reproduz o mean pooling do sentence-transformers (similaridade ~0,995 com o original).
    Tokeniza com o SentencePiece original (~5 MB de vocabulário) em vez do tokenizer.json,
    que ocupa ~320 MB de RAM ao carregar.
    """

    REPO_ONNX = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
    ARQUIVO = "onnx/model_quantized.onnx"
    REPO_TOKENIZADOR = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    MAX_TOKENS = 128
    # Um texto por vez: na quantização dinâmica a escala depende do lote inteiro, e assim o vetor de
    # uma mensagem é o mesmo na API (que agrupa uma por vez) e na calibração.
    LOTE = 1
    # Convenção do XLM-RoBERTa (fairseq): ids do SentencePiece deslocados em 1; <s>=0, <pad>=1, </s>=2, <unk>=3.
    BOS, PAD, EOS, UNK = 0, 1, 2, 3

    def __init__(self, modelo: str):
        import onnxruntime as ort  # import tardio
        import sentencepiece as spm
        from huggingface_hub import hf_hub_download

        self.nome = modelo.split("/")[-1] + "-onnx-int8"
        self._sp = spm.SentencePieceProcessor(
            model_file=hf_hub_download(self.REPO_TOKENIZADOR, "sentencepiece.bpe.model")
        )
        opcoes = ort.SessionOptions()
        opcoes.intra_op_num_threads = 1
        opcoes.enable_cpu_mem_arena = False  # devolve memória entre chamadas
        self._sessao = ort.InferenceSession(
            hf_hub_download(self.REPO_ONNX, self.ARQUIVO), opcoes, providers=["CPUExecutionProvider"]
        )
        self._entradas = {i.name for i in self._sessao.get_inputs()}

    def _ids(self, texto: str) -> list[int]:
        corpo = [i + 1 if i else self.UNK for i in self._sp.encode(texto)][: self.MAX_TOKENS - 2]
        return [self.BOS, *corpo, self.EOS]

    def encode(self, textos: Sequence[str]) -> np.ndarray:
        lotes = []
        for i in range(0, len(textos), self.LOTE):
            seqs = [self._ids(t) for t in textos[i:i + self.LOTE]]
            largura = max(len(s) for s in seqs)
            ids = np.full((len(seqs), largura), self.PAD, dtype=np.int64)
            mascara = np.zeros((len(seqs), largura), dtype=np.int64)
            for k, s in enumerate(seqs):
                ids[k, : len(s)] = s
                mascara[k, : len(s)] = 1
            feeds = {"input_ids": ids, "attention_mask": mascara}
            if "token_type_ids" in self._entradas:
                feeds["token_type_ids"] = np.zeros_like(ids)
            tokens = self._sessao.run(None, feeds)[0]
            m = mascara[..., None].astype(np.float32)
            lotes.append((tokens * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None))
        return _normalizar_linhas(np.vstack(lotes))


@lru_cache(maxsize=2)
def _criar(backend: str, modelo: str) -> Embedder:
    if backend == "hash":
        return HashEmbedder()
    if backend == "onnx":
        return OnnxEmbedder(modelo)
    if backend == "sbert":
        return SbertEmbedder(modelo)
    raise ValueError(f"EMBEDDING_BACKEND inválido: {backend!r} (use 'onnx', 'sbert' ou 'hash')")


def get_embedder() -> Embedder:
    s = get_settings()
    return _criar(s.embedding_backend, s.embedding_model)


def para_bytes(vetor: np.ndarray) -> bytes:
    return np.asarray(vetor, dtype="<f4").tobytes()


def de_bytes(dados: bytes) -> np.ndarray:
    return np.frombuffer(dados, dtype="<f4").copy()
