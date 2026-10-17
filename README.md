# Triagem IA — priorização e detecção de incidentes em solicitações de clientes

Hackathon 2026 · Desafio 06. Classifica cada solicitação por **assunto**, **urgência** e **sentimento**, sugere a resposta
e a equipe, agrupa mensagens semelhantes para **detectar incidentes**, mede a **taxa de acerto** com as correções do
atendente e mostra tudo em um **painel** com os **prazos de resposta em risco**.

Documentação: [`management/`](management/) (visão, arquitetura, ADRs, specs) e [`docs/`](docs/) (riscos, SLO, ameaças).

## Rodar em 5 passos

Pré-requisitos: Python 3.11+ e Docker.

```bash
git clone https://github.com/Miguel-Soares1/hackathon.git && cd hackathon
cp .env.example .env                 # edite API_KEY (e DEEPSEEK_API_KEY, se tiver)
docker compose up -d                 # sobe o MySQL 8 e aplica db/schema.sql
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # leve: sem PyTorch (embeddings em ONNX, ADR-011)
python -c "import sys; sys.path.insert(0,'src'); from triagem.embeddings import OnnxEmbedder; OnnxEmbedder('m')"   # baixa o modelo de embeddings (~120 MB, 1ª vez)
```

Em dois terminais (na raiz do repositório, com o venv ativo):

```bash
python -m uvicorn triagem.api:app --app-dir src --port 8000     # 1) API + painel em http://localhost:8000
python scripts/simular.py                                       # 2) envia as 34 mensagens de demo
```

Abra http://localhost:8000 e entre com a `API_KEY` do `.env`. Documentação interativa da API: http://localhost:8000/docs (header `X-API-Key`).

Simulador de canais para a apresentação (WhatsApp, Instagram e e-mail fictícios): http://localhost:8000/demo (veja `docs/canais.md`).

> **Windows:** troque `source .venv/bin/activate` por `.venv\Scripts\activate`.
> **Sem Docker:** crie o banco `hackathon` num MySQL 8 local, rode `db/schema.sql` nele e ajuste `DATABASE_URL`.
> **Sem chave do LLM:** funciona mesmo assim; a triagem usa o plano B por regras (`origem = fallback`).

## Dia da apresentação (Windows, tudo local)

Com o Docker Desktop aberto, um comando sobe o banco, a API e abre o painel:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
```

Para repetir a demo do zero: `python scripts/resetar_demo.py --sim` e depois `python scripts/simular.py`.
O sistema roda só no notebook; a única chamada externa é ao LLM (DeepSeek). Sem internet, a triagem usa o plano B por regras.

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

O limiar de similaridade já vem calibrado em `0,60` (ver [`docs/calibracao_limiar.md`](docs/calibracao_limiar.md)). Se trocar o modelo ou as mensagens de demo, recalibre:

```bash
python scripts/calibrar_limiar.py        # mostra precisão/revocação por limiar e sugere o melhor
mysql -h127.0.0.1 -uhackathon -phackathon hackathon -e "UPDATE app_config SET valor='0.xx' WHERE chave='similarity_threshold';"
```

## Scripts da demo

```bash
python scripts/avaliar_triagem.py      # taxa de acerto do LLM e das regras contra os rótulos + teste de prompt injection
python scripts/resetar_demo.py         # apaga tickets e incidentes para repetir a demo (mantém a configuração)
```

Roteiro da apresentação: [`docs/roteiro_demo.md`](docs/roteiro_demo.md).

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
frontend/      painel em HTML, CSS e JavaScript puros (servido pela própria API, sem build)
db/            schema.sql (DDL versionado) e init do banco de testes
scripts/       iniciar.ps1 (sobe tudo) · simular.py (canais) · calibrar_limiar.py · avaliar_triagem.py · resetar_demo.py · criar_banco.py · teste_carga.py · backup.sh
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
