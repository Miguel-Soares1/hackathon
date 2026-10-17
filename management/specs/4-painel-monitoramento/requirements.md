---
name: Painel de Monitoramento e Métricas
status: created
references: [1, 2, 3, 5]
---

# Painel de Monitoramento e Métricas

## Objetivo

Reunir em um painel a fila de atendimento, os incidentes detectados e as métricas operacionais, dando visibilidade em poucas horas de desenvolvimento.

## Escopo

- **Tecnologia:** painel Streamlit (ADR-005) consumindo dados do MySQL (ADR-006).
- **Fontes de dados:** classificação (Spec 1), incidentes (Spec 2), correções/precisão (Spec 3) e prazos/SLA (Spec 5).
- **Visualizações:**
  - Fila de atendimento (tickets pendentes).
  - Alertas de incidentes detectados.
  - Métricas: principais motivos de contato, prazos de resposta em risco e precisão de triagem.

## Critérios de Aceitação

- [ ] O painel exibe a fila de atendimento.
- [ ] O painel lista os incidentes detectados.
- [ ] O painel exibe a distribuição dos principais motivos de contato.
- [ ] O painel sinaliza os prazos de resposta em risco e estourados (Spec 5).
- [ ] O painel exibe o SLI de cumprimento de prazo e o consumo do error budget.
- [ ] Tickets classificados por `fallback` são identificados e contados separadamente na precisão.
- [ ] O painel exibe a precisão de triagem.
- [ ] As métricas são atualizadas em um intervalo definido.

## Fora de Escopo (V1)

- Autenticação/controle de acesso granular.
- Alertas/notificações em tempo real (push).

## Dependências

- Spec 1, Spec 2, Spec 3 e Spec 5.
