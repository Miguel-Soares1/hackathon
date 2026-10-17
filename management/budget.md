# Budget

Acompanhamento de custo do projeto em nível geral (não por sessão).

---

## Premissas

- **Infraestrutura da demo:** zero. Tudo roda no notebook (MySQL em Docker, API e painel em um processo, embeddings
  locais em ONNX, ADR-011). Canais sem custo: número de teste da WhatsApp Cloud API e caixa de e-mail por IMAP (ADR-013).
- **Único custo variável:** a API do LLM (DeepSeek), uma chamada por ticket (ADR-003). Os embeddings não têm custo
  por chamada (ADR-008).
- **Produção (opcional, ADR-012):** um servidor de 1 vCPU / 2 GB e um domínio, a contratar só se o sistema for publicado.

## Consumo de tokens por ticket

Medido sobre o prompt atual (`v3`, com idioma), em caracteres, com a aproximação de ~3,5 caracteres por token:

| Situação | Entrada (aprox.) | Saída (aprox.) |
|---|---|---|
| Prompt sem exemplos (`v3`) | ~740 tokens | até 700 (`max_tokens`); na prática, a resposta sugerida curta mais o JSON |
| Prompt com 4 exemplos (`v3+fewshot`) | ~1.130 tokens (+~70 por exemplo) | igual |
| Falha de JSON | até 2 chamadas (uma nova tentativa, ADR-009) | — |

O few-shot (ADR-014) aumenta a entrada em até ~50% por ticket; as instruções de idioma (ADR-015) somaram ~140 tokens. `FEWSHOT_K` controla esse custo (0 desliga).

## Chamadas planejadas

| Atividade | Chamadas ao LLM |
|---|---|
| Demo completa (`simular.py` + rajada) | ~40 |
| `scripts/avaliar_triagem.py` (60 mensagens × LLM e few-shot + 3 de injection) | ~123 |
| `scripts/avaliar_triagem.py --arquivo data/avaliacao_idiomas.json` | ~51 |
| Teste de carga (`scripts/teste_carga.py`) | conforme o parâmetro de volume |

## Registro de gastos

Preencha com o valor do painel de uso da DeepSeek após cada atividade relevante.

| Data | Atividade | Chamadas | Custo | Observação |
|---|---|---|---|---|
| | | | | |

## Teto e ação

O risco R10 (`docs/risks.md`) define a resposta: custo acumulado acima do teto combinado pela equipe → pausar as chamadas
de teste e rodar a avaliação só com `--so-regras` ou `--limite`.
