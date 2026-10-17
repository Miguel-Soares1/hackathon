# Testar com WhatsApp e e-mail reais

Antes: o sistema precisa estar no ar com HTTPS (veja `docs/deploy.md`). Em máquina local, use um túnel (`cloudflared tunnel --url http://localhost:8000` ou `ngrok http 8000`) e use o endereço público dele no lugar de `SEU_DOMINIO`.
Bancos criados antes desta versão: rode `db/migrations/002_external_id.sql` uma vez.

## WhatsApp (grátis, número de teste da Meta)

1. Acesse https://developers.facebook.com → **Meus apps → Criar app** → tipo **Empresa** → adicione o produto **WhatsApp**.
2. Em **WhatsApp → Configuração da API** a Meta já dá um **número de teste** gratuito. Em "Para", cadastre os números de celular que vão enviar/receber (até 5; é preciso confirmar com um código).
3. Em **Configurações do app → Básico**, copie o **Segredo do app** → `WHATSAPP_APP_SECRET`.
4. Invente um texto qualquer como `WHATSAPP_VERIFY_TOKEN` (ex.: `openssl rand -hex 16`). Coloque os dois no `.env.production` e reinicie: `docker compose -f docker-compose.prod.yml --env-file .env.production up -d`.
5. Em **WhatsApp → Configuração → Webhook → Editar**: URL de retorno `https://SEU_DOMINIO/webhooks/whatsapp`, token de verificação = o mesmo do passo 4 → **Verificar e salvar**. Depois **Gerenciar** e assine o campo **messages**.
6. **Teste:** do celular cadastrado, envie uma mensagem ao número de teste. Em segundos aparece um ticket com canal `whatsapp` no painel.

Observações: o token de acesso temporário da Meta expira em ~24 h (só afeta enviar; receber continua). O sistema **não responde** o cliente: o atendente responde pelo WhatsApp e marca "respondido" no painel.

## E-mail (básico, IMAP)

1. Crie/use uma caixa dedicada (ex.: Gmail `triagem.seunome@gmail.com`). Ative a verificação em duas etapas e gere uma **Senha de app** (https://myaccount.google.com/apppasswords). Em outros provedores, ative IMAP e use a senha/app password.
2. No `.env.production`: `IMAP_HOST=imap.gmail.com`, `IMAP_USER=<o e-mail>`, `IMAP_PASSWORD=<senha de app>`.
3. Suba o leitor: `docker compose -f docker-compose.prod.yml --env-file .env.production --profile email up -d --build`.
4. **Teste:** envie um e-mail de outra conta para essa caixa. Em até 30 s vira um ticket com canal `email` (assunto + corpo; respostas automáticas e no-reply são ignorados). Ver o log: `docker compose ... logs -f email`.
5. Sem Docker (teste rápido): `API_URL=http://127.0.0.1:8000 API_KEY=... IMAP_HOST=... IMAP_USER=... IMAP_PASSWORD=... python -m triagem.email_imap --uma-vez`.

Cuidado: o leitor processa e-mails **não lidos** da pasta INBOX e os marca como lidos; use uma caixa só para o projeto.

## Roteiro de demonstração (5 min)

1. Mande por WhatsApp: "meu pix não caiu e preciso do dinheiro hoje" → urgência alta, financeiro.
2. Mande por e-mail: assunto "Cobrança duplicada", corpo com reclamação → cobrança, financeiro.
3. De 3 celulares/contas diferentes, mande a mesma queixa ("não consigo entrar, conta bloqueada") → o painel mostra o **incidente**.
4. Corrija uma classificação no painel e mostre a precisão de triagem mudando.
