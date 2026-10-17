---
name: Canais Reais e Entrada Pública
status: implemented
references: [1]
---

# Canais Reais e Entrada Pública

## Objetivo

Receber demanda real, além do simulador: mensagens de WhatsApp, e-mails e um formulário web público, sem custo e sem
abrir brechas de abuso ou de custo do LLM (ADR-012, ADR-013).

## Escopo

- **WhatsApp:** `GET/POST /webhooks/whatsapp` para a WhatsApp Cloud API (número de teste gratuito da Meta), com token de
  verificação e assinatura HMAC-SHA256 do corpo bruto.
- **E-mail:** processo `triagem.email_imap` que lê mensagens não lidas por IMAP (senha de app) e as envia ao webhook.
- **Formulário público:** `GET /enviar` e `POST /public/mensagens`, sem chave, com limite de taxa por IP e global,
  honeypot e texto limitado.
- **Idempotência:** `external_id` com unicidade `(canal, external_id)`; reenvio responde `duplicado`.
- **Fora do sistema:** a resposta ao cliente continua sendo feita pelo atendente no próprio canal.

## Critérios de Aceitação

- [x] A verificação do WhatsApp devolve o desafio só com o token correto e configurado.
- [x] Um POST do WhatsApp com assinatura válida cria um ticket classificado em background; assinatura inválida, ausente ou sem segredo configurado não cria nada.
- [x] Mídias e eventos de status do WhatsApp são ignorados; só texto vira ticket.
- [x] Reenvio com o mesmo `external_id` no mesmo canal não duplica o ticket; o mesmo id em canais diferentes não conflita.
- [x] O e-mail vira mensagem com assunto, corpo sem a citação da resposta e horário em UTC; respostas automáticas, listas e no-reply são ignorados.
- [x] O leitor de e-mail só marca como lido o que a API aceitou.
- [x] O formulário público cria ticket sem chave e não revela a classificação.
- [x] O limite por IP e o global devolvem `429` com `Retry-After`; `X-Forwarded-For` só vale com `TRUST_PROXY=1`.
- [x] Honeypot preenchido descarta a mensagem sem criar ticket; texto curto ou ausente retorna `400`.
- [x] A rota pública não expõe o restante da API.

Testes: `tests/test_canais.py` e `tests/test_publico.py`. Passo a passo: `docs/canais.md`.

## Fora de Escopo (V2)

- Enviar respostas ao cliente pelo sistema.
- Número de WhatsApp de produção (o de teste aceita até 5 destinatários e o token temporário expira; riscos R14 e R15).
- Limitador de taxa compartilhado entre processos (o atual é em memória: um worker por instância).
