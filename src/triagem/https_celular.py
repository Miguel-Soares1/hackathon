"""HTTPS para as telas de demo no celular (só em desenvolvimento).

O navegador do celular só libera o microfone (gravar áudio) em páginas seguras: `https://` ou o próprio `localhost`.
Aberta pelo IP do notebook em `http://`, a tela de demo envia texto e foto, mas não grava áudio. Este módulo:
- gera um certificado autoassinado para os IPs do notebook (pasta `.certs/`, fora do git) e o renova quando os IPs
  mudam (ex.: ligou o hotspot);
- escuta HTTPS em 0.0.0.0:8443 e repassa cada conexão, sem alterar nada, para a API em 127.0.0.1:8000.
Na primeira vez o celular avisa que a conexão "não é particular" (o certificado é do próprio notebook): toque em
Avançado -> Continuar. Uso: `python scripts/https_celular.py` (o `scripts\\iniciar.ps1 -Celular` já liga).
"""
import asyncio
import datetime as dt
import ipaddress
import logging
import socket
import ssl
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PORTA_HTTPS = 8443
PORTA_API = 8000
PASTA_CERTS = Path(__file__).resolve().parents[2] / ".certs"


def ips_do_notebook() -> list[str]:
    """IPv4 privados do notebook (inclui o do hotspot do Windows, se ligado)."""
    from .demo_celular import ip_da_rede, outros_ips
    ips = set(outros_ips())
    principal = ip_da_rede()
    if principal:
        ips.add(principal)
    return sorted(ips)


def _cobre(cert_path: Path, ips: list[str]) -> bool:
    """O certificado existente ainda vale e cobre todos os IPs atuais?"""
    from cryptography import x509
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        cobertos = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
        valido = cert.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False
    return valido and set(ips) <= cobertos


def gerar_certificado(ips: list[str], pasta: Path = PASTA_CERTS) -> tuple[Path, Path]:
    """Certificado autoassinado para localhost e os IPs dados (reaproveita o anterior se ainda servir)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    pasta.mkdir(parents=True, exist_ok=True)
    cert_path, chave_path = pasta / "celular.crt", pasta / "celular.key"
    if cert_path.exists() and chave_path.exists() and _cobre(cert_path, ips):
        return cert_path, chave_path
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Demo NEXUS (notebook)")])
    agora = dt.datetime.now(dt.timezone.utc)
    alternativos = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    alternativos += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    cert = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5)).not_valid_after(agora + dt.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(alternativos), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    chave_path.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, chave_path


def porta_ativa(porta: int = PORTA_HTTPS) -> Optional[int]:
    """Porta do HTTPS do celular se ele estiver ligado neste notebook; senão None."""
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.3):
            return porta
    except OSError:
        return None


async def _bombear(origem: asyncio.StreamReader, destino: asyncio.StreamWriter) -> None:
    try:
        while dados := await origem.read(65536):
            destino.write(dados)
            await destino.drain()
    except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError, OSError):
        pass
    finally:
        try:
            destino.close()
        except Exception:  # noqa: BLE001 - conexão já caiu do outro lado
            pass


async def _atender(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter, porta_api: int) -> None:
    try:
        api_leitor, api_escritor = await asyncio.open_connection("127.0.0.1", porta_api)
    except OSError:
        escritor.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\n\r\n"
                       b"A API nao esta rodando na porta 8000 do notebook.")
        await escritor.drain()
        escritor.close()
        return
    await asyncio.gather(_bombear(leitor, api_escritor), _bombear(api_leitor, escritor))


async def servir(porta_https: int = PORTA_HTTPS, porta_api: int = PORTA_API) -> None:
    ips = ips_do_notebook()
    cert, chave = gerar_certificado(ips)
    contexto = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    contexto.load_cert_chain(cert, chave)
    servidor = await asyncio.start_server(lambda r, w: _atender(r, w, porta_api), "0.0.0.0", porta_https, ssl=contexto)
    for ip in ips:
        print(f"Celular (HTTPS, grava áudio): https://{ip}:{porta_https}/demo")
    print("Na 1ª vez o celular avisa que a conexão não é particular: toque em Avançado -> Continuar.")
    async with servidor:
        await servidor.serve_forever()


def main() -> None:
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)  # celular recusando o certificado não é erro nosso
    try:
        asyncio.run(servir())
    except KeyboardInterrupt:
        pass
