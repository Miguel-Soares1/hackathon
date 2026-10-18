"""HTTPS das telas de demo no celular (certificado autoassinado + repasse 8443 -> API)."""
import asyncio
import ssl

from cryptography import x509

from triagem import demo_celular, https_celular


def test_certificado_cobre_os_ips_e_e_reaproveitado(tmp_path):
    cert, chave = https_celular.gerar_certificado(["192.168.137.1", "10.0.50.155"], tmp_path)
    san = x509.load_pem_x509_certificate(cert.read_bytes()).extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert {str(ip) for ip in san.get_values_for_type(x509.IPAddress)} >= {"192.168.137.1", "10.0.50.155", "127.0.0.1"}
    antes = cert.read_bytes()
    https_celular.gerar_certificado(["192.168.137.1"], tmp_path)  # IPs já cobertos: não gera outro
    assert cert.read_bytes() == antes
    https_celular.gerar_certificado(["192.168.0.20"], tmp_path)  # IP novo (outra rede): gera de novo
    assert cert.read_bytes() != antes and chave.exists()


def test_repasse_https_entrega_a_requisicao_a_api_e_devolve_a_resposta(tmp_path):
    async def cenario():
        async def api_falsa(leitor, escritor):
            pedido = await leitor.readuntil(b"\r\n\r\n")
            corpo = b"ok:" + pedido.split(b"\r\n")[0]
            escritor.write(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s" % (len(corpo), corpo))
            await escritor.drain()
            escritor.close()
        api = await asyncio.start_server(api_falsa, "127.0.0.1", 0)
        porta_api = api.sockets[0].getsockname()[1]
        cert, chave = https_celular.gerar_certificado(["127.0.0.1"], tmp_path)
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(cert, chave)
        relay = await asyncio.start_server(lambda r, w: https_celular._atender(r, w, porta_api), "127.0.0.1", 0, ssl=ctx)
        porta_https = relay.sockets[0].getsockname()[1]
        cliente_ctx = ssl.create_default_context(cafile=str(cert))  # o celular, depois de aceitar o certificado
        leitor, escritor = await asyncio.open_connection("127.0.0.1", porta_https, ssl=cliente_ctx, server_hostname="127.0.0.1")
        escritor.write(b"POST /demo/whatsapp HTTP/1.1\r\nHost: 192.168.137.1:8443\r\n\r\n")
        await escritor.drain()
        resposta = await leitor.read()
        escritor.close()
        relay.close(); api.close()
        return resposta
    resposta = asyncio.run(cenario())
    assert resposta.startswith(b"HTTP/1.1 200 OK") and resposta.endswith(b"ok:POST /demo/whatsapp HTTP/1.1")


def test_pagina_do_celular_usa_https_quando_ligado(monkeypatch):
    monkeypatch.setattr(demo_celular, "ip_da_rede", lambda: "192.168.137.1")
    monkeypatch.setattr(demo_celular, "outros_ips", lambda: ["192.168.137.1"])
    com = demo_celular.pagina("localhost:8000", 8000, 8443)
    sem = demo_celular.pagina("localhost:8000", 8000, None)
    assert "https://192.168.137.1:8443/demo/whatsapp" in com and "Avançado" in com
    assert "http://192.168.137.1:8000/demo/whatsapp" in sem and "gravar áudio" in sem


def test_porta_ativa_sem_servidor():
    assert https_celular.porta_ativa(1) is None
