---
name: Classificação de Solicitações por Assunto, Urgência e Sentimento
status: implemented
references: []
---

# Classificação de Solicitações por Assunto, Urgência e Sentimento

## Objetivo

Classificar automaticamente cada solicitação de cliente e devolver, além das dimensões principais, a equipe responsável e uma resposta sugerida, por meio de uma única chamada a um LLM com saída JSON.

## Escopo

- **Entrada:** texto de uma solicitação (ticket, mensagem, chamado) recebida via webhook (ADR-001).
- **Processamento (ADR-003, ADR-009):** o webhook salva o ticket como `pendente` e responde `202`; uma tarefa em background faz uma única chamada a um LLM com saída JSON estruturada (provedor: API da DeepSeek), com timeout e uma nova tentativa se o JSON vier inválido.
- **Plano B:** se a API falhar, classificação por regras de palavras-chave, marcada com `origem = fallback` e confiança baixa.
- **Segurança:** o texto do cliente é tratado como dado (nunca como instrução) e a saída é validada contra os valores permitidos (ver `docs/threat-model.md`).
- **Saída (JSON):**
  - `assunto`: categoria/tópico de um conjunto predefinido (ex.: cobrança, suporte técnico, cancelamento, reclamação).
  - `urgencia`: nível de prioridade (ex.: baixa, média, alta, crítica).
  - `sentimento`: polaridade (positivo, neutro, negativo).
  - `equipe`: time responsável pelo atendimento.
  - `resposta_sugerida`: texto de resposta sugerida ao cliente.
  - `confianca`: score de confiança por dimensão.

## Critérios de Aceitação

- [x] Toda solicitação recebe `assunto`, `urgencia`, `sentimento`, `equipe` e `resposta_sugerida`.
- [x] A saída do LLM é um JSON válido e estruturado.
- [x] É feita uma única chamada ao LLM por ticket.
- [x] Cada predição inclui um score de confiança.
- [x] O resultado é persistido em MySQL (ADR-006) associado ao identificador do ticket, com `origem` (`llm` ou `fallback`) e `received_at`.
- [x] O webhook responde `202` sem aguardar o LLM e exige a chave de API no header.
- [x] Se o JSON for inválido, há uma nova tentativa; persistindo a falha, aplica-se o plano B.
- [x] Valores fora do conjunto permitido (assunto, urgência, sentimento, equipe) são rejeitados.

## Fora de Escopo (V1)

- Treinamento com dados reais de produção.
- Suporte multilíngue automático (idiomas suportados a definir em design).
- Retreino automático do modelo.

## Dependências

- Nenhuma (spec base).
