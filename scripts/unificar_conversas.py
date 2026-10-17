"""Junta tickets duplicados do mesmo cliente numa conversa só (ADR-016).

Tickets criados antes do chat de atendimento (ou enviados sem `conversa_id`) viraram um ticket por mensagem, e o
mesmo cliente aparecia várias vezes em Atendimento. Este script aplica aos dados antigos a regra que o sistema usa
hoje: mesmo canal + mesmo cliente = mesma conversa, até 24 h depois da última resposta.

Uso:
  python scripts/unificar_conversas.py            # só mostra o que seria unido (não altera nada)
  python scripts/unificar_conversas.py --aplicar  # une de verdade (faça um backup antes em produção)
"""
import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from triagem.tickets import unificar_conversas  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true", help="une os tickets (sem isso, só mostra o plano)")
    args = p.parse_args()

    plano = unificar_conversas(aplicar=args.aplicar)
    if not plano:
        print("Nenhum ticket duplicado: cada cliente já está numa conversa só.")
        return 0
    total = sum(len(g["unidos"]) for g in plano)
    for g in plano:
        unidos = ", ".join(f"#{i}" for i in g["unidos"])
        print(f"  {g['canal']:<10} {g['cliente'] or '(sem nome)':<40} #{g['principal']} <- {unidos}")
    verbo = "unidos" if args.aplicar else "seriam unidos"
    print(f"\n{total} tickets {verbo} em {len(plano)} conversas.")
    if not args.aplicar:
        print("Nada foi alterado. Para unir de verdade: python scripts/unificar_conversas.py --aplicar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
