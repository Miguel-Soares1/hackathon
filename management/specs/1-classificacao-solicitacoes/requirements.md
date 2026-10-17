---
name: Classificação de Solicitações por Assunto, Urgência e Sentimento
status: created
references: []
---

# Classificação de Solicitações por Assunto, Urgência e Sentimento

## Objetivo

Classificar automaticamente cada solicitação de cliente e devolver, além das dimensões principais, a equipe responsável e uma resposta sugerida, por meio de uma única chamada a um LLM com saída JSON.

## Escopo

- **Entrada:** texto de uma solicitação (ticket, mensagem, chamado) recebida via webhook (ADR-001).
- **Processamento:** uma única chamada a um LLM com saída JSON estruturada (ADR-003). Provedor: API da DeepSeek.
- **Saída (JSON):**
  - `assunto`: categoria/tópico de um conjunto predefinido (ex.: cobrança, suporte técnico, cancelamento, reclamação).
  - `urgencia`: nível de prioridade (ex.: baixa, média, alta, crítica).
  - `sentimento`: polaridade (positivo, neutro, negativo).
  - `equipe`: time responsável pelo atendimento.
  - `resposta_sugerida`: texto de resposta sugerida ao cliente.
  - `confianca`: score de confiança por dimensão.

## Critérios de Aceitação

- [ ] Toda solicitação recebe `assunto`, `urgencia`, `sentimento`, `equipe` e `resposta_sugerida`.
- [ ] A saída do LLM é um JSON válido e estruturado.
- [ ] É feita uma única chamada ao LLM por ticket.
- [ ] Cada predição inclui um score de confiança.
- [ ] O resultado é persistido em MySQL (ADR-002) associado ao identificador do ticket.

## Fora de Escopo (V1)

- Treinamento com dados reais de produção.
- Suporte multilíngue automático (idiomas suportados a definir em design).
- Retreino automático do modelo.

## Dependências

- Nenhuma (spec base).
