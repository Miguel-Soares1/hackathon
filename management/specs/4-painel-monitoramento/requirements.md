---
name: Painel de Monitoramento e Métricas
status: created
references: []
---

# Painel de Monitoramento e Métricas

## Objetivo

Reunir em um painel a fila de atendimento, os incidentes detectados e as métricas operacionais, dando visibilidade em poucas horas de desenvolvimento.

## Escopo

- **Tecnologia:** painel Streamlit (ADR-005) consumindo dados do SQLite (ADR-002).
- **Fontes de dados:** classificação (Spec 1), incidentes (Spec 2), correções/precisão (Spec 3) e prazos/SLA das solicitações.
- **Visualizações:**
  - Fila de atendimento (tickets pendentes).
  - Alertas de incidentes detectados.
  - Métricas: principais motivos de contato, prazos de resposta em risco e precisão de triagem.

## Critérios de Aceitação

- [ ] O painel exibe a fila de atendimento.
- [ ] O painel lista os incidentes detectados.
- [ ] O painel exibe a distribuição dos principais motivos de contato.
- [ ] O painel sinaliza os prazos de resposta em risco.
- [ ] O painel exibe a precisão de triagem.
- [ ] As métricas são atualizadas em um intervalo definido.

## Fora de Escopo (V1)

- Autenticação/controle de acesso granular.
- Alertas/notificações em tempo real (push).

## Dependências

- Spec 1, Spec 2 e Spec 3.
