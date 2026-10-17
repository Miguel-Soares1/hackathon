# Checklist de Prontidão para Produção (DoD)

Estado verificado no desenvolvimento. Itens abertos estão desmarcados.

- [x] **Fundamentos:** estrutura `src/`, `db/`, `docs/`, `tests/`; README com execução passo a passo; `.env` fora do Git.
- [x] **Produto mínimo:** API sobe conectada ao MySQL; webhook, classificação, SLA, correções, incidentes e painel operam de ponta a ponta (validado com o simulador e as 34 mensagens de demo).
- [x] **Evidência de qualidade:** SQL 100% parametrizado; `pytest` com testes unitários e de integração passando.
- [x] **Decisões documentadas:** 9 ADRs em `management/adr.md` (mínimo exigido: 2).
- [x] **Evidência de requisitos:** specs 1 a 5 com critérios de aceitação mapeados para rotas e testes.
- [x] **Governança:** matriz de riscos (`risks.md`), SLO e política de error budget (`slo.md`).
- [x] **Segurança:** sem segredos no código; schema versionado em `db/`; threat modeling (`threat-model.md`).
- [ ] **Limiar de similaridade calibrado com o modelo de embeddings real** (`scripts/calibrar_limiar.py`).
- [ ] **Auditoria cruzada:** outra pessoa rodar o projeto só pelo README, cronometrado (meta: menos de 10 min).
- [ ] **Teste com a chave real do LLM** (DeepSeek) em pelo menos 20 mensagens, medindo a taxa de acerto.
- [ ] **Deploy em produção:** seguir `docs/deploy.md`; conferir HTTPS, 401 sem chave, formulário público e login do painel.
- [ ] **Teste de carga no ambiente real:** `scripts/teste_carga.py` com a chave do LLM (medir tempo até classificar e proporção de `fallback`).
- [ ] **Backup agendado** (`scripts/backup.sh` no cron) e testado com uma restauração.

