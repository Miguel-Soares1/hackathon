"""API HTTP (FastAPI). Webhook único (ADR-001), responde 202 e processa em background (ADR-009)."""
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from . import corrections, incidents, metrics, pipeline, tickets
from .config import get_settings
from .db import get_engine, utcnow

logger = logging.getLogger(__name__)

CANAIS_MAX = 30


def exigir_chave(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Autenticação por chave no header X-API-Key (threat model T1)."""
    esperada = get_settings().api_key
    if not esperada:
        raise HTTPException(status_code=503, detail="API_KEY não configurada no servidor")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), esperada.encode()):
        raise HTTPException(status_code=401, detail="chave de API ausente ou inválida")


class MensagemIn(BaseModel):
    canal: str = Field(min_length=2, max_length=CANAIS_MAX)
    texto: str = Field(min_length=3, max_length=4000)
    cliente: Optional[str] = Field(default=None, max_length=120)
    received_at: Optional[datetime] = Field(
        default=None, description="Opcional: data/hora original (importação ou simulação). Padrão: agora (UTC)."
    )

    @field_validator("texto", "canal")
    @classmethod
    def _sem_espacos(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("valor muito curto")
        return v

    @field_validator("received_at")
    @classmethod
    def _utc_naive(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        if v > utcnow() + timedelta(minutes=5):
            raise ValueError("received_at não pode estar no futuro")
        return v


class RespostaIn(BaseModel):
    respondido_em: Optional[datetime] = Field(
        default=None, description="Opcional: momento da 1ª resposta (importação/simulação). Padrão: agora (UTC)."
    )

    @field_validator("respondido_em")
    @classmethod
    def _utc_naive(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        if v.tzinfo is not None:
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        if v > utcnow() + timedelta(minutes=5):
            raise ValueError("respondido_em não pode estar no futuro")
        return v


class CorrecaoIn(BaseModel):
    assunto: Optional[str] = None
    urgencia: Optional[str] = None
    sentimento: Optional[str] = None
    equipe: Optional[str] = None
    resposta_sugerida: Optional[str] = None


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Recuperação: reprocessa tickets pendentes sem bloquear a subida da API.
        threading.Thread(target=pipeline.recuperar_pendentes, daemon=True).start()
        yield

    app = FastAPI(title="Triagem IA", version="1.0.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, exc: RequestValidationError):
        erros = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "erro": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=400, content={"detail": "requisição inválida", "erros": erros})

    @app.get("/health")
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/webhook/mensagens", status_code=202, dependencies=[Depends(exigir_chave)])
    def webhook(msg: MensagemIn, background: BackgroundTasks):
        ticket_id = tickets.criar_ticket(msg.canal, msg.texto, msg.cliente, msg.received_at)
        background.add_task(pipeline.processar_ticket, ticket_id)
        return {"ticket_id": ticket_id, "status": "pendente"}

    @app.get("/tickets", dependencies=[Depends(exigir_chave)])
    def listar_tickets(limite: int = Query(100, ge=1, le=1000), apenas_abertos: bool = False):
        return tickets.listar(limite=limite, apenas_abertos=apenas_abertos)

    @app.get("/tickets/{ticket_id}", dependencies=[Depends(exigir_chave)])
    def obter_ticket(ticket_id: int):
        try:
            return tickets.obter(ticket_id)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")

    @app.post("/tickets/{ticket_id}/resposta", dependencies=[Depends(exigir_chave)])
    def responder(ticket_id: int, corpo: Optional[RespostaIn] = None):
        quando = corpo.respondido_em if corpo else None
        try:
            return tickets.marcar_respondido(ticket_id, quando)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")
        except tickets.RespostaAnteriorAoRecebimento:
            raise HTTPException(status_code=400, detail="respondido_em anterior ao recebimento do ticket")

    @app.post("/tickets/{ticket_id}/revisao", status_code=204, dependencies=[Depends(exigir_chave)])
    def confirmar(ticket_id: int):
        try:
            corrections.confirmar_revisao(ticket_id)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")
        except corrections.TicketNaoClassificado:
            raise HTTPException(status_code=409, detail="ticket ainda não foi classificado")

    @app.post("/tickets/{ticket_id}/correcoes", status_code=201, dependencies=[Depends(exigir_chave)])
    def corrigir(ticket_id: int, corpo: CorrecaoIn):
        enviados = {k: v for k, v in corpo.model_dump().items() if v is not None}
        try:
            registradas = corrections.registrar_correcoes(ticket_id, enviados)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")
        except corrections.TicketNaoClassificado:
            raise HTTPException(status_code=409, detail="ticket ainda não foi classificado")
        except corrections.CorrecaoInvalida as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ticket_id": ticket_id, "correcoes_registradas": registradas}

    @app.get("/correcoes", dependencies=[Depends(exigir_chave)])
    def historico(ticket_id: Optional[int] = None, limite: int = Query(200, ge=1, le=1000)):
        return corrections.historico(ticket_id, limite)

    @app.get("/incidentes", dependencies=[Depends(exigir_chave)])
    def incidentes(todos_os_grupos: bool = False):
        return incidents.listar_incidentes(apenas_incidentes=not todos_os_grupos)

    @app.get("/metricas", dependencies=[Depends(exigir_chave)])
    def resumo():
        return metrics.resumo()

    return app


app = create_app()
