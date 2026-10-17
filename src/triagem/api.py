"""API HTTP (FastAPI). Webhook único (ADR-001), responde 202 e processa em background (ADR-009)."""
import json
import re
import logging
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from . import canais, cliente_simulado, corrections, demo_chat, demo_email, incidents, metrics, pipeline, tickets
from .config import get_settings, validar_producao
from .db import get_engine, utcnow
from .domain import ASSUNTOS, EQUIPES, SENTIMENTOS, URGENCIAS
from .idioma import IDIOMAS
from .pagina_envio import PAGINA_ENVIO
from .ratelimit import LimitadorJanela

logger = logging.getLogger(__name__)

CANAIS_MAX = 30
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


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
    external_id: Optional[str] = Field(
        default=None, max_length=190, description="Opcional: id da mensagem no canal; torna o envio idempotente."
    )
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


class MensagemPublicaIn(BaseModel):
    texto: str = Field(min_length=10, max_length=1000)
    cliente: Optional[str] = Field(default=None, max_length=120)
    website: Optional[str] = Field(default=None, max_length=200, description="Honeypot: deve ficar vazio")

    @field_validator("texto")
    @classmethod
    def _texto_util(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("texto muito curto")
        return v


def ip_do_cliente(request: Request, confiar_proxy: bool) -> str:
    """IP de origem. Só confia em X-Forwarded-For quando a API está atrás de um proxy nosso (TRUST_PROXY=1)."""
    if confiar_proxy:
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado:
            return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


class EmailDemoIn(BaseModel):
    de_email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
    de_nome: Optional[str] = Field(default=None, max_length=80)
    para: str = Field(default="atendimento@suaempresa.com.br", max_length=120)
    assunto: str = Field(default="", max_length=200)
    corpo: str = Field(default="", max_length=3500)

    @field_validator("de_nome", "assunto")
    @classmethod
    def _uma_linha(cls, v: Optional[str]) -> Optional[str]:
        return " ".join(v.split()) if v else v


class ChatDemoIn(BaseModel):
    remetente: str = Field(min_length=1, max_length=30, description="WhatsApp: telefone só com dígitos; Instagram: usuário")
    nome: Optional[str] = Field(default=None, max_length=80)
    texto: str = Field(min_length=1, max_length=1000)


class ConversaDemoIn(BaseModel):
    cenario: Optional[str] = Field(default=None, max_length=30, description="situação do cliente; vazio = sorteada")


class RespostaDemoIn(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


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

    settings = get_settings()
    validar_producao(settings)
    docs = settings.docs_enabled
    app = FastAPI(
        title="Triagem IA", version="1.0.0", lifespan=lifespan,
        docs_url="/docs" if docs else None, redoc_url=None, openapi_url="/openapi.json" if docs else None,
    )

    @app.middleware("http")
    async def _cabecalhos_seguranca(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, exc: RequestValidationError):
        erros = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "erro": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=400, content={"detail": "requisição inválida", "erros": erros})

    limitador = LimitadorJanela(settings.public_rate_per_ip_min, settings.public_rate_global_min)

    @app.get("/enviar", response_class=HTMLResponse, include_in_schema=False)
    def pagina_envio():
        csp = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
               "connect-src 'self'; base-uri 'none'; form-action 'none'")
        return HTMLResponse(PAGINA_ENVIO, headers={"Content-Security-Policy": csp})

    @app.post("/public/mensagens", status_code=202)
    def receber_publica(msg: MensagemPublicaIn, request: Request, background: BackgroundTasks):
        """Entrada pública (formulário web). Sem chave, mas com limite de taxa e honeypot."""
        if msg.website:  # robô: finge sucesso e descarta
            return {"protocolo": None, "status": "recebido"}
        permitido, espera = limitador.permitir(ip_do_cliente(request, settings.trust_proxy))
        if not permitido:
            return JSONResponse(status_code=429, content={"detail": "muitas mensagens; tente novamente em instantes"},
                                headers={"Retry-After": str(espera)})
        ticket_id = tickets.criar_ticket("formulario-web", msg.texto, msg.cliente)
        background.add_task(pipeline.processar_ticket, ticket_id)
        return {"protocolo": ticket_id, "status": "recebido"}

    @app.get("/health")
    def health():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/webhook/mensagens", status_code=202, dependencies=[Depends(exigir_chave)])
    def webhook(msg: MensagemIn, background: BackgroundTasks):
        try:
            ticket_id = tickets.criar_ticket(msg.canal, msg.texto, msg.cliente, msg.received_at, msg.external_id)
        except tickets.TicketDuplicado as dup:
            return {"ticket_id": dup.ticket_id, "status": "duplicado"}
        background.add_task(pipeline.processar_ticket, ticket_id)
        return {"ticket_id": ticket_id, "status": "pendente"}

    # ---- WhatsApp Cloud API (Meta) ----
    @app.get("/webhooks/whatsapp", include_in_schema=False)
    def whatsapp_verificacao(
        modo: Optional[str] = Query(default=None, alias="hub.mode"),
        token: Optional[str] = Query(default=None, alias="hub.verify_token"),
        desafio: Optional[str] = Query(default=None, alias="hub.challenge"),
    ):
        esperado = settings.whatsapp_verify_token
        if not esperado or modo != "subscribe" or not token or not secrets.compare_digest(token, esperado):
            raise HTTPException(status_code=403, detail="verificação recusada")
        return PlainTextResponse(desafio or "")

    def _receber_meta(canal: str, corpo: bytes, assinatura: Optional[str], segredo: str, extrair, background) -> dict:
        """Recebe um webhook da Meta (WhatsApp ou Instagram): valida a assinatura, cria tickets e agenda a triagem."""
        if not segredo:
            raise HTTPException(status_code=503, detail=f"canal {canal} não configurado")
        if not canais.assinatura_valida(corpo, assinatura, segredo):
            raise HTTPException(status_code=403, detail="assinatura inválida")
        try:
            payload = json.loads(corpo)
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "JSON inválido"})
        novas = 0
        for m in extrair(payload):
            recebido = m["received_at"]
            if recebido and recebido > utcnow():
                recebido = None
            try:
                ticket_id = tickets.criar_ticket(canal, m["texto"], m["cliente"], recebido, m["external_id"])
            except tickets.TicketDuplicado:
                continue  # a Meta reenvia quando não recebe 200 a tempo
            background.add_task(pipeline.processar_ticket, ticket_id)
            novas += 1
        return {"recebidas": novas}  # 200 sempre que a assinatura é válida, para a Meta não reenviar em loop

    @app.post("/webhooks/whatsapp", include_in_schema=False)
    async def whatsapp_receber(request: Request, background: BackgroundTasks):
        return _receber_meta("whatsapp", await request.body(), request.headers.get("x-hub-signature-256"),
                             settings.whatsapp_app_secret, canais.mensagens_whatsapp, background)

    # ---- Instagram Direct (Meta) ----
    @app.get("/webhooks/instagram", include_in_schema=False)
    def instagram_verificacao(
        modo: Optional[str] = Query(default=None, alias="hub.mode"),
        token: Optional[str] = Query(default=None, alias="hub.verify_token"),
        desafio: Optional[str] = Query(default=None, alias="hub.challenge"),
    ):
        esperado = settings.instagram_verify_token
        if not esperado or modo != "subscribe" or not token or not secrets.compare_digest(token, esperado):
            raise HTTPException(status_code=403, detail="verificação recusada")
        return PlainTextResponse(desafio or "")

    @app.post("/webhooks/instagram", include_in_schema=False)
    async def instagram_receber(request: Request, background: BackgroundTasks):
        return _receber_meta("instagram", await request.body(), request.headers.get("x-hub-signature-256"),
                             settings.instagram_app_secret, canais.mensagens_instagram, background)

    # ---- Telas de demonstração dos canais (só fora de produção; DEMO=0 desliga) ----
    if settings.demo_enabled:
        csp_demo = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "connect-src 'self'; base-uri 'none'; form-action 'none'")
        # O apresentador é o atendente e a IA faz o papel do cliente (cliente_simulado). A primeira fala do cliente passa
        # pelo mesmo conversor do canal real e abre o ticket; o resto da conversa continua nele, como numa central de
        # atendimento (uma conversa = um ticket). A resposta do atendente registra a 1ª resposta (SLA).
        conversas = cliente_simulado.Conversas()

        def _fala_do_cliente(conv: cliente_simulado.Conversa, background: BackgroundTasks) -> dict:
            fala = cliente_simulado.proxima_fala(conv)
            if fala["assunto"]:
                conv.assunto = fala["assunto"]
            conv.historico.append(("cliente", fala["mensagem"]))
            conv.encerrada = fala["encerrou"]
            ticket_id, m = None, None
            if not conv.tickets and conv.canal == "email":
                m = demo_email.email_demo_para_mensagem(conv.contato, conv.nome, "atendimento@suaempresa.com.br",
                                                        conv.assunto or "", fala["mensagem"])
            elif not conv.tickets:
                m = demo_chat.mensagem_demo(conv.canal, conv.contato, conv.nome if conv.canal == "whatsapp" else None,
                                            fala["mensagem"])
            if m is not None:  # texto que o canal real ignoraria (curto demais) não vira ticket
                ticket_id = tickets.criar_ticket(conv.canal, m["texto"], m["cliente"], m["received_at"], m["external_id"])
                conv.tickets.append(ticket_id)
                background.add_task(pipeline.processar_ticket, ticket_id)
            return {"texto": fala["mensagem"], "ticket_id": ticket_id, "encerrou": conv.encerrada,
                    "assunto": conv.assunto if conv.canal == "email" else None}

        def _conversa(cid: str) -> cliente_simulado.Conversa:
            conv = conversas.obter(cid)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversa não encontrada (a API reiniciou?)")
            return conv

        @app.get("/demo/cenarios", include_in_schema=False)
        def demo_cenarios():
            return [{"chave": k, "titulo": v[0]} for k, v in cliente_simulado.CENARIOS.items()]

        @app.post("/demo/{canal}/conversas", status_code=201, include_in_schema=False)
        def demo_nova_conversa(canal: str, background: BackgroundTasks, corpo: Optional[ConversaDemoIn] = None):
            if canal not in cliente_simulado.CANAIS:
                raise HTTPException(status_code=404, detail="canal de demonstração inexistente")
            cid, conv = conversas.nova(canal, corpo.cenario if corpo else None)
            mensagem = _fala_do_cliente(conv, background)
            return {"conversa": cid, "cliente": {"nome": conv.nome, "contato": conv.contato},
                    "cenario": cliente_simulado.CENARIOS[conv.cenario][0], "mensagem": mensagem}

        @app.post("/demo/conversas/{cid}/respostas", include_in_schema=False)
        def demo_responder(cid: str, corpo: RespostaDemoIn, background: BackgroundTasks):
            conv = _conversa(cid)
            if conv.encerrada:
                raise HTTPException(status_code=409, detail="o cliente já encerrou a conversa")
            conv.historico.append(("atendente", corpo.texto.strip()))
            for ticket_id in conv.tickets:  # idempotente: só a primeira resposta de cada ticket conta para o prazo
                try:
                    tickets.marcar_respondido(ticket_id)
                except tickets.RespostaAnteriorAoRecebimento:
                    # resposta no mesmo segundo da chegada: o MySQL arredonda o horário de chegada para cima
                    tickets.marcar_respondido(ticket_id, tickets.obter(ticket_id)["received_at"])
                except tickets.TicketNaoEncontrado:
                    pass  # a demo foi zerada no meio da conversa
            return {"mensagem": _fala_do_cliente(conv, background)}

        @app.get("/demo/conversas/{cid}/tickets/{ticket_id}", include_in_schema=False)
        def demo_ticket_da_conversa(cid: str, ticket_id: int):
            if ticket_id not in _conversa(cid).tickets:
                raise HTTPException(status_code=404, detail="ticket não pertence a esta conversa")
            try:
                tk = tickets.obter(ticket_id)
            except tickets.TicketNaoEncontrado:
                raise HTTPException(status_code=404, detail="ticket não encontrado")
            campos = ("ticket_id", "status", "origem", "assunto", "urgencia", "sentimento", "equipe", "resposta_sugerida",
                      "exemplos", "first_response_at")
            return {**{k: tk.get(k) for k in campos}, "sla": {k: tk["sla"][k] for k in ("estado", "prazo_minutos")}}

        @app.get("/demo", include_in_schema=False)
        def demo_inicio():
            return RedirectResponse("/demo/whatsapp")

        @app.get("/demo/email", response_class=HTMLResponse, include_in_schema=False)
        def demo_email_pagina():
            return HTMLResponse(demo_email.PAGINA_DEMO_EMAIL, headers={"Content-Security-Policy": csp_demo})

        @app.post("/demo/email", status_code=202, include_in_schema=False)
        def demo_email_enviar(msg: EmailDemoIn, background: BackgroundTasks):
            convertida = demo_email.email_demo_para_mensagem(msg.de_email, msg.de_nome, msg.para, msg.assunto, msg.corpo)
            if convertida is None:  # remetente no-reply, texto vazio etc.: o leitor IMAP também ignoraria
                return JSONResponse(status_code=400, content={"detail": "e-mail ignorado pelo filtro (remetente automático ou texto vazio)"})
            ticket_id = tickets.criar_ticket("email", convertida["texto"], convertida["cliente"],
                                             convertida["received_at"], convertida["external_id"])
            background.add_task(pipeline.processar_ticket, ticket_id)
            return {"ticket_id": ticket_id, "status": "pendente"}

        @app.get("/demo/{canal}", response_class=HTMLResponse, include_in_schema=False)
        def demo_chat_pagina(canal: str):
            if canal not in demo_chat.PAGINAS:
                raise HTTPException(status_code=404, detail="canal de demonstração inexistente")
            return HTMLResponse(demo_chat.PAGINAS[canal], headers={"Content-Security-Policy": csp_demo})

        @app.post("/demo/{canal}", status_code=202, include_in_schema=False)
        def demo_chat_enviar(canal: str, msg: ChatDemoIn, background: BackgroundTasks):
            if canal not in demo_chat.PAGINAS:
                raise HTTPException(status_code=404, detail="canal de demonstração inexistente")
            ok = msg.remetente.isdigit() and 8 <= len(msg.remetente) <= 15 if canal == "whatsapp" \
                else bool(re.fullmatch(r"[a-z0-9._]{1,30}", msg.remetente))
            if not ok:
                return JSONResponse(status_code=400, content={"detail": "remetente inválido para o canal"})
            m = demo_chat.mensagem_demo(canal, msg.remetente, msg.nome, msg.texto)
            if m is None:
                return JSONResponse(status_code=400, content={"detail": "mensagem ignorada pelo canal (texto curto demais)"})
            ticket_id = tickets.criar_ticket(canal, m["texto"], m["cliente"], m["received_at"], m["external_id"])
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

    @app.get("/dominio", dependencies=[Depends(exigir_chave)])
    def dominio():
        """Valores permitidos na triagem, para o painel montar os formulários de correção."""
        return {"assuntos": ASSUNTOS, "urgencias": URGENCIAS, "sentimentos": SENTIMENTOS, "equipes": EQUIPES,
                "idiomas": IDIOMAS}

    # Painel (HTML/CSS/JS estáticos) servido pela própria API: um único serviço para subir.
    # Montado por último para não sombrear as rotas acima.
    if FRONTEND.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="painel")

    return app


app = create_app()
