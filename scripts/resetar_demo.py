"""Limpa os dados da demo para repetir a apresentação do zero.

Apaga tickets, classificações, correções, revisões, embeddings, grupos e incidentes.
Mantém a configuração (sla_policy e app_config, incluindo o limiar calibrado).

Uso:
  python scripts/resetar_demo.py          # pede confirmação
  python scripts/resetar_demo.py --sim    # sem confirmação
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sqlalchemy import text  # noqa: E402

from triagem.db import get_engine  # noqa: E402

# Ordem: filhas antes das mães (FKs).
TABELAS = ("group_members", "incident_groups", "ticket_embeddings", "corrections", "reviews", "classifications", "tickets")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sim", action="store_true", help="não pedir confirmação")
    args = p.parse_args()

    eng = get_engine()
    print(f"Banco: {eng.url.database} em {eng.url.host}:{eng.url.port}")
    if not args.sim and input("Apagar todos os tickets e incidentes da demo? [s/N] ").strip().lower() != "s":
        print("Cancelado.")
        return 1

    with eng.begin() as conn:
        for t in TABELAS:
            n = conn.execute(text(f"DELETE FROM {t}")).rowcount  # nomes fixos acima, sem entrada do usuário
            if t in ("tickets", "incident_groups", "corrections"):
                conn.execute(text(f"ALTER TABLE {t} AUTO_INCREMENT = 1"))
            print(f"  {t:<18} {n} linhas apagadas")
    print("Pronto. Configuração (sla_policy, app_config) preservada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
