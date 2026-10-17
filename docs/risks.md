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
