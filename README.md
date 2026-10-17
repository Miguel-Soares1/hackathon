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

Abra http://localhost:8000 e entre com a `API_KEY` do `.env`. O painel tem menu lateral: **Dashboard** (visão geral: clientes em espera, em atendimento, cancelados e encerrados; indicadores da triagem, incidentes e métricas), **Atendimento** (em espera × em atendimento × finalizados, conversa e triagem da IA), **Incidentes**, **Correções** e **Atendimentos** (relatório de controle: abertos e finalizados por status, período, canal, time e urgência, com busca por nome/telefone/protocolo e exportação em CSV). Para simular mensagens de clientes, use o simulador de canais em http://localhost:8000/demo. Documentação interativa da API: http://localhost:8000/docs (header `X-API-Key`).

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

Canais reais (WhatsApp e e-mail): **[`docs/canais.md`](docs/canais.md)**. Chat de atendimento e integração com o chat do cliente: **[`docs/chat.md`](docs/chat.md)**.

## Calibrar o limiar de incidentes (faça antes da demo)

O limiar de similaridade já vem calibrado em `0,60` (ver [`docs/calibracao_limiar.md`](docs/calibracao_limiar.md)). Se trocar o modelo ou as mensagens de demo, recalibre:

```bash
python scripts/calibrar_limiar.py        # mostra precisão/revocação por limiar e sugere o melhor
mysql -h127.0.0.1 -uhackathon -phackathon hackathon -e "UPDATE app_config SET valor='0.xx' WHERE chave='similarity_threshold';"
```

## A IA aprende com as correções (few-shot dinâmico)

Não há fine-tuning: antes de classificar, o sistema busca os tickets **já revisados** pelo atendente mais parecidos
com a mensagem nova e os envia ao DeepSeek como exemplos (ADR-014). Corrigiu uma triagem no painel? A próxima
mensagem parecida já usa essa correção. O painel mostra os exemplos usados em cada ticket e, em Métricas, a taxa de
acerto por versão do prompt (`v3`, `v3+fewshot`, `regras`). Ajuste com `FEWSHOT_K` (0 desliga) e `FEWSHOT_SIM_MIN`.

**Medir antes de mudar o prompt:** `data/avaliacao.json` tem 60 mensagens rotuladas nas 4 dimensões, separadas das
mensagens de demo (inclui ironia e prompt injection). Ao mudar o texto do prompt, incremente `PROMPT_VERSION` em
`src/triagem/classifier.py` e compare:

```bash
python scripts/avaliar_triagem.py --saida data/avaliacoes/v3.json   # regras × LLM × LLM+few-shot + injection
```

**Banco criado antes desta versão:** aplique as migrações em ordem e recrie a visão:
```powershell
Get-Content db/migrations/002_external_id.sql, db/migrations/003_prompt_version.sql, db/migrations/004_idioma.sql, db/migrations/005_chat.sql, db/migrations/006_midias.sql, db/migrations/007_desfecho.sql, db/migrations/008_midias_chat.sql | docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon
python scripts/criar_banco.py
```

## Clientes em outros idiomas

A IA identifica o idioma de cada mensagem (pt, en, es, fr, it, de...) e escreve a resposta sugerida **no mesmo idioma**,
mantendo a classificação em português para a fila, o SLA e as métricas (ADR-015). Um detector local confere o idioma e
recusa resposta em outro idioma; sem o LLM, o plano B responde em português, inglês ou espanhol. A fila mostra o idioma,
e Métricas mostra a distribuição. Avaliação: `python scripts/avaliar_triagem.py --arquivo data/avaliacao_idiomas.json`.

## Áudio e foto do cliente

O webhook aceita até 3 mídias por mensagem (áudio ou foto, até 8 MB cada) em `midias`, e o texto passa a ser
opcional quando há mídia (ADR-017). No background, o **Gemini** transcreve o áudio e descreve a foto (inclusive o
texto que aparece nela). O resultado é anexado ao texto do ticket (`[Áudio transcrito pela IA]: …`) e a triagem,
o few-shot e os incidentes seguem iguais. No painel, o atendimento toca o áudio e mostra a foto original do cliente.

O atendente também responde com mídia: no chat do **Atendimento**, **📎 Anexar imagem** e **🎙 Gravar áudio** (microfone)
mandam até 3 anexos junto com a resposta (`POST /tickets/{id}/mensagens` com `midias`). Essas mídias aparecem no
balão da conversa e não passam pela IA.

```json
{"canal": "whatsapp", "cliente": "Loja Aurora", "texto": "",
 "midias": [{"tipo": "audio", "mime": "audio/ogg", "dados_base64": "T2dnUw..."}]}
```

Formatos: foto JPG, PNG ou WebP; áudio OGG/Opus (WhatsApp), WebM (navegador), MP3, M4A, WAV ou AAC. O conteúdo é
conferido pelos primeiros bytes (um arquivo com o tipo trocado é recusado). Configure `GEMINI_API_KEY` no `.env`;
sem ela, a mídia fica guardada, o ticket é classificado só com o texto e o painel avisa que a IA não leu a mídia.

## Scripts da demo

```bash
python scripts/avaliar_triagem.py      # taxa de acerto: regras × LLM × LLM+few-shot + teste de prompt injection
python scripts/resetar_demo.py         # apaga tickets e incidentes para repetir a demo (mantém a configuração)
```

Roteiro da apresentação: [`docs/roteiro_demo.md`](docs/roteiro_demo.md).

## Como funciona

```
Canais (webhook, WhatsApp, e-mail, formulário público) → MySQL (ticket pendente, 202)
   └→ background: áudio/foto → Gemini → texto anexado ao ticket (ADR-017)
                  └→ busca tickets já revisados parecidos (few-shot, ADR-014)
                  └→ LLM com os exemplos (JSON validado) ──falha──▶ regras (fallback)
                  └→ embedding local → grupo (centroide) → incidente (≥3 em 30 min)
Atendente (painel/API): confirmar ou corrigir a triagem · marcar 1ª resposta  → a correção vira exemplo
Painel: fila · incidentes · motivos de contato · prazos em risco · SLI/error budget · precisão por versão do prompt
```

| Regra | Valor (configurável em `app_config` / `sla_policy`) |
|---|---|
| Prazo da 1ª resposta | crítica 15 min · alta 1 h · média 4 h · baixa 24 h |
| Prazo "em risco" | ≥ 75% do prazo consumido sem resposta; "estourado" ≥ 100% |
| Incidente | ≥ 3 mensagens no mesmo grupo em 30 min (cosseno com o centroide ≥ limiar) |
| SLO | 95% das primeiras respostas dentro do prazo, janela de 7 dias |
| Taxa de acerto | `1 − correções/revisados` por dimensão; agregado = 4 dimensões (assunto, urgência, sentimento, equipe). Separada por origem (`llm`/`fallback`) e por versão do prompt (`v3`, `v3+fewshot`, `regras`) |
| Idioma | resposta sugerida no idioma do cliente; plano B com respostas em pt, en e es (outros idiomas → en) |
| Few-shot | até `FEWSHOT_K` = 4 tickets revisados com similaridade ≥ `FEWSHOT_SIM_MIN` = 0,45 entram como exemplo |

### Endpoints (header `X-API-Key`, exceto `/health`)

| Método e rota | Função | Respostas |
|---|---|---|
| `POST /webhook/mensagens` | recebe uma solicitação (canais/integrações); `conversa_id` agrupa na mesma conversa; áudio e foto opcionais (`midias`) | 202, 400, 401 |
| `GET/POST /tickets/{id}/mensagens` | lê a conversa / registra resposta do atendente (texto, imagem e áudio) | 200, 201, 400, 401, 404 |
| `GET/POST /webhooks/whatsapp` · `/webhooks/instagram` | webhooks da Meta (assinatura `X-Hub-Signature-256`) | 200, 403, 503 |
| `GET /enviar` · `POST /public/mensagens` | formulário web público (sem chave, com limite de taxa) | 200 · 202, 400, 429 |
| `GET /tickets`, `GET /tickets/{id}` | fila com prazo (SLA), versão do prompt, exemplos usados e mídias | 200, 404 |
| `GET /tickets/{id}/midias/{midia_id}` | arquivo original do áudio ou da foto | 200, 404 |
| `POST /tickets/{id}/resposta` | registra a 1ª resposta | 200, 404 |
| `POST /tickets/{id}/revisao` | confirma a triagem | 204, 404, 409 |
| `POST /tickets/{id}/correcoes` | corrige assunto/urgência/sentimento/equipe/resposta | 201, 400, 404, 409 |
| `GET /correcoes` | histórico de correções | 200 |
| `GET /incidentes` | incidentes e justificativa | 200 |
| `GET /metricas` | motivos, idiomas, prazos em risco, SLI, precisão (por origem e por versão do prompt) | 200 |
| `GET /dominio` | valores permitidos de assunto, urgência, sentimento e equipe, e nomes dos idiomas | 200 |

## Estrutura

```
src/triagem/   api, pipeline, classifier (LLM), exemplos (few-shot), idioma, fallback (regras), embeddings, incidents, sla,
               corrections, metrics, canais (WhatsApp, Instagram), demo_chat/demo_email (telas /demo), email_imap, pagina_envio (formulário), ratelimit
frontend/      painel em HTML, CSS e JavaScript puros (servido pela própria API, sem build)
db/            schema.sql (DDL versionado), migrations/ (bancos existentes) e init do banco de testes
scripts/       iniciar.ps1 (sobe tudo) · simular.py (canais) · calibrar_limiar.py · avaliar_triagem.py · resetar_demo.py · criar_banco.py · teste_carga.py · backup.sh
data/          mensagens_demo.json (34 rotuladas) · rajada_demo.json · avaliacao.json (60 rotuladas) · avaliacao_idiomas.json (24 em 6 idiomas)
tests/         pytest (padrão AAA)
docs/          risks.md · slo.md · threat-model.md · deploy.md · canais.md · chat.md · calibracao_limiar.md · roteiro_demo.md · release_checklist_final.md
management/    vision · arch · adr · roadmap · specs
```

## Segurança

- Todas as consultas SQL são parametrizadas (`:param`); nenhuma concatenação.
- Webhook e API exigem `X-API-Key`; segredos só em `.env` (ignorado pelo Git).
- O texto do cliente é enviado ao LLM como dado delimitado e a saída é validada contra valores permitidos (prompt injection).
  Os exemplos do few-shot (também texto de cliente) seguem a mesma regra, e versão do prompt e exemplos nunca vêm da resposta do LLM.
- O texto da mensagem é enviado ao provedor do LLM (DeepSeek); não use dados pessoais reais na demo.
- Áudios e fotos são enviados ao Google (Gemini) para leitura. O prompt manda ignorar instruções contidas na mídia, e a
  transcrição volta como texto de cliente, que a triagem já trata como dado delimitado. O arquivo original só é
  servido com a chave, com o tipo conferido e `Content-Security-Policy: sandbox`.
- Painel protegido pela `API_KEY` (guardada só na aba do navegador); em produção a API recusa subir com segredos fracos.
- Formulário público com limite de taxa por IP e global, honeypot e sem revelar a classificação.

## Limitações conhecidas

- O limiar de incidentes depende do modelo de embeddings e precisa ser calibrado (acima).
- Prazos contam 24x7 (sem horário comercial) e não há notificação push.
- Sem autenticação por atendente (chave única do painel): correções não registram autoria.
- O few-shot propaga as correções, inclusive as erradas: acompanhe a taxa de acerto por versão do prompt e rode `scripts/avaliar_triagem.py` antes de mudar o prompt.
- Limitador de taxa em memória: rodar a API com 1 worker. Sem alta disponibilidade (servidor único).
