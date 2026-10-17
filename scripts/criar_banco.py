"""Cria as tabelas, a view e a configuração inicial aplicando db/schema.sql no banco do DATABASE_URL.

Útil para um MySQL instalado sem o docker compose, que não roda o schema sozinho.
O schema é idempotente: rodar de novo não apaga dados.

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


def main() -> int:
    eng = get_engine()
    print(f"Banco: {eng.url.database} em {eng.url.host}:{eng.url.port}")
    lista = comandos((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
    with eng.begin() as conn:
        for c in lista:
            conn.exec_driver_sql(c)
        tabelas = [r[0] for r in conn.execute(text("SHOW TABLES"))]
    print(f"{len(lista)} comandos aplicados. Tabelas: {', '.join(sorted(tabelas))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
