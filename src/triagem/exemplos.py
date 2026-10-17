"""Few-shot dinâmico: tickets já revisados pelo atendente, parecidos com a mensagem nova, viram exemplos no prompt.

É assim que a triagem "aprende" com as correções sem fine-tuning: cada revisão passa a orientar as próximas
classificações de mensagens semelhantes (ver management/adr.md, ADR-014).
"""
import logging
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import text

from .config import Settings, get_settings
from .db import get_engine
from .embeddings import de_bytes, get_embedder

logger = logging.getLogger(__name__)

# Teto de candidatos lidos do banco (os revisados mais recentes); suficiente para a escala do atendimento.
MAX_CANDIDATOS = 3000


@dataclass(frozen=True)
class Exemplo:
    ticket_id: int
    texto: str
    assunto: str
    urgencia: str
    sentimento: str
    equipe: str
    similaridade: float = 0.0

    def rotulos(self) -> dict:
        return {"assunto": self.assunto, "urgencia": self.urgencia, "sentimento": self.sentimento,
                "equipe": self.equipe}


def selecionar(vetor: np.ndarray, candidatos: Sequence[Exemplo], vetores: np.ndarray,
               k: int, sim_min: float) -> list[Exemplo]:
    """Os `k` candidatos mais parecidos (cosseno, vetores normalizados) com similaridade >= `sim_min`."""
    if k <= 0 or not candidatos:
        return []
    sims = vetores @ vetor
    ordem = np.argsort(-sims)
    escolhidos = []
    for i in ordem[:k]:
        if sims[i] < sim_min:
            break
        c = candidatos[i]
        escolhidos.append(Exemplo(c.ticket_id, c.texto, c.assunto, c.urgencia, c.sentimento, c.equipe,
                                  round(float(sims[i]), 4)))
    return escolhidos


def buscar(texto: str, excluir_ticket: Optional[int] = None, settings: Optional[Settings] = None) -> list[Exemplo]:
    """Exemplos revisados mais parecidos com `texto`. Nunca levanta exceção: na falha, segue sem exemplos."""
    settings = settings or get_settings()
    if settings.fewshot_k <= 0:
        return []
    try:
        embedder = get_embedder()
        with get_engine().connect() as conn:
            # Valores efetivos (com a última correção) de tickets revisados, com embedding do mesmo modelo.
            rows = conn.execute(
                text(
                    "SELECT v.ticket_id, v.texto, v.assunto, v.urgencia, v.sentimento, v.equipe, e.vetor "
                    "FROM vw_tickets v JOIN ticket_embeddings e ON e.ticket_id = v.ticket_id "
                    "WHERE v.revisado = 1 AND e.modelo = :m AND (:x IS NULL OR v.ticket_id <> :x) "
                    "ORDER BY v.ticket_id DESC LIMIT :lim"
                ),
                {"m": embedder.nome, "x": excluir_ticket, "lim": MAX_CANDIDATOS},
            ).fetchall()
        if not rows:
            return []
        candidatos = [Exemplo(r.ticket_id, r.texto, r.assunto, r.urgencia, r.sentimento, r.equipe) for r in rows]
        vetores = np.stack([de_bytes(r.vetor) for r in rows])
        vetor = embedder.encode([texto])[0]
        return selecionar(vetor, candidatos, vetores, settings.fewshot_k, settings.fewshot_sim_min)
    except Exception:
        logger.exception("falha ao buscar exemplos few-shot; classificando sem exemplos")
        return []
