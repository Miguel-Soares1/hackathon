---
name: Painel de Monitoramento e Métricas
status: implemented
references: [1, 2, 3, 5, 6, 9]
---

# Painel de Monitoramento e Métricas

## Objetivo

Reunir em um painel a fila de atendimento, os incidentes detectados e as métricas operacionais, dando visibilidade em poucas horas de desenvolvimento.

## Escopo

- **Tecnologia:** painel em HTML, CSS e JavaScript puros (ADR-010), servido pela API e consumindo seus endpoints.
- **Fontes de dados:** classificação (Spec 1), incidentes (Spec 2), correções/precisão (Spec 3), prazos/SLA (Spec 5) e versão do prompt/exemplos (Spec 6).
- **Acesso:** o painel pede a `API_KEY` e consome só a API autenticada (sem acesso direto ao banco).
- **Visualizações:**
  - Fila de atendimento (tickets pendentes).
  - Alertas de incidentes detectados.
  - Métricas: principais motivos de contato, prazos de resposta em risco e precisão de triagem.

## Critérios de Aceitação

- [x] O painel exibe a fila de atendimento.
- [x] O painel lista os incidentes detectados.
- [x] O painel exibe a distribuição dos principais motivos de contato.
- [x] O painel sinaliza os prazos de resposta em risco e estourados (Spec 5).
- [x] O painel exibe o SLI de cumprimento de prazo e o consumo do error budget.
- [x] Tickets classificados por `fallback` são identificados e contados separadamente na precisão.
- [x] O painel exibe a precisão de triagem.
- [x] As métricas são atualizadas em um intervalo definido.
- [x] O detalhe do ticket mostra a versão do prompt e os tickets revisados usados como exemplo (Spec 6).
- [x] O painel exibe a taxa de acerto por versão do prompt (Spec 6).
- [x] Sem a `API_KEY`, o painel não carrega dados.
- [x] A fila e o detalhe mostram o idioma do cliente, e Métricas mostra a distribuição de idiomas (Spec 9).

## Fora de Escopo (V1)

- Autenticação/controle de acesso granular.
- Alertas/notificações em tempo real (push).

## Dependências

- Spec 1, Spec 2, Spec 3, Spec 5, Spec 6 e Spec 9.
