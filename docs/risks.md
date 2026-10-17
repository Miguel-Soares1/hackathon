# Matriz de Riscos

Probabilidade (P) e Impacto (I) de 1 (baixo) a 3 (alto). Score = P x I. Resposta: mitigar, evitar, transferir ou aceitar.

| # | Risco | P | I | Score | Resposta | Gatilho de ação |
|---|-------|---|---|-------|----------|-----------------|
| R1 | API do LLM fora do ar ou lenta durante a demo | 2 | 3 | 6 | Mitigar: plano B por regras (ADR-009), timeout e nova tentativa | 2 falhas seguidas do LLM → alternar para `fallback` e avisar o time |
| R2 | LLM classifica errado (assunto ou urgência) | 3 | 2 | 6 | Mitigar: correção do atendente e medição da taxa de acerto | Taxa de acerto da urgência abaixo de 80% → revisar prompt e exemplos |
| R3 | JSON inválido devolvido pelo LLM | 2 | 2 | 4 | Mitigar: validação, uma nova tentativa e plano B | Mais de 5% de respostas inválidas → ajustar prompt/formato |
| R4 | Limiar de similaridade mal calibrado (falsos incidentes ou incidentes perdidos) | 3 | 2 | 6 | Mitigar: calibrar com mensagens de demo rotuladas; limiar configurável | Falso incidente ou incidente perdido no teste → recalibrar |
| R5 | Falha na demo (ambiente, rede, modelo de embeddings não baixado) | 2 | 3 | 6 | Mitigar: `docker compose`, pré-download do modelo, ensaio ponta a ponta e dados de demo prontos | Ensaio falhar em máquina limpa → corrigir o README antes de qualquer novo recurso |
| R6 | Vazamento da chave do LLM ou de credenciais do banco | 1 | 3 | 3 | Evitar: `.env` fora do Git, `.env.example` sem valores | Segredo detectado em commit → revogar a chave imediatamente |
| R7 | SQL Injection | 1 | 3 | 3 | Evitar: consultas 100% parametrizadas e revisão | Qualquer concatenação encontrada no review → bloquear o merge |
| R8 | Prompt injection no texto do cliente | 2 | 2 | 4 | Mitigar: texto tratado como dado, validação da saída contra valores permitidos | Classificação fora do conjunto permitido → rejeitar e usar plano B |
| R9 | Estouro do prazo de 26 h (escopo grande) | 2 | 3 | 6 | Mitigar: priorizar Specs 1 e 4; cortar recursos avançados primeiro | Spec 1 não concluída em 8 h de projeto → reduzir escopo das Specs 2 e 3 |
| R10 | Custo da API acima do esperado | 1 | 2 | 2 | Aceitar/monitorar: 1 chamada por ticket, registro em `budget.md` | Custo acumulado acima do teto definido → pausar chamadas de teste |
| R11 | Abuso do formulário público gera custo e enche a fila | 2 | 2 | 4 | Mitigar: limite por IP e global, honeypot, texto curto | Mais de 20 respostas 429/h ou custo diário acima do teto → baixar `PUBLIC_RATE_*` ou desligar a rota `/enviar` |
| R12 | Perda de dados do servidor único (sem alta disponibilidade) | 1 | 3 | 3 | Mitigar: `scripts/backup.sh` diário e cópia fora do servidor | Backup mais antigo que 24 h → rodar o backup manualmente e verificar o cron |
| R13 | Vazão do LLM insuficiente para a demanda real (limite de requisições do provedor) | 2 | 2 | 4 | Mitigar: plano B por regras, teste de carga antes de divulgar | Tickets `pendente` por mais de 2 min ou origem `fallback` acima de 20% → revisar plano/limites do provedor |
| R14 | Token de acesso temporário do WhatsApp (teste) expira e o canal para sem aviso | 3 | 2 | 6 | Mitigar: conferir o token antes da demonstração; gerar token permanente (usuário do sistema) se for usar por mais de 24 h | Mensagem de teste não vira ticket em 1 min → renovar o token e conferir a assinatura |
| R15 | Número de teste do WhatsApp só conversa com destinatários cadastrados (até 5) e exige a janela de 24 h do cliente | 3 | 1 | 3 | Aceitar: cadastrar os números dos avaliadores no painel da Meta antes da demonstração | Avaliador não consegue enviar → cadastrar o número |
