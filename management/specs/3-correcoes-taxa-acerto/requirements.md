---
name: Registro de Correções e Medição da Taxa de Acerto
status: implemented
references: [1]
---

# Registro de Correções e Medição da Taxa de Acerto

## Objetivo

Permitir que o atendente corrija a classificação automática e registrar essas correções para medir a taxa de acerto (precisão) da triagem ao longo do tempo.

## Escopo

- **Entrada:** correções do atendente sobre assunto, urgência, sentimento, equipe e/ou resposta sugerida, associadas à predição original.
- **Processamento:** comparar predição vs. correção (acerto/erro por dimensão).
- **Persistência:** tickets, correções e métricas são guardados em MySQL (ADR-006).
- **Saída:** métricas de precisão (taxa de acerto) por dimensão e no agregado.

## Critérios de Aceitação

- [x] O atendente consegue registrar uma correção para assunto, urgência, sentimento, equipe e/ou resposta sugerida.
- [x] A correção é associada ao ticket e à predição original.
- [x] A taxa de acerto é calculada por dimensão e no agregado.
- [x] O histórico de correções é persistido em MySQL e exposto ao painel (Spec 4).

## Fora de Escopo (V1)

- Retreino automático do modelo a partir das correções.
- Fluxo de aprovação/validação das correções.

## Dependências

- Spec 1 (classificação) como fonte das predições a serem corrigidas.
