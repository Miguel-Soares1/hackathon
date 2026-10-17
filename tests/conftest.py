"""Fixtures de teste. Usa um banco *_test separado; nunca toca no banco real."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "mysql+pymysql://hackathon:hackathon@127.0.0.1:3306/hackathon_test"
)

# Deve ser definido antes de qualquer import de triagem.*
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["API_KEY"] = "chave-de-teste"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["EMBEDDING_BACKEND"] = "hash"

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
LIMPEZA = [
    "TRUNCATE TABLE group_members", "TRUNCATE TABLE incident_groups", "TRUNCATE TABLE ticket_embeddings",
    "TRUNCATE TABLE reviews", "TRUNCATE TABLE messages", "TRUNCATE TABLE corrections", "TRUNCATE TABLE classifications",
    "TRUNCATE TABLE ticket_midias", "TRUNCATE TABLE tickets", "TRUNCATE TABLE sessoes", "TRUNCATE TABLE usuarios",
]
CHAVE = {"X-API-Key": "chave-de-teste"}


@pytest.fixture(scope="session")
def engine():
    nome_banco = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
    assert nome_banco.endswith("_test"), f"banco de testes deve terminar com _test (veio {nome_banco!r})"
    eng = create_engine(TEST_DATABASE_URL)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # falha explícita: teste quebrado não pode passar silenciosamente
        pytest.fail(
            "MySQL de teste indisponível. Suba o banco com `docker compose up -d` "
            f"e confira TEST_DATABASE_URL. Erro: {type(exc).__name__}",
            pytrace=False,
        )
    comandos = [c.strip() for c in SCHEMA.read_text(encoding="utf-8").split(";\n") if c.strip()]
    with eng.begin() as conn:
        # Recria do zero (só no banco *_test): CREATE TABLE IF NOT EXISTS não adiciona colunas novas do schema.
        conn.execute(text("DROP VIEW IF EXISTS vw_tickets"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for tabela in ("group_members", "incident_groups", "ticket_embeddings", "reviews", "corrections",
                       "classifications", "ticket_midias", "messages", "sessoes", "usuarios", "tickets", "sla_policy",
                       "app_config"):
            conn.execute(text(f"DROP TABLE IF EXISTS {tabela}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        for cmd in comandos:
            conn.execute(text(cmd))
    return eng


@pytest.fixture(autouse=False)
def db(engine):
    """Banco limpo (e configuração padrão) para cada teste."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for comando in LIMPEZA:
            conn.execute(text(comando))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.execute(text("DELETE FROM app_config"))
        conn.execute(text("DELETE FROM sla_policy"))
        conn.execute(text(
            "INSERT INTO sla_policy (urgencia, prazo_minutos) VALUES "
            "('critica', 15), ('alta', 60), ('media', 240), ('baixa', 1440)"
        ))
        conn.execute(text(
            "INSERT INTO app_config (chave, valor) VALUES ('sla_risco_pct','75'), ('similarity_threshold','0.70'), "
            "('window_minutes','30'), ('min_group_size','3'), ('slo_alvo_pct','95'), ('slo_janela_dias','7')"
        ))
    return engine


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from triagem.api import create_app

    return TestClient(create_app())
