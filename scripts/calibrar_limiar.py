"""Calibra o limiar de similaridade (Spec 2, ADR-004) com as mensagens de demo rotuladas.

Compara todos os pares: positivos = mesmo `grupo` (mesmo problema), negativos = o resto.
Rode com o modelo real para obter o valor a ser usado:
  python scripts/calibrar_limiar.py   (usa EMBEDDING_BACKEND do .env; padrão onnx)
Depois grave o resultado: UPDATE app_config SET valor='0.xx' WHERE chave='similarity_threshold';
"""
import argparse
import itertools
import json
import os
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arquivo", default=str(RAIZ / "data" / "mensagens_demo.json"))
    p.add_argument("--backend", default=os.getenv("EMBEDDING_BACKEND", "onnx"))
    args = p.parse_args()
    os.environ["EMBEDDING_BACKEND"] = args.backend

    from triagem.embeddings import get_embedder

    msgs = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    emb = get_embedder()
    vet = emb.encode([m["texto"] for m in msgs])

    sims, rotulos = [], []
    for i, j in itertools.combinations(range(len(msgs)), 2):
        sims.append(float(np.dot(vet[i], vet[j])))
        gi, gj = msgs[i]["grupo"], msgs[j]["grupo"]
        rotulos.append(gi is not None and gi == gj)
    sims, rotulos = np.array(sims), np.array(rotulos)
    pos, neg = sims[rotulos], sims[~rotulos]

    print(f"Modelo: {emb.nome} | pares positivos: {len(pos)} | negativos: {len(neg)}")
    print(f"Similaridade dos pares do MESMO problema : min={pos.min():.2f} média={pos.mean():.2f}")
    print(f"Similaridade dos pares DIFERENTES        : média={neg.mean():.2f} p95={np.percentile(neg, 95):.2f} máx={neg.max():.2f}")

    melhor = (0.0, 0.0, 0.0, 0.0)
    print("\nlimiar  precisão  revocação  F1")
    for lim in np.arange(0.30, 0.96, 0.05):
        pred = sims >= lim
        tp = int(np.sum(pred & rotulos)); fp = int(np.sum(pred & ~rotulos)); fn = int(np.sum(~pred & rotulos))
        prec = tp / (tp + fp) if tp + fp else 1.0
        rev = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rev / (prec + rev) if prec + rev else 0.0
        print(f"{lim:5.2f}   {prec:6.2f}    {rev:6.2f}   {f1:5.2f}")
        if f1 > melhor[3]:
            melhor = (lim, prec, rev, f1)
    print(f"\nMelhor F1: limiar {melhor[0]:.2f} (precisão {melhor[1]:.2f}, revocação {melhor[2]:.2f}, F1 {melhor[3]:.2f})")
    print("Dica: prefira o menor limiar com precisão alta (evita falsos incidentes na demo).")

    simular_incidentes(msgs, vet)
    return 0


def simular_incidentes(msgs: list, vet: np.ndarray, janela_min: float = 30, minimo: int = 3) -> None:
    """Reproduz o algoritmo real (centroide + janela) em ordem de chegada e conta incidentes certos e falsos."""
    from collections import Counter
    from datetime import datetime, timedelta

    from triagem.incidents import atualizar_centroide, escolher_grupo, janela_atingida

    ordem = sorted(range(len(msgs)), key=lambda i: -msgs[i].get("idade_min", 0))
    reais = {g for g, n in Counter(m["grupo"] for m in msgs).items() if g and n >= minimo}
    base = datetime(2026, 1, 1, 12)

    print(f"\nSimulação ponta a ponta (centroide, janela {janela_min:.0f} min, mínimo {minimo}).")
    print(f"Incidentes esperados: {sorted(reais)}")
    print("limiar  certos  falsos  grupos que viraram incidente (rótulo:acertos/tamanho)")
    for lim in np.arange(0.40, 0.76, 0.05):
        grupos: list[dict] = []
        for i in ordem:
            t = base - timedelta(minutes=msgs[i].get("idade_min", 0))
            cand = [(k, g["c"]) for k, g in enumerate(grupos) if g["tempos"][-1] >= t - timedelta(minutes=janela_min)]
            k, _ = escolher_grupo(vet[i], cand, lim)
            if k is None:
                grupos.append({"c": vet[i], "membros": [msgs[i]], "tempos": [t]})
            else:
                g = grupos[k]
                g["c"] = atualizar_centroide(g["c"], len(g["membros"]), vet[i])
                g["membros"].append(msgs[i])
                g["tempos"].append(t)
        certos, falsos, desc = set(), 0, []
        for g in grupos:
            if not janela_atingida(g["tempos"], minimo, janela_min):
                continue
            rotulo, n = Counter(m["grupo"] for m in g["membros"]).most_common(1)[0]
            if rotulo in reais and n >= minimo:
                certos.add(rotulo)
            else:
                falsos += 1
            desc.append(f"{rotulo}:{n}/{len(g['membros'])}")
        print(f"{lim:5.2f}   {len(certos)}/{len(reais)}     {falsos}      {', '.join(desc) or '-'}")
    print("Escolha um limiar no meio da faixa com todos os incidentes certos e zero falsos.")


if __name__ == "__main__":
    sys.exit(main())
