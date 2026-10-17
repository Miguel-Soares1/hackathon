---
name: Aprendizado com as Correções do Atendente
status: implemented
references: [1, 2, 3]
---

# Aprendizado com as Correções do Atendente

## Objetivo

Fazer a triagem melhorar com o uso: cada ticket revisado pelo atendente passa a orientar a classificação das próximas
mensagens parecidas, sem fine-tuning (indisponível na API do DeepSeek), e a melhora precisa ser medida (ADR-014).

## Escopo

- **Entrada:** a mensagem nova e os tickets já revisados (confirmados ou corrigidos), com seus embeddings locais.
- **Processamento:** selecionar até `FEWSHOT_K` (padrão 4) revisados com similaridade de cosseno ≥ `FEWSHOT_SIM_MIN`
  (padrão 0,45) e enviá-los ao LLM como exemplos, com os valores efetivos (a última correção).
- **Persistência:** cada classificação grava `prompt_version` (`v1`, `v2`, `v3`, com ou sem `+fewshot`, e `regras`) e os ids dos exemplos.
- **Saída:** taxa de acerto por versão do prompt no painel e em `/metricas`; avaliação offline em um conjunto fixo.

## Critérios de Aceitação

- [x] Uma correção do atendente aparece como exemplo, com o valor corrigido, na classificação de uma mensagem parecida.
- [x] Tickets não revisados, o próprio ticket e mensagens pouco parecidas não viram exemplo.
- [x] O texto dos exemplos vai delimitado e sem as tags do sistema (o cliente não consegue fechar um bloco).
- [x] Versão do prompt, origem e exemplos são definidos pelo sistema, nunca pela resposta do LLM.
- [x] Falha na busca de exemplos não impede a classificação; `FEWSHOT_K=0` desliga o recurso.
- [x] O painel mostra os exemplos usados em cada ticket e a taxa de acerto por versão do prompt.
- [x] `scripts/avaliar_triagem.py` compara regras, LLM e LLM + few-shot em `data/avaliacao.json` (60 mensagens, 4 dimensões).

Testes: `tests/test_exemplos.py`.

## Fora de Escopo (V1)

- Fine-tuning ou retreino de modelo.
- Ponderar exemplos pela confiabilidade do atendente ou expirar correções antigas.
- Busca vetorial dedicada (a busca é em memória sobre até 3.000 revisados).
