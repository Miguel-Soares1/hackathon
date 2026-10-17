---
name: Agrupamento de Mensagens e Detecção de Incidentes
status: created
references: []
---

# Agrupamento de Mensagens e Detecção de Incidentes

## Objetivo

Agrupar mensagens semelhantes por embeddings + similaridade de cosseno e abrir um incidente quando há concentração anômala, permitindo resposta proativa.

## Escopo

- **Entrada:** textos das solicitações (e classificação da Spec 1 para enriquecer o grupo).
- **Processamento (ADR-004):**
  - Gerar embeddings das mensagens.
  - Comparar por similaridade de cosseno e agrupar as que ficam acima de um limiar (ex.: `0,80`).
  - Janela temporal de agregação: 30 minutos.
- **Regra de incidente:** 3 ou mais mensagens semelhantes acima do limiar dentro da janela de 30 minutos → abrir incidente.
- **Saída:** grupos de mensagens semelhantes e alertas de incidente (com grupo associado e justificativa).

## Critérios de Aceitação

- [ ] Mensagens com similaridade de cosseno acima do limiar (`0,80`) são agrupadas.
- [ ] Um incidente é aberto quando 3+ mensagens de um grupo ultrapassam o limiar dentro de 30 minutos.
- [ ] Limiar, janela e volume mínimo são configuráveis.
- [ ] Cada alerta inclui o grupo associado e uma justificativa/evidência.
- [ ] Alertas são persistidos e expostos ao painel (Spec 4).

## Fora de Escopo (V1)

- Atuação/remoção automática sobre o incidente.
- Deduplicação/merge de tickets (apenas agrupamento e visualização).

## Dependências

- Spec 1 (classificação) para enriquecer o agrupamento.
