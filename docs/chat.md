# Chat do atendimento e integração com o chat do cliente

No painel, na página **Atendimento**, os clientes aparecem em cartões com o **canal de origem** em destaque (etiqueta e ícone no avatar: WhatsApp, Instagram, E-mail, Chat; filtro por canal no topo) (**Em espera**: o cliente falou por último; **Em atendimento**: a vez é do cliente; **Finalizados**: encerrados ou cancelados). Os botões **Encerrar atendimento** e **Cancelar** finalizam a conversa (`POST /tickets/{id}/encerrar` com `desfecho`), e **Reabrir** a devolve à fila (`POST /tickets/{id}/reabrir`). Se o cliente escrever depois de finalizado, nasce um atendimento novo. Ao abrir um cartão, o painel mostra a conversa do cliente (balões de cliente e atendente) e uma caixa para responder (Enter envia; Shift+Enter quebra a linha).
Nesta versão o chat é **de demonstração**: a resposta do atendente fica gravada na conversa, mas **não é enviada** ao canal do cliente.
A integração com o chat do cliente usa a API abaixo (todas as rotas exigem o header `X-API-Key`).

## Como as mensagens viram conversa
- `POST /webhook/mensagens` aceita `conversa_id` (opcional): identifica o cliente no canal (id da sessão do chat, telefone, e-mail).
- Mensagens com o mesmo `canal` + `conversa_id` entram **na mesma conversa** enquanto ela está aberta ou foi respondida há menos de 24 h. Depois disso nasce um ticket novo.
- Sem `conversa_id`, cada mensagem é um ticket (comportamento anterior). WhatsApp usa o número como `conversa_id`; Instagram, o id do remetente; e-mail, o endereço do remetente. As telas `/demo/*` seguem a mesma regra.
- Resposta: `{"status": "pendente"}` (ticket novo, vai para a IA), `"anexada"` (entrou numa conversa existente) ou `"duplicado"` (mesmo `external_id` já recebido).
- Mensagens anexadas não são reclassificadas: a triagem e o SLA valem para a primeira mensagem do ticket.

## Integrar o chat do cliente
1. **Cliente → sistema:** `POST /webhook/mensagens` com `{"canal": "chat", "cliente": "Nome", "conversa_id": "<id da sessão>", "texto": "...", "external_id": "<id da mensagem>"}`.
2. **Sistema → cliente (resposta do atendente):** o chat do cliente consulta `GET /tickets/{ticket_id}/mensagens?depois_de=<último id visto>` a cada poucos segundos e exibe as mensagens com `direcao = "saida"`. O `ticket_id` vem da resposta do passo 1.
3. **Atendente por API (opcional):** `POST /tickets/{ticket_id}/mensagens` com `{"texto": "...", "autor": "Nome"}`.
   Para mandar imagem ou áudio, inclua `"midias": [{"tipo": "imagem", "mime": "image/png", "dados_base64": "..."}]`
   (até 3, 8 MB cada; o texto vira opcional). Cada mensagem da conversa traz `midias` com `id`, `tipo` e `mime`;
   o arquivo sai em `GET /tickets/{ticket_id}/midias/{id}`. Sem texto, a mensagem leva o rótulo "📷 Imagem" ou "🎙 Áudio".

A primeira resposta do atendente (pelo chat do painel ou pela API) registra o prazo de resposta (SLA). Respostas seguintes não o alteram.

## Banco de dados
Bancos já existentes: rode `db/migrations/005_chat.sql` uma vez (depois da `004`).
