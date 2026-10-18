"""Encerramento automático por falta de comunicação do cliente.

Se a última mensagem da conversa é nossa (da IA ou de um atendente) e o cliente fica `encerrar_inativo_min` minutos
sem responder (app_config; 0 desliga), o atendimento é encerrado como "cliente sem retorno", com o relatório final.
Antes, o cliente recebe um aviso de que pode escrever de novo, o que abre outro atendimento.
Fica de fora a conversa que a IA acabou de passar para um atendente (modo humano e última mensagem da IA): nesse
caso quem espera é o cliente.
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from . import relatorios, sla, tickets
from .db import get_engine, utcnow

logger = logging.getLogger(__name__)

AUTOR = "Encerramento automático"
INTERVALO_SEG = 60

AVISO = {
    "pt": "Como não recebemos sua resposta, estamos encerrando este atendimento. Se precisar de algo, é só mandar uma "
          "nova mensagem por aqui.",
    "en": "Since we haven't heard back from you, we're closing this conversation. If you need anything, just send us "
          "a new message here.",
    "es": "Como no recibimos tu respuesta, estamos cerrando esta atención. Si necesitas algo, solo envíanos un nuevo "
          "mensaje por aquí.",
}


def inativos(minutos: float, agora: Optional[datetime] = None) -> list[int]:
    """Atendimentos abertos cuja última mensagem é nossa e tem `minutos` ou mais."""
    limite = (agora or utcnow()) - timedelta(minutes=minutos)
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.id FROM tickets t "
                "JOIN messages m ON m.id = (SELECT MAX(id) FROM messages WHERE ticket_id = t.id) "
                "WHERE t.desfecho IS NULL AND m.direcao = 'saida' AND m.created_at <= :limite "
                "AND NOT (t.modo = 'humano' AND m.autor = :ia) ORDER BY t.id"
            ),
            {"limite": limite, "ia": tickets.AUTOR_IA},
        ).fetchall()
    return [r.id for r in rows]


def encerrar_inativos(agora: Optional[datetime] = None) -> list[int]:
    """Avisa o cliente e encerra cada atendimento inativo. Retorna os ids encerrados. Nunca levanta exceção."""
    try:
        with get_engine().connect() as conn:
            minutos = sla.carregar_config(conn)["encerrar_inativo_min"]
        if minutos <= 0:
            return []
        ids = inativos(minutos, agora)
    except Exception:
        logger.exception("erro ao procurar atendimentos sem retorno do cliente")
        return []
    encerrados = []
    for tid in ids:
        try:
            idioma = tickets.obter(tid).get("idioma") or "pt"
            tickets.responder_chat(tid, AVISO.get(idioma, AVISO["pt"]), AUTOR)
            relatorios.encerrar(tid, "sem_retorno", AUTOR,
                                f"Encerrado automaticamente: {int(minutos)} min sem resposta do cliente.")
            encerrados.append(tid)
            logger.info("ticket %s encerrado: %s min sem resposta do cliente", tid, int(minutos))
        except relatorios.TicketJaEncerrado:
            pass  # o atendente encerrou ao mesmo tempo
        except Exception:
            logger.exception("erro ao encerrar o ticket %s por falta de resposta", tid)
    return encerrados


def iniciar_verificacao(parar: threading.Event) -> threading.Thread:
    """Verifica a cada INTERVALO_SEG, em background, até `parar` ser sinalizado."""
    def laco():
        while not parar.wait(INTERVALO_SEG):
            encerrar_inativos()

    th = threading.Thread(target=laco, daemon=True, name="encerrar-inativos")
    th.start()
    return th
