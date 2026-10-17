"""Simulador de canais (ADR-001): dispara as mensagens de demo para o webhook.

Uso (com a API no ar):
  python scripts/simular.py                 # envia tudo, com a data original retroativa (idade_min)
  python scripts/simular.py --tempo-real    # envia tudo "agora" (received_at = agora)
  python scripts/simular.py --limite 10 --intervalo 1.5
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    p.add_argument("--arquivo", default=str(RAIZ / "data" / "mensagens_demo.json"))
    p.add_argument("--limite", type=int, default=0, help="enviar só as N primeiras (0 = todas)")
    p.add_argument("--intervalo", type=float, default=0.0, help="segundos entre mensagens")
    p.add_argument("--tempo-real", action="store_true", help="ignora idade_min e usa a hora atual")
    args = p.parse_args()

    chave = os.getenv("API_KEY", "")
    if not chave:
        print("Defina API_KEY no .env (ou no ambiente).", file=sys.stderr)
        return 2

    mensagens = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    if args.limite:
        mensagens = mensagens[: args.limite]

    agora = datetime.now(timezone.utc)
    enviados = 0
    with httpx.Client(base_url=args.url, headers={"X-API-Key": chave}, timeout=30) as http:
        for m in sorted(mensagens, key=lambda x: -x.get("idade_min", 0)):  # da mais antiga para a mais recente
            corpo = {"canal": m["canal"], "cliente": m.get("cliente"), "texto": m["texto"]}
            if not args.tempo_real and "idade_min" in m:
                corpo["received_at"] = (agora - timedelta(minutes=m["idade_min"])).isoformat()
            r = http.post("/webhook/mensagens", json=corpo)
            if r.status_code != 202:
                print(f"FALHA {r.status_code}: {r.text[:200]}", file=sys.stderr)
                return 1
            enviados += 1
            ticket_id = r.json()["ticket_id"]
            # Demo: registra a 1ª resposta com data retroativa (só quando a data original é preservada).
            if not args.tempo_real and m.get("respondido_apos_min") is not None:
                quando = agora - timedelta(minutes=m["idade_min"] - m["respondido_apos_min"])
                rr = http.post(f"/tickets/{ticket_id}/resposta", json={"respondido_em": quando.isoformat()})
                if rr.status_code != 200:
                    print(f"FALHA ao registrar resposta {rr.status_code}: {rr.text[:200]}", file=sys.stderr)
                    return 1
            print(f"[{enviados}/{len(mensagens)}] ticket {ticket_id}: {m['texto'][:60]}")
            if args.intervalo:
                time.sleep(args.intervalo)
    print(f"{enviados} mensagens enviadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
