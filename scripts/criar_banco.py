"""Cria as tabelas, a view e a configuração inicial aplicando db/schema.sql no banco do DATABASE_URL.

Útil para um MySQL instalado sem o docker compose, que não roda o schema sozinho.
O schema é idempotente: rodar de novo não apaga dados. Em um banco criado por uma versão anterior, aplica antes
as migrações de db/migrations que faltam (detectadas pela coluna que cada uma cria).

Uso:
  python scripts/criar_banco.py
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sqlalchemy import text  # noqa: E402

from triagem.db import get_engine  # noqa: E402


def comandos(sql: str) -> list[str]:
    sem_comentarios = re.sub(r"^\s*--.*$", "", sql, flags=re.M)
    return [c.strip() for c in sem_comentarios.split(";") if c.strip()]


# Migração -> (tabela, coluna) que ela cria. Em ordem: a 005 e a 006 dependem das anteriores.
MIGRACOES = [
    ("002_external_id.sql", "tickets", "external_id"),
    ("003_prompt_version.sql", "classifications", "prompt_version"),
    ("004_idioma.sql", "classifications", "idioma"),
    ("005_chat.sql", "tickets", "conversa_id"),
    ("006_encerramento.sql", "tickets", "encerrado_em"),
]


def _tem_coluna(conn, tabela: str, coluna: str) -> bool:
    return bool(conn.execute(
        text("SELECT COUNT(*) FROM information_schema.columns "
             "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"),
        {"t": tabela, "c": coluna},
    ).scalar())


def migrar(eng) -> list[str]:
    """Aplica as migrações que faltam num banco já existente. Banco novo (sem tickets): o schema cria tudo."""
    aplicadas = []
    with eng.begin() as conn:
        if not _tem_coluna(conn, "tickets", "id"):
            return aplicadas
        for arquivo, tabela, coluna in MIGRACOES:
            if _tem_coluna(conn, tabela, coluna):
                continue
            for c in comandos((RAIZ / "db" / "migrations" / arquivo).read_text(encoding="utf-8")):
                conn.exec_driver_sql(c)
            aplicadas.append(arquivo)
    return aplicadas


def main() -> int:
    eng = get_engine()
    print(f"Banco: {eng.url.database} em {eng.url.host}:{eng.url.port}")
    aplicadas = migrar(eng)
    if aplicadas:
        print(f"Migrações aplicadas: {', '.join(aplicadas)}")
    lista = comandos((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
    with eng.begin() as conn:
        for c in lista:
            conn.exec_driver_sql(c)
        tabelas = [r[0] for r in conn.execute(text("SHOW TABLES"))]
    print(f"{len(lista)} comandos aplicados. Tabelas: {', '.join(sorted(tabelas))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
