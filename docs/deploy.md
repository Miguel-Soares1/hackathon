# Guia de deploy (produção)

Sobe o sistema inteiro em **um servidor** com Docker Compose: MySQL, API (que serve também o painel) e Caddy (HTTPS automático).
Só as portas 80 e 443 ficam abertas; o MySQL e os serviços internos não são publicados.

```
Internet ─► Caddy (80/443, HTTPS) ─┬─ /enviar, /public/*  ─► API  (formulário público, com limite de uso)
                                   ├─ /api/*              ─► API  (X-API-Key: webhook dos canais, /tickets, /metricas)
                                   └─ tudo o mais         ─► API  (painel HTML; pede a API_KEY no navegador)
                                  API ─► MySQL
```

## O que você precisa

- Um servidor Linux (VPS) com **1 vCPU e 2 GB de RAM** no mínimo (embeddings em ONNX, sem PyTorch) e ~5 GB de disco.
- Docker e Docker Compose instalados.
- Um domínio com um registro **A** apontando para o IP do servidor (ex.: `triagem.seudominio.com`). O HTTPS depende disso.
- Firewall liberando só **80** e **443** (e 22 para você).
- (Opcional) chave da API do DeepSeek. Sem ela, funciona só com o plano B por regras.

## Passo a passo

```bash
git clone <repositório> && cd <repositório>/Hackathon
cp .env.production.example .env.production
```

Preencha o `.env.production`. Gere cada segredo com `openssl rand -hex 24` (só letras e números):

| Variável | O que é |
|---|---|
| `DOMAIN` | domínio do passo anterior |
| `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` | senhas do banco (diferentes entre si) |
| `API_KEY` | chave dos canais/integrações e de acesso ao painel (mínimo 24 caracteres) |
| `DEEPSEEK_API_KEY` | chave do LLM (opcional) |
| `PUBLIC_RATE_PER_IP_MIN` / `PUBLIC_RATE_GLOBAL_MIN` | limites do formulário público (padrão 5 por IP e 60 no total, por minuto) |

Suba tudo (a primeira construção baixa o modelo de embeddings, ~120 MB):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production ps     # todos "running"/"healthy"
```

A API **recusa subir** em produção se a `API_KEY` ou a senha do banco forem fracas ou de exemplo.

## Conferir que está funcionando

Troque `SEU_DOMINIO` e `SUA_API_KEY`:

```bash
curl -s https://SEU_DOMINIO/api/health                                   # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" https://SEU_DOMINIO/api/tickets # 401 (sem chave)
curl -s -X POST https://SEU_DOMINIO/api/webhook/mensagens \
  -H "X-API-Key: SUA_API_KEY" -H "Content-Type: application/json" \
  -d '{"canal":"whatsapp","texto":"O sistema caiu, ninguém consegue emitir nota, urgente!"}'   # 202
```

No navegador:
1. `https://SEU_DOMINIO/` → pede a `API_KEY`; depois mostra a fila com o ticket de teste.
2. `https://SEU_DOMINIO/enviar` → formulário público; envie uma mensagem e veja o ticket aparecer no painel.
3. Cadeado (HTTPS válido) no navegador. Se o certificado falhar, confira o DNS e as portas 80/443.

Confirme também que o ticket tem origem `llm` (e não `fallback`) quando a chave do DeepSeek está configurada.

## Receber demanda real

| Canal | Como integrar |
|---|---|
| **Formulário web** | divulgue `https://SEU_DOMINIO/enviar` (público, com limite de uso) |
| **WhatsApp e e-mail** | prontos: veja `docs/canais.md` (WhatsApp Cloud API em `/webhooks/whatsapp`; leitor IMAP com `--profile email`) |
| **Chat, redes, outros** | o provedor (ou uma automação, como n8n/Zapier/Make) chama `POST https://SEU_DOMINIO/api/webhook/mensagens` com o header `X-API-Key` e o corpo `{"canal": "...", "cliente": "...", "texto": "..."}` |

## Testar a carga esperada

Rode de qualquer máquina (com `API_KEY` no `.env` local). Cria tickets de verdade, então faça antes de divulgar o sistema ou limpe depois:

```bash
python scripts/teste_carga.py --url https://SEU_DOMINIO/api --total 100 --concorrencia 5
```

O relatório mostra vazão, latência do webhook (p50/p95/p99) e tempo até a classificação. Com a chave do LLM, o tempo até classificar é dominado pela latência do provedor.
Medição local sem LLM (plano B, 200 mensagens, concorrência 10): 90 msg/s de entrada, webhook p95 ≈ 190 ms, todas classificadas em ≤ 2 s.

**Dimensionamento:** cada ticket gera 1 chamada ao LLM (e 1 embedding local). A API roda com 1 worker; as chamadas ao LLM ocorrem em threads, então a vazão sustentável depende do limite de requisições por minuto do seu plano no provedor. Para centenas de mensagens por hora não há problema; acima disso, meça com o teste de carga e considere uma fila externa.

## Operação

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f api       # logs da API
docker compose -f docker-compose.prod.yml --env-file .env.production restart api       # reiniciar (tickets pendentes são reprocessados)
./scripts/backup.sh                                                                      # backup do MySQL (agende no cron)
```

Agendar o backup diário (`crontab -e`): `0 3 * * * cd /caminho/Hackathon && ./scripts/backup.sh`.
**Restaurar:** `gunzip -c backups/ARQUIVO.sql.gz | docker compose -f docker-compose.prod.yml --env-file .env.production exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hackathon'`.
Copie os backups para fora do servidor.

**Atualizar a versão:** `git pull` e rode de novo o comando `up -d --build`. O schema (`db/schema.sql`) só é aplicado na primeira criação do banco; mudanças de tabela exigem migração manual.

**Dados de demo:** não rode `simular.py` no banco de produção que receberá clientes reais; ele cria tickets fictícios.

## Segurança em produção

- HTTPS com HSTS; MySQL e serviços internos sem porta exposta; container sem root; documentação interativa da API desligada.
- `API_KEY` protege tudo, exceto `/health` e o formulário público; o painel pede a mesma chave (guardada só na aba do navegador).
- Formulário público: limite por IP e global (protege o custo do LLM), campo-armadilha contra robôs, texto limitado a 1000 caracteres, e a resposta não revela a classificação.
- O texto das mensagens é enviado ao provedor do LLM (DeepSeek). Avise os usuários e não colete dados sensíveis (o formulário já traz o aviso).
- O limitador de taxa é em memória, por processo: vale para 1 worker/container. Não aumente os workers sem trocá-lo por um limitador compartilhado.
- Ameaças e riscos: `docs/threat-model.md` e `docs/risks.md`.

## Hospedagem gerenciada (Render, Railway, Fly.io etc.)

O mesmo `Dockerfile` serve. Crie um serviço com a imagem, um MySQL gerenciado (aplique `db/schema.sql`) e defina as mesmas variáveis de ambiente (`ENVIRONMENT=production`, `TRUST_PROXY=1`, `DOCS_ENABLED=0`, `DATABASE_URL`, `API_KEY`, `DEEPSEEK_API_KEY`, `EMBEDDING_BACKEND=onnx`). A plataforma faz o HTTPS; como a API serve o painel, basta um domínio. Esse caminho não foi testado aqui.
