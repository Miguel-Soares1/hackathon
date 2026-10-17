# Triagem IA — priorização e detecção de incidentes em solicitações de clientes

Hackathon 2026 · Desafio 06. Classifica cada solicitação por **assunto**, **urgência** e **sentimento**, sugere a resposta
e a equipe, agrupa mensagens semelhantes para **detectar incidentes**, mede a **taxa de acerto** com as correções do
atendente e mostra tudo em um **painel** com os **prazos de resposta em risco**.

Documentação: [`management/`](management/) (visão, arquitetura, ADRs, specs) e [`docs/`](docs/) (riscos, SLO, ameaças).

## Rodar em 5 passos

Pré-requisitos: Python 3.11+ e Docker.

```bash
cd Hackathon
cp .env.example .env                 # edite API_KEY (e DEEPSEEK_API_KEY, se tiver)
docker compose up -d                 # sobe o MySQL 8 e aplica db/schema.sql
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # inclui o PyTorch (download grande na 1ª vez) e o pytest
python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"   # baixa o modelo de embeddings (1ª vez)
```

Em três terminais (todos dentro de `Hackathon/`, com o venv ativo):

```bash
python -m uvicorn triagem.api:app --app-dir src --port 8000     # 1) API + webhook
streamlit run dashboard/app.py                                  # 2) painel em http://localhost:8501
python scripts/simular.py                                       # 3) envia as 34 mensagens de demo
```

Simulador de canais para a apresentação (WhatsApp, Instagram e e-mail fictícios): http://localhost:8000/demo (veja `docs/canais.md`).

Documentação interativa da API: http://localhost:8000/docs (use o header `X-API-Key`).

> **Windows:** troque `source .venv/bin/activate` por `.venv\Scripts\activate`.
> **Sem Docker:** crie o banco `hackathon` num MySQL 8 local, rode `db/schema.sql` nele e ajuste `DATABASE_URL`.
> **Sem chave do LLM:** funciona mesmo assim; a triagem usa o plano B por regras (`origem = fallback`).

## Testes

```bash
docker compose up -d      # os testes usam o banco hackathon_test (criado pelo compose)
python -m pytest
```

Os testes usam o embedder leve (`EMBEDDING_BACKEND=hash`) e nunca chamam a API do LLM nem tocam o banco real.
Se o MySQL não estiver no ar, os testes **falham** com uma mensagem clara (não são ignorados).

## Colocar no ar (produção)

Guia completo em **[`docs/deploy.md`](docs/deploy.md)**: Docker Compose com MySQL, API, painel e HTTPS automático (Caddy),
formulário público de entrada (`/enviar`), webhook com chave, backup e teste de carga (`scripts/teste_carga.py`).

## Calibrar o limiar de incidentes (faça antes da demo)

O limiar de similaridade (`0,70`) é um valor inicial. Calibre com o modelo real:

```bash
python scripts/calibrar_limiar.py        # mostra precisão/revocação por limiar e sugere o melhor
mysql -h127.0.0.1 -uhackathon -phackathon hackathon -e "UPDATE app_config SET valor='0.xx' WHERE chave='similarity_threshold';"
```

## Como funciona

```
Canais → POST /webhook/mensagens (202) → MySQL (ticket pendente)
                                            └→ background: LLM (JSON validado) ──falha──▶ regras (fallback)
                                                           └→ embedding local → grupo (centroide) → incidente (≥3 em 30 min)
Atendente (painel/API): confirmar ou corrigir a triagem · marcar 1ª resposta
Painel: fila · incidentes · motivos de contato · prazos em risco · SLI/error budget · precisão
```

| Regra | Valor (configurável em `app_config` / `sla_policy`) |
|---|---|
| Prazo da 1ª resposta | crítica 15 min · alta 1 h · média 4 h · baixa 24 h |
| Prazo "em risco" | ≥ 75% do prazo consumido sem resposta; "estourado" ≥ 100% |
| Incidente | ≥ 3 mensagens no mesmo grupo em 30 min (cosseno com o centroide ≥ limiar) |
| SLO | 95% das primeiras respostas dentro do prazo, janela de 7 dias |
| Taxa de acerto | `1 − correções/revisados` por dimensão; agregado = 4 dimensões (assunto, urgência, sentimento, equipe). Tickets `fallback` ficam separados |

### Endpoints (header `X-API-Key`, exceto `/health`)

| Método e rota | Função | Respostas |
|---|---|---|
| `POST /webhook/mensagens` | recebe uma solicitação (canais/integrações) | 202, 400, 401 |
| `GET/POST /webhooks/whatsapp` · `/webhooks/instagram` | webhooks da Meta (assinatura `X-Hub-Signature-256`) | 200, 403, 503 |
| `GET /enviar` · `POST /public/mensagens` | formulário web público (sem chave, com limite de taxa) | 200 · 202, 400, 429 |
| `GET /tickets`, `GET /tickets/{id}` | fila com prazo (SLA) | 200, 404 |
| `POST /tickets/{id}/resposta` | registra a 1ª resposta | 200, 404 |
| `POST /tickets/{id}/revisao` | confirma a triagem | 204, 404, 409 |
| `POST /tickets/{id}/correcoes` | corrige assunto/urgência/sentimento/equipe/resposta | 201, 400, 404, 409 |
| `GET /correcoes` | histórico de correções | 200 |
| `GET /incidentes` | incidentes e justificativa | 200 |
| `GET /metricas` | motivos, prazos em risco, SLI, precisão | 200 |

## Estrutura

```
src/triagem/   api, pipeline, classifier (LLM), fallback (regras), embeddings, incidents, sla, corrections, metrics
dashboard/     painel Streamlit
db/            schema.sql (DDL versionado) e init do banco de testes
scripts/       simular.py · calibrar_limiar.py · teste_carga.py · backup.sh
data/          mensagens_demo.json (34 mensagens rotuladas)
tests/         pytest (padrão AAA)
docs/          risks.md · slo.md · threat-model.md · deploy.md · release_checklist_final.md
management/    vision · arch · adr · roadmap · specs
```

## Segurança

- Todas as consultas SQL são parametrizadas (`:param`); nenhuma concatenação.
- Webhook e API exigem `X-API-Key`; segredos só em `.env` (ignorado pelo Git).
- O texto do cliente é enviado ao LLM como dado delimitado e a saída é validada contra valores permitidos (prompt injection).
- O texto da mensagem é enviado ao provedor do LLM (DeepSeek); não use dados pessoais reais na demo.
- Painel com senha (`DASHBOARD_PASSWORD`); em produção a API recusa subir com segredos fracos.
- Formulário público com limite de taxa por IP e global, honeypot e sem revelar a classificação.

## Limitações conhecidas

- O limiar de incidentes depende do modelo de embeddings e precisa ser calibrado (acima).
- Prazos contam 24x7 (sem horário comercial) e não há notificação push.
- Sem autenticação por atendente (senha única do painel): correções não registram autoria.
- Limitador de taxa em memória: rodar a API com 1 worker. Sem alta disponibilidade (servidor único).
