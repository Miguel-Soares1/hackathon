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

**Status:** accepted (canais reais acrescentados pelo ADR-013)

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

**Decisão:** gerar embeddings das mensagens (modelo local, ADR-008) e compará-las por similaridade de cosseno com o centroide dos grupos abertos. Um incidente é aberto quando um grupo atinge 3 ou mais mensagens dentro de uma janela de 30 minutos. O limiar inicial era 0,70; calibrado com as mensagens de demo rotuladas, passou a 0,60 (`docs/calibracao_limiar.md`).

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

---

## ADR-012: Deploy em produção com Docker Compose, HTTPS automático e entrada pública limitada

**Status:** accepted (opcional: a demo roda localmente; os arquivos de deploy ficam para uso futuro)

**Contexto:** o sistema será exposto na web e precisa receber demanda real, mas os canais reais (WhatsApp, e-mail) ainda não estão integrados. O painel mostra texto de clientes e o LLM tem custo por chamada.

**Decisão:** empacotar em uma imagem Docker e subir com `docker-compose.prod.yml` (MySQL, API e Caddy; a API serve também o painel, ADR-010). O Caddy faz HTTPS automático e é o único serviço com portas publicadas. A entrada de demanda se dá por (1) um formulário web público em `/enviar`, protegido por limite de taxa por IP e global, honeypot e limite de tamanho, e (2) o webhook autenticado por `X-API-Key` para integrações. O painel exige a `API_KEY`. Em produção, a API recusa subir com segredos fracos.

**Consequências:**
- Um único servidor com 1 vCPU/2 GB roda tudo (embeddings em ONNX, ADR-011); simples de operar e de reproduzir.
- O formulário público abre uma superfície de abuso, mitigada por limites (ver `docs/threat-model.md`, T9 e T10).
- O limitador de taxa é em memória: a API deve rodar com um único worker.
- Não há alta disponibilidade; backup diário do MySQL via `scripts/backup.sh`.

## ADR-013: Canais reais — WhatsApp Cloud API (webhook) e e-mail por IMAP (leitor separado)

**Status:** accepted

**Contexto:** o hackathon pede testar com mensagens reais de WhatsApp e e-mail, com custo zero e prazo de 26 horas. O sistema só tinha o webhook genérico.

**Decisão:** WhatsApp: endpoint `/webhooks/whatsapp` na API, para a Cloud API oficial da Meta (número de teste gratuito), com verificação por token e assinatura HMAC. E-mail: processo `triagem.email_imap` que lê mensagens não lidas por IMAP (senha de app) e chama o webhook genérico. Ambos usam `external_id` (id da mensagem) com unicidade `(canal, external_id)` para idempotência. O sistema só recebe: a resposta ao cliente continua sendo feita pelo atendente fora dele.

**Alternativas descartadas:** bibliotecas não oficiais de WhatsApp Web (risco de banimento do número, frágeis); webhook de provedor de e-mail transacional (exige domínio e DNS, tempo demais para 26 h); Twilio (pago após o teste).

**Consequências:**
- Sem custo e sem domínio próprio de e-mail; o número de teste da Meta limita destinatários (R15) e o token temporário expira (R14).
- IMAP é por varredura (30 s): latência de até 30 s para e-mail, aceitável frente ao menor prazo de SLA (15 min).
- Migração de bancos existentes: `db/migrations/002_external_id.sql`.
- Instagram Direct entrou depois pelo mesmo caminho (`/webhooks/instagram`, mesma assinatura HMAC da Meta).
- Telas `/demo/*` simulam os três canais na apresentação passando pelo mesmo conversor do canal real; ficam desligadas em produção.

## ADR-014: A triagem aprende com as correções por few-shot dinâmico (sem fine-tuning)

**Status:** accepted

**Contexto:** queremos que a IA melhore com as correções do atendente (Spec 3). A API do DeepSeek não oferece fine-tuning, e treinar um modelo próprio exige GPU, milhares de exemplos e mais tempo do que o hackathon permite.

**Decisão:** antes de classificar, buscar entre os tickets **já revisados** (confirmados ou corrigidos) os `FEWSHOT_K` (padrão 4) mais parecidos com a mensagem nova, pelo cosseno dos embeddings locais já usados no agrupamento (ADR-008), com similaridade mínima `FEWSHOT_SIM_MIN` (padrão 0,45). Eles entram no prompt como exemplos, com os valores **efetivos** (a última correção, não a predição original). Cada classificação grava `prompt_version` (`v1` = prompt original, `v2` = prompt com critérios, `v3` = idioma do cliente (ADR-015), cada um com ou sem `+fewshot`, e `regras`) e os ids dos exemplos usados. A taxa de acerto é medida por versão (`/metricas` → `precisao_por_versao`), e um conjunto rotulado fixo (`data/avaliacao.json`) com `scripts/avaliar_triagem.py` compara regras, LLM e LLM + few-shot antes de cada mudança de prompt.

**Alternativas descartadas:** fine-tuning (indisponível na API, caro e lento); exemplos fixos escritos à mão (não aprendem com o uso); RAG em base vetorial externa (mais infraestrutura, desnecessário na escala atual: a busca é em memória sobre até 3.000 revisados).

**Consequências:**
- Cada correção passa a valer para as próximas mensagens parecidas, sem retreino; o painel mostra quais tickets serviram de exemplo (explicabilidade).
- O prompt fica maior (≈ +80 tokens por exemplo), e o custo e a latência sobem um pouco.
- Uma correção errada do atendente também se propaga; mitigação: a taxa de acerto por versão e o eval fixo expõem regressões.
- O texto dos exemplos é conteúdo de cliente: vai delimitado por tags, que são removidas do texto (mesma defesa contra prompt injection da mensagem principal).
- Falha na busca nunca impede a classificação (segue sem exemplos). Migração de bancos existentes: `db/migrations/003_prompt_version.sql`.

---

## ADR-015: Idioma do cliente identificado pelo LLM, conferido localmente e respeitado na resposta

**Status:** accepted

**Contexto:** clientes também escrevem em inglês, espanhol e outros idiomas. O prompt mandava responder sempre em português, e o plano B só tinha respostas e palavras-chave em português.

**Decisão:** o LLM devolve o campo `idioma` (ISO 639-1) e escreve a `resposta_sugerida` no mesmo idioma do cliente; assunto, urgência, sentimento e equipe continuam com os códigos em português (prompt `v3`). Um detector local (`src/triagem/idioma.py`, palavras funcionais e acentos de pt, en, es, fr, it e de, sem rede e sem modelo) completa o idioma quando o LLM não o informa, corrige o idioma quando a detecção local é forte e diverge, e recusa uma resposta escrita claramente em outro idioma (nova tentativa e, se persistir, plano B). O plano B detecta o idioma e responde com textos prontos em pt, en ou es; os demais idiomas recebem a resposta em inglês. O idioma é gravado em `classifications.idioma` e aparece no painel e em `/metricas`.

**Alternativas descartadas:** biblioteca de detecção de idioma (dependência e modelo a mais para um sinal que o LLM já dá); traduzir a mensagem para português antes de classificar (segunda chamada ao LLM e perda de nuances); confiar só no LLM (sem rede de segurança quando ele responde no idioma errado).

**Consequências:**
- O atendente recebe a resposta pronta no idioma do cliente; a fila e as métricas mostram de onde vem a demanda.
- O detector local é conservador: em textos curtos ou mistos ele não contraria o LLM (só a detecção "forte", com ao menos 3 sinais e o dobro do segundo idioma, decide). Zero erros nas 94 mensagens em português dos conjuntos rotulados.
- O prompt cresce ~140 tokens (~740 sem exemplos, ~1.130 com 4 exemplos).
- As palavras-chave do plano B em outros idiomas são poucas: a classificação por regras fora do português é fraca (65% de acerto agregado em `data/avaliacao_idiomas.json`, contra o idioma detectado em 24/24).
- Migração de bancos existentes: `db/migrations/004_idioma.sql`.
---

## ADR-016: Chat de atendimento com conversa por cliente e integração por API

**Status:** accepted

**Contexto:** o atendente precisa conversar com o cliente na própria tela de atendimento, e o chat do cliente já existe fora deste sistema e será integrado depois. Até lá o chat roda local, de demonstração.

**Decisão:** tabela `messages` (entrada/saída) ligada ao ticket; mensagens do mesmo `canal` + `conversa_id` entram no mesmo ticket por até 24 h após a última resposta. A resposta do atendente é gravada e conta como primeira resposta para o SLA, mas não é enviada a nenhum canal. A integração futura usa `GET/POST /tickets/{id}/mensagens`, com polling por `depois_de`. Ver `docs/chat.md`.

**Alternativas descartadas:** WebSocket entre painel e chat do cliente (mais complexo e não necessário para a demo); enviar por WhatsApp/SMTP agora (exige credenciais e só vale com o canal real); um ticket novo por mensagem (quebra o fluxo de conversa e infla a fila).

**Consequências:**
- O polling basta para o volume esperado; pode virar push depois sem mudar o modelo de dados.
- Mensagens anexadas não são reclassificadas nem entram no agrupamento de incidentes.
- No painel HTML (ADR-010), o layout segue a dashboard de atendimento desenhada para o chat (menu lateral; página Atendimento com cartões "Em espera" × "Respondidos", conversa e a triagem num painel recolhível). A conversa atualiza a cada ciclo de atualização automática, não em tempo real.
- WhatsApp, Instagram e e-mail usam o remetente como `conversa_id`, inclusive nas telas `/demo/*`.

## ADR-017: Áudio e foto do cliente lidos pelo Gemini e convertidos em texto antes da triagem

**Status:** accepted

**Contexto:** clientes querem mandar áudio e foto (print de erro, boleto, produto danificado), não só texto. O DeepSeek só entende texto, então outra IA precisa ler a mídia.

**Decisão:** o webhook aceita até 3 mídias por mensagem em base64 (`midias: [{tipo, mime, dados_base64}]`, até 8 MB cada), validadas pelo tipo declarado **e** pelos primeiros bytes do arquivo, e guardadas em `ticket_midias` na mesma transação do ticket. No background, antes da triagem, o **Gemini** (`GEMINI_MODEL`, padrão `gemini-3.8-flash`) transcreve cada áudio e descreve cada foto em uma chamada própria. O resultado é anexado ao texto do ticket com um rótulo (`[Áudio transcrito pela IA]: …`), e daí em diante triagem, few-shot e incidentes funcionam sem mudança. As chamadas acontecem fora de transação e o resultado é gravado de uma vez, então reprocessar após uma queda não duplica o texto.

**Alternativas descartadas:** Whisper local + outro modelo para foto (duas peças e, sem GPU, transcrição lenta no notebook); OCR local (lê texto, mas não entende foto sem texto); guardar o arquivo em disco (mais um volume para backup; o MEDIUMBLOB basta na escala do projeto).

**Consequências:**
- Uma chave só (Google AI Studio, com plano gratuito) cobre áudio e foto. O conteúdo da mídia sai do notebook para o Google.
- Sem chave ou com falha do Gemini, o ticket não trava: segue com o texto que houver, a mídia fica com status `erro` e o painel avisa o atendente, que pode ouvir ou ver o original.
- A transcrição é texto controlado pelo cliente: entra na triagem pelo mesmo caminho delimitado da mensagem (defesa contra prompt injection), e o prompt do Gemini manda ignorar instruções contidas na mídia.
- O arquivo original é servido só com a chave, com o tipo conferido e `Content-Security-Policy: sandbox`.
- O atendente também envia imagem e áudio na resposta do chat: a mídia fica ligada à mensagem (`ticket_midias.mensagem_id`), com status `enviado`, aparece no balão da conversa e não passa pela IA. Sem texto, a mensagem leva um rótulo ("📷 Imagem") para quem só lê texto.
- Migração de bancos existentes: `db/migrations/006_midias.sql` e `db/migrations/009_midias_chat.sql`.

---

## ADR-018: Login do painel por usuário e senha, com sessões no banco

**Status:** revogado. O sistema de contas foi retirado: o painel entra com a `API_KEY` (threat model T11), o atendente informa o próprio nome ("Seu nome no chat", enviado no header `X-Atendente`) e o plantão é marcado por navegador (ADR-020). Bancos que já têm as tabelas `usuarios` e `sessoes` podem mantê-las; o código não as usa mais.

**Contexto:** o painel pedia a `API_KEY` do servidor toda vez que era aberto, e todos os atendentes usavam a mesma chave: não havia como saber quem respondeu, tirar o acesso de uma pessoa ou trocar a senha sem trocar a chave das integrações.

**Decisão:** tabelas `usuarios` (usuário único, nome, papel `admin` ou `atendente`, ativo) e `sessoes`. A senha é guardada com PBKDF2-SHA256 (390 mil iterações, sal aleatório, biblioteca padrão do Python). O login devolve um token aleatório; no banco fica só o SHA-256 dele. A sessão dura 12 h, ou 30 dias com "manter conectado" (guardada no `localStorage` do navegador). As rotas do painel aceitam `Authorization: Bearer <token>`; a `X-API-Key` continua valendo só para integrações e não administra usuários. O primeiro administrador é criado na tela inicial quando o banco não tem usuários, mediante a `API_KEY` do servidor. A área **Administração** cria usuários, troca nome e papel, desativa e redefine senhas; cada usuário troca a própria senha.

**Alternativas descartadas:** manter a chave única (sem identidade nem revogação); JWT sem estado (não dá para derrubar uma sessão ao desativar alguém); bcrypt/argon2 (dependência nova; PBKDF2 da biblioteca padrão atende ao caso).

**Consequências:**
- A resposta no chat sai assinada com o nome de quem está logado (não dá para assinar como outra pessoa).
- Desativar um usuário ou redefinir a senha derruba as sessões abertas dele; trocar a própria senha derruba as outras sessões e mantém a atual.
- O sistema nunca fica sem administrador ativo; login errado não diz se o usuário existe; tentativas limitadas a 10 por minuto por IP.
- Bancos existentes: `db/migrations/007_usuarios.sql`.

---

## ADR-019: Urgência baixa e média atendidas pela IA; alta e crítica por um atendente

**Status:** accepted

**Contexto:** a equipe quer que a IA resolva sozinha os atendimentos simples e que as pessoas fiquem com o que é urgente. Uma conversa simples que se arrasta também precisa chegar a uma pessoa.

**Decisão:** depois da triagem (`atendimento_ia.iniciar`), urgência **baixa ou média** com triagem feita pelo LLM: a IA envia a resposta sugerida ao cliente e passa a responder cada nova mensagem com a conversa como contexto (`atendimento_ia.responder`, `classifier.sugerir_resposta`). Urgência **alta ou crítica**, ou triagem pelo plano B: vai direto para a fila do Atendimento. A IA passa a conversa para um atendente (`escalar`) quando ela passa de `ia_max_minutos` (15) desde a 1ª mensagem, quando a IA já respondeu `ia_max_respostas` (5) vezes, quando o cliente pede uma pessoa ou quando a IA falha; o cliente é avisado no idioma dele. Se um atendente responde num atendimento da IA, ele assume. Os limites e a chave `ia_auto_ativo` ficam em `app_config`. Coluna `tickets.modo` (`ia` | `humano`), `escalado_em` e `motivo_escalada` (migração 012).

**Consequências:**
- As respostas da IA são assinadas como "Assistente NEXUS (IA)" e não contam como resposta humana: um atendimento transferido volta para "Em espera" até uma pessoa responder. A 1ª resposta da IA conta para o prazo (SLA).
- O painel mostra a aba "🤖 IA atendendo", o selo "↗ veio da IA" com o motivo e as falas da IA destacadas.
- Erros da IA viram transferência, nunca silêncio para o cliente.

---

## ADR-020: Painel mínimo, alerta de problema crítico para o plantão e relatório de problemas

**Status:** accepted

**Contexto:** a equipe quer a tela de atendimento com o mínimo de informação, só WhatsApp, um aviso impossível de ignorar quando aparece um problema crítico e um lugar para contar quantas vezes cada problema aconteceu, com os clientes afetados, para priorizar a solução.

**Decisão:**
- Painel: cartão com nome, hora, última mensagem e urgência (só alta e crítica); detalhe com a conversa, as mídias do cliente e a resposta. Saem o filtro por canal, a barra de filtros, a triagem e a sugestão da IA no chat. Instagram e e-mail saem da navegação das telas de demo e dos QR codes (as rotas continuam).
- Alerta: `GET /alertas` lista atendimentos críticos esperando uma pessoa e incidentes abertos nas últimas 2 h. A faixa pisca no topo do painel para todos e cada navegador marcado **de plantão** (botão no menu, guardado no próprio navegador) recebe uma notificação do Windows e um aviso sonoro, uma vez por problema. Responder o atendimento tira o alerta.
- Relatórios: tabelas `problemas` (título, características, aberto/resolvido) e `problema_ocorrencias` (identificação do cliente, atendimento opcional, observação, quem registrou). A aba mostra quantas vezes cada problema aconteceu e quantos clientes distintos; o botão "📋 Registrar problema" do atendimento já preenche o cliente e o número do atendimento. Migração 013.

**Consequências:**
- A notificação é do navegador (precisa da permissão e do painel aberto); não há envio por SMS ou e-mail aos atendentes.
- Com os dados de demonstração, os atendimentos críticos sem resposta mantêm a faixa piscando até alguém responder.

## ADR-021 — Roteamento por equipe, rascunho revisado e correções no chat

**Contexto:** o desafio pede roteamento para a equipe certa na posição de prioridade, sugestão de resposta que não é enviada sozinha, correções do atendente medindo a taxa de acerto e um painel com motivos, incidentes, prazos (SLA) em risco e precisão. A tela mínima (ADR-020) tinha tirado a sugestão e a correção do chat.

**Decisão:**
- Fila: seletor de equipe ao lado da busca; cada cartão mostra a equipe da triagem; a ordem continua a de prioridade (urgência, estado do prazo, prazo consumido).
- (Substituído pelo ADR-022: não há mais rascunho.) Atendimento humano (alta/crítica ou escalado): o rascunho da IA aparece acima do campo; "Usar no campo" só preenche o texto, o atendente revisa e envia. Se reescrever, a versão enviada fica registrada como correção de `resposta_sugerida`.
- Faixa de triagem recolhida no topo da conversa: "IA acertou" (revisão) ou "Salvar correção" (`POST /tickets/{id}/correcoes`). Urgência corrigida para alta/crítica numa conversa da IA passa a conversa para a fila de atendentes (`atendimento_ia.apos_correcao`).
- Aba Recorrência ganha o painel "Prazos (SLA) em risco" (clicável, abre o atendimento).

**Consequência:** a resposta automática da IA em urgência baixa/média (ADR-019) continua, por decisão do time; pode ser desligada com `ia_auto_ativo = 0`, e então todo atendimento usa só o rascunho revisado.

---

## ADR-022: A IA atende sozinha toda mensagem: resolve ou encaminha para a equipe

**Status:** accepted (substitui a divisão por urgência do ADR-019 e o rascunho do ADR-021)

**Contexto:** na demonstração, um cliente disse que ia cancelar tudo se o problema não fosse resolvido na hora e a IA
seguiu pedindo detalhes; alta e crítica ficavam sem resposta nenhuma até uma pessoa ver; e o rascunho para o atendente
revisar não automatizava nada. A equipe quer o atendimento automatizado: a IA resolve ou passa para quem resolve.

**Decisão:**
- Toda mensagem é atendida na hora pela IA (`atendimento_ia`). Para cada mensagem do cliente, `classifier.atender`
  devolve `resolver` (com a resposta) ou `encaminhar` (com a equipe que resolve o problema como ele está agora).
- Encaminha direto, sem perguntar ao modelo: urgência alta ou crítica, assunto cancelamento, ameaça de cancelar ou de
  sair, Procon/processo, exigência de solução imediata, pedido para falar com uma pessoa, triagem sem a IA (plano B),
  conversa da IA além dos limites de `app_config` e falha da IA (depois de uma segunda tentativa).
- Ao encaminhar, o cliente recebe um aviso fixo no idioma dele (pt, en, es; outros, em inglês) com o nome da equipe e
  "com prioridade" quando a urgência é alta ou crítica. O aviso **não** conta como 1ª resposta: o prazo (SLA) segue
  até a equipe responder. Se o problema mudou na conversa (dúvida de boleto que virou erro 500), a IA troca a equipe.
- Saem as sugestões: o rascunho no painel, o botão de gerar de novo, `POST /tickets/{id}/sugestao` e a sugestão
  recalculada a cada mensagem. As colunas `sugestao_*` ficam no banco sem uso.

**Consequências:**
- O cliente nunca fica sem resposta; a fila de cada equipe só recebe o que a IA não resolve.
- A qualidade da decisão depende do prompt `PROMPT_ATENDIMENTO`; a regra fixa cobre os casos de risco sem depender do modelo.
- `ia_auto_ativo = 0` desliga o atendimento automático (tudo vai para as pessoas, sem aviso).
