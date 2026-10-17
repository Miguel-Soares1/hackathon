"""Leitor de e-mail por IMAP (canal 'email'). Processo separado: lê a caixa e envia ao webhook da API.

Uso:  python -m triagem.email_imap          (laço contínuo)
      python -m triagem.email_imap --uma-vez (uma varredura e sai)
Variáveis: IMAP_HOST, IMAP_PORT(993), IMAP_USER, IMAP_PASSWORD (senha de app), IMAP_FOLDER(INBOX),
           IMAP_POLL_SECONDS(30), API_URL(http://api:8000), API_KEY.
"""
import imaplib
import logging
import os
import sys
import time
from typing import Callable, Optional

import httpx

from .canais import email_para_mensagem

logger = logging.getLogger("triagem.email")
MAX_POR_VARREDURA = 50


def varrer_caixa(imap, enviar: Callable[[dict], bool]) -> dict:
    """Processa e-mails NÃO LIDOS. Marca como lido só o que foi entregue (ou ignorado de propósito).

    `enviar(msg)` devolve True se a API aceitou (inclusive duplicado). Em falha, o e-mail continua
    não lido e será tentado de novo na próxima varredura.
    """
    resumo = {"enviados": 0, "ignorados": 0, "falhas": 0}
    tipo, dados = imap.search(None, "UNSEEN")
    if tipo != "OK" or not dados or not dados[0]:
        return resumo
    for num in dados[0].split()[:MAX_POR_VARREDURA]:
        tipo, partes = imap.fetch(num, "(BODY.PEEK[])")
        if tipo != "OK" or not partes or not isinstance(partes[0], tuple):
            resumo["falhas"] += 1
            continue
        try:
            msg = email_para_mensagem(partes[0][1])
        except Exception:  # e-mail malformado não pode travar a fila
            logger.exception("e-mail ilegível; marcado como lido")
            msg = None
        if msg is None:
            resumo["ignorados"] += 1
        elif enviar(msg):
            resumo["enviados"] += 1
        else:
            resumo["falhas"] += 1
            continue
        imap.store(num, "+FLAGS", "\\Seen")
    return resumo


def criar_enviador(api_url: str, api_key: str, cliente_http: Optional[httpx.Client] = None) -> Callable[[dict], bool]:
    http = cliente_http or httpx.Client(timeout=10)

    def enviar(msg: dict) -> bool:
        corpo = {"canal": "email", "texto": msg["texto"], "cliente": msg["cliente"], "external_id": msg["external_id"]}
        if msg.get("received_at"):
            corpo["received_at"] = msg["received_at"].isoformat()
        try:
            r = http.post(f"{api_url.rstrip('/')}/webhook/mensagens", json=corpo, headers={"X-API-Key": api_key})
        except httpx.HTTPError as exc:
            logger.warning("API indisponível: %s", type(exc).__name__)
            return False
        if r.status_code == 202:
            return True
        logger.warning("API recusou o e-mail (HTTP %s)", r.status_code)
        return r.status_code == 400  # mensagem inválida nunca vai passar: não repetir para sempre

    return enviar


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host, user, senha = os.getenv("IMAP_HOST", ""), os.getenv("IMAP_USER", ""), os.getenv("IMAP_PASSWORD", "")
    if not (host and user and senha):
        logger.error("Defina IMAP_HOST, IMAP_USER e IMAP_PASSWORD.")
        return 2
    porta, pasta = int(os.getenv("IMAP_PORT", "993")), os.getenv("IMAP_FOLDER", "INBOX")
    intervalo = int(os.getenv("IMAP_POLL_SECONDS", "30"))
    enviar = criar_enviador(os.getenv("API_URL", "http://api:8000"), os.getenv("API_KEY", ""))
    uma_vez = "--uma-vez" in argv
    while True:
        try:
            with imaplib.IMAP4_SSL(host, porta) as imap:
                imap.login(user, senha)
                imap.select(pasta)
                resumo = varrer_caixa(imap, enviar)
            if any(resumo.values()):
                logger.info("varredura: %s", resumo)
        except (imaplib.IMAP4.error, OSError) as exc:
            logger.warning("falha de conexão IMAP (%s); tentando de novo", type(exc).__name__)
            if uma_vez:
                return 1
        if uma_vez:
            return 0
        time.sleep(intervalo)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
