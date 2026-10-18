"""Página /demo/celular: QR codes para abrir as telas de demonstração no celular (só em desenvolvimento).

O celular precisa estar na mesma rede Wi-Fi do notebook e a API precisa escutar na rede (`--host 0.0.0.0`,
ou `scripts\\iniciar.ps1 -Celular`). Quem abre a página no notebook por `localhost` recebe o endereço do notebook
na rede local, que é o que o celular consegue acessar.
"""
import html
import ipaddress
import re
import socket
from typing import Optional

import qrcode
import qrcode.image.svg

CANAIS = (("whatsapp", "WhatsApp"), ("instagram", "Instagram"), ("email", "E-mail"))
_LOCAIS = {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}
HOTSPOT_WINDOWS = "192.168.137.1"  # endereço fixo do notebook quando o hotspot móvel do Windows está ligado


def ip_da_rede() -> Optional[str]:
    """IPv4 do notebook que o celular alcança. Não envia nenhum pacote.

    Com o hotspot do Windows ligado, o celular conectado nele só enxerga o notebook em 192.168.137.1, mesmo que a
    rota padrão saia por outra interface (cabo ou outro Wi-Fi). Sem hotspot, vale a interface da rota padrão.
    """
    if HOTSPOT_WINDOWS in outros_ips():
        return HOTSPOT_WINDOWS
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ipaddress.ip_address(ip).is_loopback else ip


def outros_ips() -> list[str]:
    """Demais IPv4 privados do notebook (ex.: hotspot do Windows, 192.168.137.1)."""
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return []
    return sorted(ip for ip in ips if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback)


def base_para_celular(host_header: str, porta_padrao: int, porta_https: Optional[int] = None) -> tuple[str, bool]:
    """Endereço que o celular deve abrir e se ele foi descoberto (True) ou é o mesmo usado no navegador (False).

    Com o HTTPS do celular ligado (`porta_https`, ver https_celular.py), o endereço é https: só assim o navegador do
    celular libera o microfone para gravar áudio.
    """
    host, _, porta = host_header.rpartition(":") if re.search(r":\d+$", host_header) else (host_header, "", "")
    porta = porta or str(porta_padrao)
    if host.lower() in _LOCAIS:
        ip = ip_da_rede()
        if ip:
            return (f"https://{ip}:{porta_https}" if porta_https else f"http://{ip}:{porta}"), True
    if porta_https:
        return f"https://{host}:{porta_https}", False
    return f"http://{host_header}", False


def qr_svg(texto: str) -> str:
    q = qrcode.QRCode(border=2, image_factory=qrcode.image.svg.SvgPathImage)
    q.add_data(texto)
    q.make(fit=True)
    svg = q.make_image().to_string(encoding="unicode")
    return re.sub(r'\swidth="[^"]*" height="[^"]*"', "", svg, count=1)  # tamanho vem do CSS


def pagina(host_header: str, porta_padrao: int, porta_https: Optional[int] = None) -> str:
    base, descoberto = base_para_celular(host_header, porta_padrao, porta_https)
    cartoes = "".join(
        f'<a class="cartao" href="/demo/{c}"><div class="qr">{qr_svg(f"{base}/demo/{c}")}</div>'
        f"<b>{nome}</b><code>{html.escape(base)}/demo/{c}</code></a>"
        for c, nome in CANAIS
    )
    esquema = base.split("://", 1)[0]
    extras = [ip for ip in outros_ips() if f"//{ip}:" not in base]
    dica_extra = (
        "<li>Se não abrir, tente outro endereço do notebook: "
        + ", ".join(f"<code>{esquema}://{html.escape(ip)}:{html.escape(base.rsplit(':', 1)[-1])}/demo</code>" for ip in extras)
        + "</li>"
        if extras else ""
    )
    if porta_https:
        dica_extra += ("<li><b>Primeira vez no celular:</b> ele avisa que a conexão não é particular (o certificado é do "
                       "próprio notebook). Toque em <b>Avançado → Continuar</b>. É isso que libera o microfone para gravar áudio.</li>")
    else:
        dica_extra += ("<li>Para <b>gravar áudio</b> pelo celular, ligue o HTTPS: <code>scripts\\iniciar.ps1 -Celular</code> "
                       "(ou <code>python scripts/https_celular.py</code>) e recarregue esta página. Sem ele, texto e foto "
                       "funcionam, mas o navegador do celular bloqueia o microfone.</li>")
    aviso = "" if descoberto or host_header.split(":")[0].lower() not in _LOCAIS else (
        '<p class="alerta">Não encontrei o endereço do notebook na rede. Conecte-o ao Wi-Fi e recarregue a página.</p>'
    )
    return _PAGINA.replace("__CARTOES__", cartoes).replace("__AVISO__", aviso).replace("__EXTRA__", dica_extra)


_PAGINA = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Abrir no celular · demonstração</title>
<style>
  :root { --bg:#eef1f4; --card:#fff; --tx:#16202e; --mu:#5e6b7e; --bd:#dbe1e8; --er:#c5221f; --ers:#fce8e6; --pr:#0f8f6f; color-scheme: light dark; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0f141b; --card:#18202b; --tx:#e6ebf3; --mu:#98a4b8; --bd:#2a3442; --er:#f28b82; --ers:#3d2322; --pr:#22b38a; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--tx); font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:20px 16px; }
  main { max-width:900px; margin:0 auto; }
  h1 { font-size:22px; margin:0 0 4px; } p { margin:0 0 16px; color:var(--mu); }
  .grade { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:14px; }
  .cartao { background:var(--card); border:1px solid var(--bd); border-radius:16px; padding:16px; text-align:center; color:inherit; text-decoration:none; display:flex; flex-direction:column; gap:8px; align-items:center; }
  .qr { background:#fff; border-radius:10px; padding:6px; width:100%; max-width:220px; }
  .qr svg { display:block; width:100%; height:auto; }
  .qr path { fill:#000; }
  code { font-size:12px; color:var(--mu); word-break:break-all; }
  ol { color:var(--mu); padding-left:20px; } li { margin:4px 0; }
  .alerta { color:var(--er); background:var(--ers); padding:10px 14px; border-radius:10px; }
  a.voltar { color:var(--pr); font-weight:600; }
</style>
</head>
<body>
<main>
  <h1>Abrir a demonstração no celular</h1>
  <p>Aponte a câmera do celular para o QR do canal. O celular vira o cliente; as mensagens chegam no painel do notebook.</p>
  __AVISO__
  <div class="grade">__CARTOES__</div>
  <ol>
    <li>Celular e notebook na <b>mesma rede Wi-Fi</b> (ou o celular no hotspot do notebook).</li>
    <li>A API precisa ter subido para a rede: <code>scripts\iniciar.ps1 -Celular</code> (ou uvicorn com <code>--host 0.0.0.0</code>).</li>
    <li>Se o Windows perguntar, permita o Python no firewall em <b>redes privadas</b>.</li>
    __EXTRA__
  </ol>
  <p><a class="voltar" href="/demo/whatsapp">Voltar ao simulador</a></p>
</main>
</body>
</html>
"""
