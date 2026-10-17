---
name: Idioma do Cliente e Resposta no Mesmo Idioma
status: implemented
references: [1, 4]
---

# Idioma do Cliente e Resposta no Mesmo Idioma

## Objetivo

Identificar o idioma em que cada cliente escreve e sugerir a resposta nesse mesmo idioma, sem perder a classificação
padronizada (códigos em português) usada pela fila, pelo SLA e pelas métricas (ADR-015).

## Escopo

- **LLM (prompt `v3`):** devolve `idioma` (ISO 639-1) e escreve `resposta_sugerida` no idioma do cliente.
- **Detector local** (`src/triagem/idioma.py`): pt, en, es, fr, it e de, por palavras funcionais e acentos; texto sem
  sinais assume português.
- **Conferência:** completa o idioma ausente, corrige o idioma quando a detecção local é forte e diverge e recusa a
  resposta escrita em outro idioma (nova tentativa e plano B).
- **Plano B:** respostas prontas em pt, en e es; outros idiomas recebem inglês; algumas palavras-chave em en e es.
- **Persistência e exibição:** `classifications.idioma`, coluna na fila, linha no detalhe do ticket, card "Idiomas dos
  clientes" em Métricas, `idiomas` em `/metricas` e nomes em `/dominio`.

## Critérios de Aceitação

- [x] Os seis idiomas suportados são detectados com sinal forte em frases típicas; texto sem sinais vira `pt`, sem força.
- [x] Nenhuma das 94 mensagens em português dos conjuntos rotulados é detectada como outro idioma.
- [x] Códigos como `pt-BR`, `EN` ou nomes como "Português" são normalizados; valor ilegível não invalida a classificação.
- [x] Cliente em inglês recebe `idioma = en` e resposta em inglês; o prompt exige a resposta no mesmo idioma.
- [x] Resposta do LLM em outro idioma é recusada, há nova tentativa e o plano B responde no idioma certo.
- [x] Sem `idioma` na resposta do LLM, vale a detecção local; detecção local forte corrige um idioma errado do LLM; em texto curto, vale o idioma do LLM.
- [x] O plano B responde em pt, en ou es conforme o cliente e em inglês para os demais idiomas.
- [x] O idioma é salvo, exposto em `/tickets`, contado em `/metricas` e nomeado em `/dominio`.
- [x] `scripts/avaliar_triagem.py --arquivo data/avaliacao_idiomas.json` mede o acerto do idioma e se a resposta saiu no idioma do cliente (24 mensagens em 6 idiomas, com casos mistos e injection).

Testes: `tests/test_idioma.py`.

## Fora de Escopo (V2)

- Corrigir o idioma pelo painel (não é uma dimensão da taxa de acerto).
- Respostas prontas do plano B em francês, italiano e alemão.
- Traduzir a mensagem do cliente para o atendente.
