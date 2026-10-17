# Avaliação da triagem

Como reproduzir: `python scripts/avaliar_triagem.py --arquivo <conjunto> [--modos regras llm fewshot] [--rodadas N] [--saida relatorio.json]`
(`--so-regras` avalia só o plano B, sem custo de API).

## Três conjuntos, três papéis

| Conjunto | Mensagens | Uso |
|---|---|---|
| `data/mensagens_demo.json` | 34 | Demo, calibração do limiar e ajuste do prompt e das regras. **O resultado aqui é otimista.** |
| `data/avaliacao.json` | 60 | Conjunto padrão do script: compara regras, LLM e LLM + few-shot antes de mudar o prompt (ADR-014). |
| `data/mensagens_holdout.json` | 30 | Nunca usado para ajustar nada. Rotula também `equipe`. **É o número que vale.** |

O prompt do LLM (`classifier.py`) cita exemplos tirados do conjunto de demo ("boleto recusado", "código que não chegou",
"relatório com erro"), e as palavras-chave do plano B (`fallback.py`) seguem o vocabulário dele. Por isso o
acerto medido na demo não indica o desempenho em mensagens novas.

**Regra:** não ajuste o prompt, as regras nem o limiar olhando os erros do holdout. Se ajustar, o holdout vira
conjunto de ajuste e é preciso escrever outro.

## Resultados

| Avaliação | Demo (34) | Holdout (30) |
|---|---|---|
| Plano B (regras), agregado | 80,4% | **48,3%** |
| Plano B, urgência | 70,6% | 36,7% |
| Plano B, urgência subestimada | 8/34 | **17/30** |
| LLM (DeepSeek), agregado | 89,2% (1 rodada) | pendente |

No holdout, o plano B classifica como `duvida` muitas mensagens sem palavra-chave conhecida e cai em urgência `baixa`.
Esse é o erro mais grave para o SLA. Isso não muda a decisão do ADR-009 (o plano B só entra quando o LLM falha),
mas mostra que, nesse modo, a urgência precisa de revisão humana.

**Pendente:** rodar o LLM no holdout com 3 rodadas e gravar o relatório:
`python scripts/avaliar_triagem.py --arquivo data/mensagens_holdout.json --rodadas 3 --saida docs/avaliacao_holdout.json`

## Limitações

- Com 30 mensagens, a margem de erro é de cerca de ±15 pontos percentuais por dimensão. Diferenças pequenas entre
  versões do prompt não são conclusivas.
- Os rótulos do holdout foram escritos por uma pessoa só. Urgência e sentimento são subjetivos: vale outra pessoa
  do grupo rotular sem ver os rótulos e comparar.
- A `equipe` esperada segue o mapa do plano B (pagamento e cobrança → financeiro; acesso → suporte_técnico;
  instabilidade → engenharia; cancelamento → retenção; o resto → atendimento). A spec não define esse mapa.
- Prompt injection: são 6 casos. O teste confere o rótulo e também a `resposta_sugerida` (link ou valor injetado e
  trechos do prompt de sistema). Não substitui um teste adversarial amplo.
