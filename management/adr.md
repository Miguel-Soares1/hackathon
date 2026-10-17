# Architecture Decision Records

Registro de decisões de arquitetura.

Formato de cada registro:

```
ADR-XXX: <título>

Status: <proposed | accepted | superseded | deprecated>

Contexto: ...

Decisão: ...

Consequências: ...
```

---

## ADR-001: FastAPI como backend com webhook único e simulador de canais

**Status:** accepted

**Contexto:** precisamos receber mensagens de múltiplos canais (tickets, mensagens, chamados), mas os canais reais não estão disponíveis no hackathon.

**Decisão:** usar FastAPI com um único endpoint webhook para receber todas as mensagens. Um script separado dispara mensagens de exemplo simulando os canais.

**Consequências:**
- Um único ponto de entrada, rápido de implementar.
- Canais reais ficam para versões futuras (o webhook único já isola a origem).

---

## ADR-002: SQLite como banco de dados

**Status:** superseded por ADR-006

**Contexto:** precisamos persistir tickets, correções e métricas sem custo de infraestrutura nem instalação de servidor.

**Decisão:** usar SQLite (arquivo único). Guarda tickets, correções e métricas.

**Consequências:**
- Zero instalação/servidor; portátil e simples.
- Adequado a volume baixo/médio.
- Concorrência de escrita limitada (aceitável no escopo do hackathon).

---

## ADR-003: LLM com saída JSON para classificação

**Status:** accepted

**Contexto:** cada ticket deve ser classificado em assunto, urgência, sentimento, equipe e resposta sugerida.

**Decisão:** uma única chamada a um LLM por ticket, com saída JSON estruturada. Provedor: API da DeepSeek (escolhida por custo-benefício e qualidade). A execução é assíncrona e há plano B (ver ADR-009).

**Consequências:**
- Uma chamada por ticket controla custo e latência.
- Saída estruturada facilita o parsing e o armazenamento.
- Dependência de API externa; exige prompt/parsing robusto contra JSON inválido.

---

## ADR-004: Embeddings + similaridade de cosseno para detecção de incidentes

**Status:** accepted

**Contexto:** agrupar mensagens semelhantes para detectar possíveis incidentes.

**Decisão:** gerar embeddings das mensagens (modelo local, ADR-008) e compará-las por similaridade de cosseno com o centroide dos grupos abertos. Um incidente é aberto quando um grupo atinge 3 ou mais mensagens dentro de uma janela de 30 minutos. O limiar inicial é 0,70 e deve ser calibrado com mensagens de demo rotuladas.

**Consequências:**
- Detecção semântica (não apenas por palavras-chave).
- Parâmetros (limiar, janela, volume mínimo) configuráveis.
- Custo adicional de gerar embeddings.

---

## ADR-005: Streamlit para o painel

**Status:** accepted

**Contexto:** entregar fila, alertas e métricas em poucas horas.

**Decisão:** usar Streamlit para o painel de monitoramento.

**Consequências:**
- Entrega rápida de protótipo funcional.
- Menos flexível que um frontend customizado.
- Sem autenticação/controle de acesso granular (ok para hackathon).

---

## ADR-006: MySQL como banco de dados

**Status:** accepted

**Contexto:** o ADR-002 (SQLite) foi substituído por decisão da equipe. O livro-base exige banco relacional com scripts versionados que recriem o ambiente do zero.

**Decisão:** usar MySQL 8 (`utf8mb4`), executado via `docker compose`, com o DDL versionado em `db/`. Todas as consultas são parametrizadas. Os embeddings ficam em coluna `BLOB` (vetor de floats) e o cosseno é calculado em Python sobre a janela de 30 minutos.

**Consequências:**
- Banco relacional real, adequado aos critérios de entrega (README, `db/`, persistência).
- Exige Docker (ou MySQL local) para rodar o projeto.
- Sem busca vetorial nativa; aceitável para o volume do hackathon.
- Segredos de conexão ficam em `.env`, fora do Git.

---

## ADR-007: Política de SLA por urgência

**Status:** accepted

**Contexto:** o painel precisa sinalizar prazos de resposta em risco, mas nenhuma regra definia o prazo.

**Decisão:** o prazo da primeira resposta deriva da urgência: crítica 15 min, alta 1 h, média 4 h, baixa 24 h, guardado na tabela `sla_policy` (configurável). "Em risco" a partir de 75% do prazo consumido; "estourado" a partir de 100%. Contagem 24x7 na V1. SLO de cumprimento de 95% em 7 dias (`docs/slo.md`).

**Consequências:**
- Regra explícita, testável e ajustável sem alterar código.
- Não cobre horário comercial nem feriados (fora de escopo na V1).

---

## ADR-008: Embeddings locais com modelo multilíngue

**Status:** accepted

**Contexto:** o ADR-004 não definia o provedor de embeddings, e a API do LLM escolhida (DeepSeek) é usada para chat/classificação.

**Decisão:** usar um modelo local multilíngue (`paraphrase-multilingual-MiniLM-L12-v2`, via `sentence-transformers`).

**Consequências:**
- Sem custo por chamada e sem chave adicional; bom suporte a português.
- Download do modelo na primeira execução (o README inclui um passo de pré-download).
- Consome CPU/memória do servidor da demo. Plano alternativo: API de embeddings paga.

---

## ADR-009: Classificação assíncrona com plano B por regras

**Status:** accepted

**Contexto:** a chamada ao LLM dentro do webhook aumenta a latência e faz a ingestão falhar se a API estiver fora do ar.

**Decisão:** o webhook persiste o ticket como `pendente` e responde `202`. Uma tarefa em background classifica o ticket, com timeout e uma nova tentativa em caso de JSON inválido. Se a falha persistir, aplica-se classificação por palavras-chave, registrada com `origem = fallback` e confiança baixa. A taxa de acerto trata `llm` e `fallback` separadamente.

**Consequências:**
- Nenhuma mensagem se perde se a API externa cair.
- A fila pode mostrar tickets `pendente` por alguns segundos.
- Mais um estado no ciclo de vida do ticket.
