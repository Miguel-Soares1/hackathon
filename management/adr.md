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

**Status:** superseded por ADR-010

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

**Status:** accepted (execução alterada pelo ADR-011)

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

---

## ADR-010: Painel em HTML, CSS e JavaScript puros, servido pela API

**Status:** accepted

**Contexto:** o projeto precisaria ser publicado em hospedagem gratuita (depois, a equipe decidiu rodar tudo localmente; a decisão continua valendo porque reduz o consumo do notebook da demo). O Streamlit é um segundo serviço Python, com servidor próprio, dependências pesadas (pandas, pyarrow) e acesso direto ao banco. Em planos gratuitos, isso dobra o consumo de memória e o número de serviços.

**Decisão:** reescrever o painel como arquivos estáticos (`frontend/`: HTML, CSS e JavaScript, sem framework, sem build e sem dependências externas). A própria API FastAPI serve esses arquivos na raiz (`/`) e o painel consome os mesmos endpoints públicos da API, com a chave no header `X-API-Key` (guardada só na aba, em `sessionStorage`). O endpoint `GET /dominio` expõe os valores permitidos para os formulários.

**Consequências:**
- Um único serviço para subir; o painel pesa alguns KB e carrega instantaneamente.
- O painel deixa de acessar o banco direto: tudo passa pela API autenticada (reduz T7 do threat model).
- Os arquivos estáticos podem ir para qualquer CDN gratuita se um dia o backend ficar separado.
- Sem gráficos de biblioteca: as barras são feitas em CSS.

---

## ADR-011: Embeddings em ONNX int8 com SentencePiece, sem PyTorch

**Status:** accepted

**Contexto:** a hospedagem gratuita avaliada (Render free) oferecia 512 MB de RAM. A equipe depois decidiu rodar tudo localmente, mas a decisão se mantém: o notebook da demo tem 8 GB, e o processo antigo chegou a ser encerrado por falta de memória. O Hugging Face Spaces passou a exigir plano pago para Docker. Com `sentence-transformers` + PyTorch, o modelo do ADR-008 ocupa ~800 MB e o processo é morto por falta de memória. Mesmo em ONNX, o `tokenizer.json` do modelo (vocabulário de 250 mil tokens) consome ~320 MB ao carregar.

**Decisão:** manter o mesmo modelo (`paraphrase-multilingual-MiniLM-L12-v2`), mas executá-lo pela versão ONNX quantizada em int8 (`Xenova/paraphrase-multilingual-MiniLM-L12-v2`, `onnx/model_quantized.onnx`) com `onnxruntime`. A tokenização usa o `sentencepiece.bpe.model` original, com a convenção de ids do XLM-RoBERTa. Cada texto é codificado sozinho, porque na quantização dinâmica a escala depende do lote. O backend `sbert` continua disponível como opção (instalando `sentence-transformers`).

**Consequências:**
- Pico de memória do serviço completo: 365 MB, medido num container de 512 MB processando 38 mensagens com o LLM real. A instalação deixa de baixar o PyTorch (~550 MB).
- Fidelidade: similaridade média de 0,995 (mínima 0,988) entre os vetores ONNX e os do modelo original. Os tokens são idênticos em 41 de 42 textos de teste, inclusive acentos, emoji e prompt injection.
- O limiar calibrado (0,60) se manteve: 2/2 incidentes, zero falsos em 200 ordens aleatórias (`docs/calibracao_limiar.md`).
- O modelo (~120 MB) é baixado do Hugging Face no primeiro uso e fica em cache; depois a API funciona sem acessar o Hugging Face.

