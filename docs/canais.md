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

## Instagram Direct (mesmo app da Meta)

Pré-requisito da Meta: conta do Instagram **profissional** (empresa ou criador) ligada a uma Página do Facebook.

1. No mesmo app de desenvolvedor do WhatsApp, adicione o produto **Instagram** (API do Instagram com login do Instagram ou do Facebook) e conecte a conta profissional.
2. Invente um `INSTAGRAM_VERIFY_TOKEN` e coloque no `.env.production`. O segredo de assinatura é o **Segredo do app**: se for o mesmo app do WhatsApp, não precisa de mais nada (o sistema usa `WHATSAPP_APP_SECRET`); se for outro app, defina `INSTAGRAM_APP_SECRET`. Reinicie a API.
3. Em **Webhooks** do produto Instagram: URL `https://SEU_DOMINIO/webhooks/instagram`, token = o do passo 2 → **Verificar e salvar**. Assine o campo **messages**.
4. Na conta do Instagram: **Configurações → Mensagens → Ferramentas conectadas → Permitir acesso às mensagens**.
5. **Teste:** de outra conta do Instagram (que tenha papel de testador no app enquanto ele estiver em modo de desenvolvimento), mande uma DM. Vira um ticket com canal `instagram`; o cliente aparece como `instagram:<id>` (o Instagram manda só o id, não o @).

Ecos (respostas enviadas pela própria empresa), reações, anexos e leituras são ignorados. O sistema **não responde** pelo Instagram.

## E-mail (básico, IMAP)

1. Crie/use uma caixa dedicada (ex.: Gmail `triagem.seunome@gmail.com`). Ative a verificação em duas etapas e gere uma **Senha de app** (https://myaccount.google.com/apppasswords). Em outros provedores, ative IMAP e use a senha/app password.
2. No `.env.production`: `IMAP_HOST=imap.gmail.com`, `IMAP_USER=<o e-mail>`, `IMAP_PASSWORD=<senha de app>`.
3. Suba o leitor: `docker compose -f docker-compose.prod.yml --env-file .env.production --profile email up -d --build`.
4. **Teste:** envie um e-mail de outra conta para essa caixa. Em até 30 s vira um ticket com canal `email` (assunto + corpo; respostas automáticas e no-reply são ignorados). Ver o log: `docker compose ... logs -f email`.
5. Sem Docker (teste rápido): `API_URL=http://127.0.0.1:8000 API_KEY=... IMAP_HOST=... IMAP_USER=... IMAP_PASSWORD=... python -m triagem.email_imap --uma-vez`.

Cuidado: o leitor processa e-mails **não lidos** da pasta INBOX e os marca como lidos; use uma caixa só para o projeto.

## Simulador de canais para apresentação (local, sem contas reais, sem túnel)

Com a API rodando, abra **http://localhost:8000/demo** (abas WhatsApp · Instagram · E-mail):

| Tela | O que imita | Por onde a mensagem passa |
|---|---|---|
| `/demo/whatsapp` | conversa no celular | JSON idêntico ao da Meta → `canais.mensagens_whatsapp` |
| `/demo/instagram` | Direct no celular | JSON idêntico ao da Meta → `canais.mensagens_instagram` |
| `/demo/email` | webmail | e-mail RFC 5322 → `canais.email_para_mensagem` (o mesmo do IMAP) |

Ou seja: do conversor em diante (ticket, triagem, incidentes, prazos, painel) é exatamente o caminho real.
Nas telas, **o apresentador é o cliente**: escolhe um cliente fictício e escreve no WhatsApp, no Instagram ou no
e-mail. A tela do cliente nunca mostra a classificação; a triagem aparece só no **painel** (http://localhost:8000).
- **Primeira mensagem** (abre o ticket): chega a confirmação automática com o protocolo e, com a opção
  **Resposta automática da IA** ligada, a resposta sugerida pela IA (com o aviso de encaminhamento para o time).
- **Mensagens seguintes** do mesmo cliente entram **na mesma conversa** (ADR-016) e esperam o atendente.
- **O atendente responde pelo painel** (Atendimento → abrir o cartão → Enviar) e a resposta aparece no celular do
  cliente em até 3 s (tiques azuis / "Visto") ou como `Re: assunto` na Caixa de entrada do e-mail. No painel, o cartão
  volta para **Em espera** com o selo "cliente respondeu" quando o cliente escreve de novo.

A tela lê a própria conversa por `/demo/conversa/{ticket}?senha=…&depois_de=…`: a senha volta no envio (HMAC com um
segredo que muda a cada subida da API), então ninguém lê a conversa de outro ticket, e a rota só devolve a resposta
sugerida e as mensagens do atendente, nunca a classificação. A resposta automática da IA é só da demonstração: não
fica gravada na conversa nem conta como 1ª resposta (SLA); quem conta é o atendente.

- **Cliente:** escolha na lista ou clique em **Outro cliente**. Mandar "Conta bloqueada" com 3 clientes diferentes gera um **incidente**.
- Ligadas por padrão em desenvolvimento; **sempre desligadas** com `ENVIRONMENT=production`. Para desligar no dev: `DEMO=0`.

## Roteiro de demonstração (5 min)

1. Mande por WhatsApp (real ou `/demo/whatsapp`, botão "Pix não caiu") → urgência alta/crítica, financeiro.
2. Mande por e-mail (real ou pela tela `/demo/email`, botão "Cobrança duplicada") → cobrança, financeiro.
3. De 3 clientes diferentes — misture WhatsApp, Instagram e e-mail — mande a mesma queixa ("conta bloqueada") → o painel mostra o **incidente**, juntando canais.
4. Corrija uma classificação no painel e mostre a precisão de triagem mudando.
