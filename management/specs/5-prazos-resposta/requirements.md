---
name: Prazos de Resposta (SLA) e Primeira Resposta
status: created
references: [1]
---

# Prazos de Resposta (SLA) e Primeira Resposta

## Objetivo

Definir de onde vem o prazo de cada solicitação, registrar a primeira resposta do atendente e sinalizar os tickets com prazo em risco ou estourado.

## Escopo

- **Política de SLA (ADR-007):** tabela `sla_policy` no MySQL (ADR-006), configurável, que mapeia urgência para o prazo da primeira resposta:

| Urgência | Prazo |
|----------|-------|
| crítica | 15 min |
| alta | 1 h |
| média | 4 h |
| baixa | 24 h |

- **Contagem:** a partir de `received_at`, 24x7 (sem horário comercial na V1).
- **Estados:** `no_prazo`, `em_risco` (75% ou mais do prazo consumido sem resposta), `estourado` (100% ou mais) e `respondido`.
- **Ação do atendente:** marcar o ticket como respondido, registrando `first_response_at`.
- **Reclassificação:** se a urgência for corrigida (Spec 3), o prazo é recalculado a partir do `received_at` original.
- **SLI/SLO:** SLI = % de tickets respondidos dentro do prazo; SLO = 95% em janela de 7 dias (ver `docs/slo.md`).

## Critérios de Aceitação

- [ ] Todo ticket classificado recebe um prazo derivado da urgência e da `sla_policy`.
- [ ] O estado do ticket (`no_prazo`, `em_risco`, `estourado`, `respondido`) é calculado a partir de `received_at`, prazo e `first_response_at`.
- [ ] Um ticket com 75% ou mais do prazo consumido e sem resposta é `em_risco`.
- [ ] O atendente consegue marcar um ticket como respondido e `first_response_at` é persistido.
- [ ] Alterar a urgência de um ticket recalcula o prazo.
- [ ] O SLI de cumprimento de prazo é calculado e exposto ao painel (Spec 4).
- [ ] Prazos e o percentual de risco são configuráveis sem alterar código.

## Fora de Escopo (V1)

- Horário comercial, feriados e pausa de prazo.
- Escalonamento automático e notificações push.

## Dependências

- Spec 1 (urgência e `received_at`).
