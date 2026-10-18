"""Limpa os dados da demo para repetir a apresentação do zero.

Apaga tickets, classificações, correções, revisões, embeddings, grupos, incidentes e as mensagens internas.
Recria a equipe de demonstração (nomes genéricos) usada em "Mensagens internas".
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
TABELAS = ("group_members", "incident_groups", "ticket_embeddings", "corrections", "reviews", "classifications", "messages", "tickets",
           "internal_messages", "team_members")

# Equipe da demonstração em "Mensagens internas". No painel, cada pessoa escolhe um destes em "Seu nome no chat".
EQUIPE_DEMO = ("Atendente 1", "Atendente 2", "Atendente 3", "Supervisor", "Financeiro", "Suporte Técnico")


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
            if t in ("tickets", "incident_groups", "corrections", "messages", "internal_messages", "team_members"):
                conn.execute(text(f"ALTER TABLE {t} AUTO_INCREMENT = 1"))
            print(f"  {t:<18} {n} linhas apagadas")
        for nome in EQUIPE_DEMO:
            conn.execute(text("INSERT INTO team_members (nome) VALUES (:n)"), {"n": nome})
    print(f"  equipe da demo     {', '.join(EQUIPE_DEMO)}")
    print("Pronto. Configuração (sla_policy, app_config) preservada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
