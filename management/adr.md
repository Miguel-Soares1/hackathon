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

## ADR-002: MySQL como banco de dados

**Status:** accepted

**Contexto:** precisamos persistir tickets, correções e métricas com um banco relacional robusto e suporte a acesso concorrente.

**Decisão:** usar MySQL (banco SQL relacional). Guarda tickets, correções e métricas.

**Consequências:**
- Banco relacional maduro e adequado a produção.
- Requer servidor de banco (instalação/conexão), diferente de um arquivo embutido.
- Suporta concorrência de escrita.

---

## ADR-003: LLM com saída JSON para classificação

**Status:** accepted

**Contexto:** cada ticket deve ser classificado em assunto, urgência, sentimento, equipe e resposta sugerida.

**Decisão:** uma única chamada a um LLM por ticket, com saída JSON estruturada. Provedor: API da DeepSeek (escolhida por custo-benefício e qualidade).

**Consequências:**
- Uma chamada por ticket controla custo e latência.
- Saída estruturada facilita o parsing e o armazenamento.
- Dependência de API externa; exige prompt/parsing robusto contra JSON inválido.

---

## ADR-004: Embeddings + similaridade de cosseno para detecção de incidentes

**Status:** accepted

**Contexto:** agrupar mensagens semelhantes para detectar possíveis incidentes.

**Decisão:** gerar embeddings das mensagens e compará-las por similaridade de cosseno. Um incidente é aberto quando 3 ou mais mensagens ficam acima de um limiar (ex.: 0,80) dentro de uma janela de 30 minutos.

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
