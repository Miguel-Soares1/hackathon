"""API HTTP (FastAPI). Webhook único (ADR-001), responde 202 e processa em background (ADR-009)."""
import hashlib
import hmac
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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text

from . import canais, corrections, demo_chat, demo_email, incidents, metrics, midias, pipeline, tickets, usuarios
from .config import get_settings, validar_producao
from .db import get_engine, utcnow
from .domain import ASSUNTOS, EQUIPES, SENTIMENTOS, URGENCIAS
from .idioma import IDIOMAS
from .pagina_envio import PAGINA_ENVIO
from .ratelimit import LimitadorJanela

logger = logging.getLogger(__name__)

CANAIS_MAX = 30
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _token_bearer(authorization: Optional[str]) -> str:
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()
    return ""


def exigir_chave(request: Request, x_api_key: Optional[str] = Header(default=None),
                 authorization: Optional[str] = Header(default=None)) -> None:
    """Acesso às rotas protegidas por um de dois caminhos:
    - painel: sessão de usuário (`Authorization: Bearer <token>`, ADR-018), aberta com usuário e senha;
    - integrações (webhook, canais, scripts): chave no header X-API-Key (threat model T1).
    """
    token = _token_bearer(authorization)
    if token:
        usuario = usuarios.usuario_da_sessao(token)
        if usuario is None:
            raise HTTPException(status_code=401, detail="sessão expirada ou inválida: entre de novo")
        request.state.usuario = usuario
        return
    request.state.usuario = None
    esperada = get_settings().api_key
    if not esperada:
        raise HTTPException(status_code=503, detail="API_KEY não configurada no servidor")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode(), esperada.encode()):
        raise HTTPException(status_code=401, detail="chave de API ausente ou inválida")


class MidiaIn(BaseModel):
    tipo: str = Field(description="'audio' ou 'imagem'")
    mime: str = Field(max_length=100, description="Ex.: audio/ogg, audio/webm, image/jpeg, image/png")
    dados_base64: str = Field(description=f"Arquivo em base64 (até {midias.MAX_BYTES // (1024 * 1024)} MB)")


class MensagemIn(BaseModel):
    canal: str = Field(min_length=2, max_length=CANAIS_MAX)
    texto: str = Field(default="", max_length=4000, description="Obrigatório (3+ caracteres) se não houver mídia.")
    cliente: Optional[str] = Field(default=None, max_length=120)
    midias: list[MidiaIn] = Field(
        default_factory=list, max_length=midias.MAX_MIDIAS,
        description="Opcional (ADR-017): áudios e fotos do cliente; a IA de mídia os transforma em texto.",
    )
    external_id: Optional[str] = Field(
        default=None, max_length=190, description="Opcional: id da mensagem no canal; torna o envio idempotente."
    )
    conversa_id: Optional[str] = Field(
        default=None, max_length=190,
        description="Opcional: identifica o cliente/conversa no canal (telefone, e-mail, id do chat). "
                    "Mensagens com o mesmo conversa_id entram na mesma conversa.",
    )
    received_at: Optional[datetime] = Field(
        default=None, description="Opcional: data/hora original (importação ou simulação). Padrão: agora (UTC)."
    )

    @field_validator("canal")
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

    @model_validator(mode="after")
    def _texto_ou_midia(self):
        self.texto = self.texto.strip()
        if not self.midias and len(self.texto) < 3:
            raise ValueError("envie um texto (3+ caracteres) ou pelo menos uma mídia")
        return self


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


class MensagemChatIn(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)
    autor: Optional[str] = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=200)
    manter_conectado: bool = True


class PrimeiroAdminIn(BaseModel):
    chave_api: str = Field(min_length=1, max_length=200, description="API_KEY do servidor: prova que é o dono")
    usuario: str = Field(min_length=3, max_length=60)
    nome: str = Field(min_length=1, max_length=120)
    senha: str = Field(min_length=1, max_length=200)


class TrocaSenhaIn(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=200)
    nova_senha: str = Field(min_length=1, max_length=200)


class UsuarioNovoIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=60)
    nome: str = Field(min_length=1, max_length=120)
    senha: str = Field(min_length=1, max_length=200)
    papel: str = "atendente"


class UsuarioAlteracaoIn(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=120)
    papel: Optional[str] = None
    ativo: Optional[bool] = None
    senha: Optional[str] = Field(default=None, max_length=200, description="redefine a senha do usuário")


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
        title="NEXUS", version="1.0.0", lifespan=lifespan,
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

    # ---- Login do painel e administração de usuários (ADR-018) ----
    limitador_login = LimitadorJanela(10, 200)  # tentativas por IP e no total, por minuto

    def _conferir_limite(request: Request) -> None:
        permitido, espera = limitador_login.permitir(ip_do_cliente(request, settings.trust_proxy))
        if not permitido:
            raise HTTPException(status_code=429, detail="muitas tentativas; aguarde um minuto",
                                headers={"Retry-After": str(espera)})

    def _sessao(usuario: dict, lembrar: bool) -> dict:
        token, expira = usuarios.abrir_sessao(usuario["id"], lembrar)
        return {"token": token, "expira_em": expira, "usuario": usuario}

    def usuario_logado(request: Request, _: None = Depends(exigir_chave)) -> dict:
        if not getattr(request.state, "usuario", None):
            raise HTTPException(status_code=401, detail="entre com usuário e senha")
        return request.state.usuario

    def exigir_admin(usuario: dict = Depends(usuario_logado)) -> dict:
        if usuario["papel"] != "admin":
            raise HTTPException(status_code=403, detail="somente administradores")
        return usuario

    @app.get("/auth/estado")
    def auth_estado():
        """Público: diz se ainda falta criar o primeiro administrador."""
        return {"precisa_configurar": not usuarios.existe_algum()}

    @app.post("/auth/primeiro-admin", status_code=201)
    def auth_primeiro_admin(corpo: PrimeiroAdminIn, request: Request):
        """Cria o 1º administrador. Só funciona com o banco sem usuários e com a API_KEY do servidor."""
        _conferir_limite(request)
        esperada = settings.api_key
        if not esperada or not secrets.compare_digest(corpo.chave_api.encode(), esperada.encode()):
            raise HTTPException(status_code=401, detail="chave de API do servidor incorreta")
        if usuarios.existe_algum():
            raise HTTPException(status_code=409, detail="o administrador já foi criado; entre com usuário e senha")
        try:
            u = usuarios.criar(corpo.usuario, corpo.nome, corpo.senha, "admin")
        except (usuarios.UsuarioInvalido, usuarios.UsuarioDuplicado) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _sessao(u, True)

    @app.post("/auth/login")
    def auth_login(corpo: LoginIn, request: Request):
        _conferir_limite(request)
        u = usuarios.autenticar(corpo.usuario, corpo.senha)
        if u is None:
            raise HTTPException(status_code=401, detail="usuário ou senha incorretos")
        return _sessao(u, corpo.manter_conectado)

    @app.post("/auth/logout", status_code=204)
    def auth_logout(authorization: Optional[str] = Header(default=None)):
        usuarios.encerrar_sessao(_token_bearer(authorization))

    @app.get("/auth/eu")
    def auth_eu(usuario: dict = Depends(usuario_logado)):
        return {k: v for k, v in usuario.items() if k != "token_hash"}

    @app.post("/auth/senha", status_code=204)
    def auth_trocar_senha(corpo: TrocaSenhaIn, request: Request, usuario: dict = Depends(usuario_logado)):
        _conferir_limite(request)
        try:
            usuarios.trocar_propria_senha(usuario["id"], corpo.senha_atual, corpo.nova_senha, usuario["token_hash"])
        except usuarios.UsuarioInvalido as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/usuarios", dependencies=[Depends(exigir_admin)])
    def listar_usuarios():
        return usuarios.listar()

    @app.post("/usuarios", status_code=201, dependencies=[Depends(exigir_admin)])
    def criar_usuario(corpo: UsuarioNovoIn):
        try:
            return usuarios.criar(corpo.usuario, corpo.nome, corpo.senha, corpo.papel)
        except usuarios.UsuarioDuplicado as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except usuarios.UsuarioInvalido as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.patch("/usuarios/{usuario_id}", dependencies=[Depends(exigir_admin)])
    def alterar_usuario(usuario_id: int, corpo: UsuarioAlteracaoIn):
        try:
            return usuarios.alterar(usuario_id, corpo.nome, corpo.papel, corpo.ativo, corpo.senha)
        except usuarios.UsuarioNaoEncontrado:
            raise HTTPException(status_code=404, detail="usuário não encontrado")
        except usuarios.UsuarioInvalido as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webhook/mensagens", status_code=202, dependencies=[Depends(exigir_chave)])
    def webhook(msg: MensagemIn, background: BackgroundTasks):
        try:
            anexos = [midias.validar(m.tipo, m.mime, m.dados_base64) for m in msg.midias]
        except midias.MidiaInvalida as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            ticket_id, novo, msg_id = tickets.receber_mensagem(
                msg.canal, msg.texto, msg.cliente, msg.received_at, msg.external_id, msg.conversa_id, anexos
            )
        except tickets.TicketDuplicado as dup:
            return {"ticket_id": dup.ticket_id, "status": "duplicado"}
        if not novo:
            if anexos:  # áudio/foto na continuação da conversa: a IA lê e o texto entra na mensagem
                background.add_task(midias.processar, ticket_id, msg.texto, msg_id)
            return {"ticket_id": ticket_id, "status": "anexada"}
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
                ticket_id, novo, _ = tickets.receber_mensagem(
                    canal, m["texto"], m["cliente"], recebido, m["external_id"], m.get("conversa_id")
                )
            except tickets.TicketDuplicado:
                continue  # a Meta reenvia quando não recebe 200 a tempo
            if novo:
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
        # A tela do cliente acompanha a própria conversa: a resposta sugerida pela IA (resposta automática da demo) e as
        # respostas que o atendente enviar pelo painel. Só quem enviou a mensagem tem a senha do ticket (HMAC com um
        # segredo que muda a cada subida da API); a classificação nunca sai por aqui.
        segredo_demo = secrets.token_bytes(32)

        def _senha_conversa(ticket_id: int) -> str:
            return hmac.new(segredo_demo, str(ticket_id).encode(), hashlib.sha256).hexdigest()[:32]

        def _enviado(ticket_id: int, status: str) -> dict:
            return {"ticket_id": ticket_id, "status": status, "senha": _senha_conversa(ticket_id)}

        @app.get("/demo/conversa/{ticket_id}", include_in_schema=False)
        def demo_conversa(ticket_id: int, senha: str = Query("", max_length=64), depois_de: int = Query(0, ge=0)):
            if not hmac.compare_digest(senha, _senha_conversa(ticket_id)):
                raise HTTPException(status_code=404, detail="conversa não encontrada")
            try:
                t = tickets.obter(ticket_id)
                msgs = tickets.mensagens(ticket_id, depois_de)
            except tickets.TicketNaoEncontrado:
                raise HTTPException(status_code=404, detail="conversa não encontrada")
            resposta = t.get("resposta_sugerida") if t.get("status") != "pendente" else None
            atendente = [{"id": m["id"], "texto": m["texto"], "autor": m["autor"]} for m in msgs if m["direcao"] == "saida"]
            return {"respondida": bool(resposta), "resposta": resposta, "equipe": t.get("equipe") if resposta else None,
                    "atendente": atendente, "ultimo_id": max([m["id"] for m in msgs], default=depois_de)}

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
            ticket_id, novo, _ = tickets.receber_mensagem("email", convertida["texto"], convertida["cliente"],
                                                       convertida["received_at"], convertida["external_id"],
                                                       convertida.get("conversa_id"))
            if not novo:
                return _enviado(ticket_id, "anexada")
            background.add_task(pipeline.processar_ticket, ticket_id)
            return _enviado(ticket_id, "pendente")

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
            ticket_id, novo, _ = tickets.receber_mensagem(canal, m["texto"], m["cliente"], m["received_at"],
                                                       m["external_id"], m.get("conversa_id"))
            if not novo:
                return _enviado(ticket_id, "anexada")
            background.add_task(pipeline.processar_ticket, ticket_id)
            return _enviado(ticket_id, "pendente")


    @app.get("/tickets", dependencies=[Depends(exigir_chave)])
    def listar_tickets(limite: int = Query(100, ge=1, le=1000), apenas_abertos: bool = False):
        return tickets.listar(limite=limite, apenas_abertos=apenas_abertos)

    @app.get("/tickets/{ticket_id}", dependencies=[Depends(exigir_chave)])
    def obter_ticket(ticket_id: int):
        try:
            return tickets.obter(ticket_id)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")

    @app.get("/tickets/{ticket_id}/midias/{midia_id}", dependencies=[Depends(exigir_chave)])
    def obter_midia(ticket_id: int, midia_id: int):
        """Arquivo original (áudio/foto) para o atendente ouvir ou ver no painel."""
        arquivo = midias.obter_arquivo(ticket_id, midia_id)
        if arquivo is None:
            raise HTTPException(status_code=404, detail="mídia não encontrada")
        mime, dados = arquivo
        # Arquivo enviado pelo cliente: nunca executa nada no navegador.
        return Response(dados, media_type=mime, headers={
            "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "private, max-age=300",
        })

    @app.post("/tickets/{ticket_id}/resposta", dependencies=[Depends(exigir_chave)])
    def responder(ticket_id: int, corpo: Optional[RespostaIn] = None):
        quando = corpo.respondido_em if corpo else None
        try:
            return tickets.marcar_respondido(ticket_id, quando)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")
        except tickets.RespostaAnteriorAoRecebimento:
            raise HTTPException(status_code=400, detail="respondido_em anterior ao recebimento do ticket")

    @app.get("/tickets/{ticket_id}/mensagens", dependencies=[Depends(exigir_chave)])
    def listar_mensagens(ticket_id: int, depois_de: int = Query(0, ge=0)):
        """Conversa do ticket. Use `depois_de=<último id visto>` para buscar só as novas (polling do chat do cliente)."""
        try:
            return tickets.mensagens(ticket_id, depois_de)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")

    @app.post("/tickets/{ticket_id}/mensagens", status_code=201, dependencies=[Depends(exigir_chave)])
    def enviar_mensagem(ticket_id: int, corpo: MensagemChatIn, request: Request):
        """Resposta do atendente na conversa (chat). Registra a 1ª resposta para o SLA."""
        if not corpo.texto.strip():
            raise HTTPException(status_code=400, detail="mensagem vazia")
        logado = getattr(request.state, "usuario", None)
        autor = logado["nome"] if logado else corpo.autor  # pelo painel, assina quem está logado (ADR-018)
        try:
            return tickets.responder_chat(ticket_id, corpo.texto, autor)
        except tickets.TicketNaoEncontrado:
            raise HTTPException(status_code=404, detail="ticket não encontrado")

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
