# SLI, SLO e Política de Error Budget

## SLI (o que medimos)

**Cumprimento do prazo de primeira resposta:** percentual de tickets cuja primeira resposta ocorreu dentro do prazo definido pela `sla_policy` (ADR-007), sobre o total de tickets respondidos ou estourados no período.

Tickets ainda abertos e dentro do prazo não entram no cálculo. Tickets `estourados` sem resposta contam como falha.

## SLO (a meta)

95% dos tickets respondidos dentro do prazo, em janela móvel de 7 dias.

## Error budget

5% dos tickets da janela podem violar o prazo. Exemplo: em 200 tickets na semana, o orçamento é de 10 violações.

Consumo do orçamento = violações / (total de tickets na janela x 5%). O painel (Spec 4) exibe esse consumo.

## Política de Error Budget

| Consumo do orçamento | Ação |
|----------------------|------|
| Até 50% | Operação normal; desenvolvimento de funcionalidades segue |
| 50% a 100% | Alerta no painel; revisar tickets em risco e a política de SLA |
| 100% ou mais | Congelar funcionalidades novas; priorizar correção das causas (fila, classificação de urgência, regras de SLA) até o consumo voltar abaixo de 100% |

## SLIs complementares (sem SLO formal na V1)

- Taxa de acerto da triagem por dimensão (Spec 3), com tickets `fallback` contados à parte.
- Latência de classificação: tempo entre `received_at` e a classificação persistida.
