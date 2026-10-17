"""Adaptadores de canais reais: WhatsApp Cloud API (Meta) e e-mail. Funções puras, sem I/O."""
import hashlib
import hmac
import re
from email import message_from_bytes, policy
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timezone
from typing import Optional

TEXTO_MAX = 4000


# ---------------- WhatsApp ----------------
def assinatura_valida(corpo: bytes, cabecalho: Optional[str], segredo: str) -> bool:
    """Valida X-Hub-Signature-256 ('sha256=<hmac>') em tempo constante. Sem segredo => sempre inválida."""
    if not segredo or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho[len("sha256="):])


def _lista(v) -> list:
    return v if isinstance(v, list) else []


def mensagens_whatsapp(payload: dict) -> list[dict]:
    """Extrai mensagens de TEXTO do payload da Meta. Ignora status de entrega e mídia.

    Retorna [{external_id, cliente, texto, received_at}]. Tolera payloads malformados (retorna []).
    """
    saida: list[dict] = []
    if not isinstance(payload, dict):
        return saida
    for entry in _lista(payload.get("entry")):
        for change in _lista(entry.get("changes") if isinstance(entry, dict) else None):
            valor = change.get("value") if isinstance(change, dict) else None
            if not isinstance(valor, dict):
                continue
            nomes = {}
            for c in _lista(valor.get("contacts")):
                if isinstance(c, dict):
                    nomes[c.get("wa_id")] = ((c.get("profile") or {}).get("name"))
            for m in _lista(valor.get("messages")):
                if not isinstance(m, dict) or m.get("type") != "text":
                    continue
                corpo = ((m.get("text") or {}).get("body") or "").strip()
                mid, de = m.get("id"), m.get("from")
                if len(corpo) < 3 or not mid or not de:
                    continue
                try:
                    recebido = datetime.fromtimestamp(int(m["timestamp"]), tz=timezone.utc).replace(tzinfo=None)
                except (KeyError, ValueError, TypeError, OverflowError, OSError):
                    recebido = None
                nome = nomes.get(de)
                saida.append({
                    "external_id": str(mid)[:190],
                    "conversa_id": str(de)[:190],
                    "cliente": (f"{nome} ({de})" if nome else str(de))[:120],
                    "texto": corpo[:TEXTO_MAX],
                    "received_at": recebido,
                })
    return saida


# ---------------- E-mail ----------------
_REMETENTE_AUTOMATICO = re.compile(r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster|notifications?@|bounce)", re.I)
_CITACAO = re.compile(r"^(>|On .+ wrote:|Em .+ escreveu:|-{2,}\s*(Original Message|Mensagem original))", re.I)


def e_automatico(msg: Message) -> bool:
    """Descarta bounces, respostas automáticas, listas e remetentes no-reply (evita loops e ruído)."""
    auto = (msg.get("Auto-Submitted") or "no").strip().lower()
    if auto != "no":
        return True
    if (msg.get("Precedence") or "").strip().lower() in ("bulk", "list", "junk", "auto_reply"):
        return True
    if msg.get("List-Id") or msg.get("List-Unsubscribe") or msg.get("X-Autoreply") or msg.get("X-Autorespond"):
        return True
    return bool(_REMETENTE_AUTOMATICO.search(parseaddr(msg.get("From") or "")[1]))


def _corpo_texto(msg: Message) -> str:
    parte = msg.get_body(preferencelist=("plain",))
    if parte is not None:
        return parte.get_content()
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.get_content()))
    return ""


def _sem_citacao(texto: str) -> str:
    linhas = []
    for linha in texto.splitlines():
        if _CITACAO.match(linha.strip()):
            break
        linhas.append(linha)
    return "\n".join(linhas).strip()


def email_para_mensagem(bruto: bytes) -> Optional[dict]:
    """Converte um e-mail bruto em {external_id, cliente, texto, received_at} ou None se deve ser ignorado."""
    msg = message_from_bytes(bruto, policy=policy.default)
    if e_automatico(msg):
        return None
    remetente = parseaddr(str(msg.get("From") or ""))[1].lower()
    mid = str(msg.get("Message-ID") or "").strip()
    if not remetente or not mid:
        return None
    assunto = re.sub(r"\s+", " ", str(msg.get("Subject") or "")).strip()
    corpo = _sem_citacao(_corpo_texto(msg))
    texto = (f"{assunto}\n\n{corpo}" if assunto and corpo else assunto or corpo).strip()
    if len(texto) < 3:
        return None
    try:
        recebido = parsedate_to_datetime(str(msg.get("Date")))
        recebido = recebido.astimezone(timezone.utc).replace(tzinfo=None) if recebido.tzinfo else recebido
    except (TypeError, ValueError):
        recebido = None
    return {"external_id": mid[:190], "conversa_id": remetente[:190], "cliente": remetente[:120], "texto": texto[:TEXTO_MAX], "received_at": recebido}
