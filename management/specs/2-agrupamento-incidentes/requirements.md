---
name: Agrupamento de Mensagens e Detecção de Incidentes
status: in-progress
references: [1]
---

# Agrupamento de Mensagens e Detecção de Incidentes

## Objetivo

Agrupar mensagens semelhantes por embeddings + similaridade de cosseno e abrir um incidente quando há concentração anômala, permitindo resposta proativa.

## Escopo

- **Entrada:** textos das solicitações (e classificação da Spec 1 para enriquecer o grupo).
- **Processamento (ADR-004, ADR-008):**
  - Gerar embeddings localmente (ADR-008), guardados em coluna BLOB.
  - A cada novo ticket, comparar com o centroide dos grupos abertos na janela; se o maior cosseno passar do limiar, o ticket entra no grupo e o centroide é atualizado; senão, abre-se um novo grupo.
  - Limiar inicial `0,70`, a ser calibrado com o conjunto de mensagens de demo rotuladas.
  - Janela temporal de agregação: 30 minutos.
- **Regra de incidente:** 3 ou mais mensagens no mesmo grupo dentro da janela de 30 minutos → abrir incidente.
- **Saída:** grupos de mensagens semelhantes e alertas de incidente (com grupo associado e justificativa).

## Critérios de Aceitação

- [x] Mensagens com similaridade de cosseno acima do limiar configurado são agrupadas.
- [ ] O limiar padrão foi calibrado com o conjunto de demo rotulado e o resultado está registrado em `docs/`.
- [x] Um incidente é aberto quando 3+ mensagens de um grupo ultrapassam o limiar dentro de 30 minutos.
- [x] Limiar, janela e volume mínimo são configuráveis.
- [x] Cada alerta inclui o grupo associado e uma justificativa/evidência.
- [x] Alertas são persistidos e expostos ao painel (Spec 4).

## Fora de Escopo (V1)

- Atuação/remoção automática sobre o incidente.
- Deduplicação/merge de tickets (apenas agrupamento e visualização).

## Dependências

- Spec 1 (classificação) para enriquecer o agrupamento.
