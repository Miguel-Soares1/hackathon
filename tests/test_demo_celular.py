"""Página /demo/celular: QR codes para abrir as telas de demo no celular."""
from fastapi.testclient import TestClient

from triagem import demo_celular


def _cliente(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from triagem.api import create_app
    return TestClient(create_app())


def test_localhost_vira_o_ip_do_notebook_na_rede(monkeypatch):
    # Arrange
    monkeypatch.setattr(demo_celular, "ip_da_rede", lambda: "192.168.0.10")
    # Act
    base, descoberto = demo_celular.base_para_celular("localhost:8000", 8000)
    # Assert
    assert (base, descoberto) == ("http://192.168.0.10:8000", True)


def test_endereco_ja_da_rede_e_mantido(monkeypatch):
    monkeypatch.setattr(demo_celular, "ip_da_rede", lambda: "192.168.0.10")
    assert demo_celular.base_para_celular("10.0.0.5:9000", 8000) == ("http://10.0.0.5:9000", False)
    assert demo_celular.base_para_celular("127.0.0.1", 8123) == ("http://192.168.0.10:8123", True)


def test_sem_rede_fica_o_endereco_local(monkeypatch):
    monkeypatch.setattr(demo_celular, "ip_da_rede", lambda: None)
    assert demo_celular.base_para_celular("localhost:8000", 8000) == ("http://localhost:8000", False)


def test_qr_e_svg_sem_tamanho_fixo():
    svg = demo_celular.qr_svg("http://192.168.0.10:8000/demo/whatsapp")
    assert svg.startswith("<svg") and "<path" in svg and 'width="' not in svg.split(">", 1)[0]


def test_pagina_tem_um_qr_por_canal_com_o_ip_da_rede(monkeypatch):
    # Arrange
    monkeypatch.setattr(demo_celular, "ip_da_rede", lambda: "192.168.0.10")
    monkeypatch.setattr(demo_celular, "outros_ips", lambda: [])
    c = _cliente(monkeypatch, API_KEY="k")
    # Act
    r = c.get("/demo/celular", headers={"host": "localhost:8000"})
    # Assert
    assert r.status_code == 200 and "Content-Security-Policy" in r.headers
    assert r.text.count("<svg") == 3
    for canal in ("whatsapp", "instagram", "email"):
        assert f"http://192.168.0.10:8000/demo/{canal}" in r.text


def test_host_malicioso_e_escapado(monkeypatch):
    c = _cliente(monkeypatch, API_KEY="k")
    r = c.get("/demo/celular", headers={"host": "x<script>"})
    assert r.status_code == 200 and "<script>" not in r.text


def test_telas_de_demo_tem_layout_de_celular_e_link_para_os_qr(monkeypatch):
    c = _cliente(monkeypatch, API_KEY="k")
    for canal in ("whatsapp", "instagram", "email"):
        html = c.get(f"/demo/{canal}").text
        assert "max-width: 520px" in html and 'href="/demo/celular"' in html, canal


def test_pagina_do_celular_desligada_em_producao(monkeypatch):
    c = _cliente(monkeypatch, ENVIRONMENT="production", API_KEY="x" * 32, DASHBOARD_PASSWORD="senha-forte-123",
                 DATABASE_URL="mysql+pymysql://u:p@127.0.0.1:3306/hackathon_test")
    assert c.get("/demo/celular").status_code == 404
