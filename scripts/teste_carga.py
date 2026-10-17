"""Teste de carga: mede vazão, latência do webhook e tempo até a classificação.

Exemplos:
  python scripts/teste_carga.py --total 200 --concorrencia 10
  python scripts/teste_carga.py --url https://triagem.seudominio.com/api --total 100 --concorrencia 5

Lê API_KEY do ambiente/.env. Cria tickets de verdade (use um banco de teste ou limpe depois).
Com a chave do LLM configurada no servidor, o 'tempo até classificar' reflete a latência real do provedor.
"""
import argparse
import json
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")


def percentil(valores, p):
    if not valores:
        return float("nan")
    v = sorted(valores)
    return v[min(len(v) - 1, math.ceil(p / 100 * len(v)) - 1)]


def resumo(nome, valores, unidade="ms", fator=1000.0):
    if not valores:
        return f"{nome}: sem dados"
    v = [x * fator for x in valores]
    return (f"{nome}: p50={percentil(v, 50):.0f}{unidade}  p95={percentil(v, 95):.0f}{unidade}  "
            f"p99={percentil(v, 99):.0f}{unidade}  máx={max(v):.0f}{unidade}  média={statistics.mean(v):.0f}{unidade}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.getenv("API_URL", "http://127.0.0.1:8000"))
    p.add_argument("--total", type=int, default=100)
    p.add_argument("--concorrencia", type=int, default=10)
    p.add_argument("--espera-classificacao", type=float, default=180.0, help="segundos aguardando a fila esvaziar")
    p.add_argument("--arquivo", default=str(RAIZ / "data" / "mensagens_demo.json"))
    args = p.parse_args()

    chave = os.getenv("API_KEY", "")
    if not chave:
        print("Defina API_KEY no .env ou no ambiente.", file=sys.stderr)
        return 2
    base = [m["texto"] for m in json.loads(Path(args.arquivo).read_text(encoding="utf-8"))]
    textos = [base[i % len(base)] for i in range(args.total)]

    enviados: dict[int, float] = {}  # ticket_id -> instante de envio
    latencias, codigos = [], {}
    lock = threading.Lock()
    cliente = httpx.Client(base_url=args.url, headers={"X-API-Key": chave}, timeout=30,
                           limits=httpx.Limits(max_connections=args.concorrencia * 2))

    def enviar(texto):
        t0 = time.perf_counter()
        try:
            r = cliente.post("/webhook/mensagens", json={"canal": "carga", "texto": texto})
            dt = time.perf_counter() - t0
            with lock:
                latencias.append(dt)
                codigos[r.status_code] = codigos.get(r.status_code, 0) + 1
                if r.status_code == 202:
                    enviados[r.json()["ticket_id"]] = time.perf_counter()
        except httpx.HTTPError as exc:
            with lock:
                codigos[type(exc).__name__] = codigos.get(type(exc).__name__, 0) + 1

    print(f"Enviando {args.total} mensagens com concorrência {args.concorrencia} para {args.url} ...")
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concorrencia) as pool:
        list(pool.map(enviar, textos))
    dur_envio = time.perf_counter() - inicio

    # Aguarda a classificação em background e mede o tempo até cada ticket ficar 'classificado'.
    vistos: dict[int, float] = {}
    limite = time.perf_counter() + args.espera_classificacao
    origem: dict[str, int] = {}
    while time.perf_counter() < limite and len(vistos) < len(enviados):
        r = cliente.get("/tickets", params={"limite": 1000})
        agora = time.perf_counter()
        for t in r.json():
            tid = t["ticket_id"]
            if tid in enviados and tid not in vistos and t["status"] == "classificado":
                vistos[tid] = agora - enviados[tid]
                origem[t["origem"]] = origem.get(t["origem"], 0) + 1
        time.sleep(0.5)
    pendentes = len(enviados) - len(vistos)
    dur_total = time.perf_counter() - inicio

    inc = cliente.get("/incidentes").json()
    print("\n=== Resultado ===")
    print(f"Respostas do webhook: {codigos}")
    print(f"Vazão de entrada: {len(latencias) / dur_envio:.1f} msg/s ({dur_envio:.1f} s para enviar)")
    print(resumo("Latência do webhook", latencias))
    print(resumo("Tempo até classificar", list(vistos.values()), unidade="s", fator=1.0))
    print(f"Classificados: {len(vistos)}/{len(enviados)}  pendentes ao fim: {pendentes}  origem: {origem}")
    print(f"Incidentes abertos: {len(inc)}  | duração total: {dur_total:.1f} s")
    ok = codigos.get(202, 0) == args.total and pendentes == 0
    print("\nRESULTADO:", "APROVADO (todas aceitas e classificadas)" if ok else "ATENÇÃO (há erros ou pendências)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
