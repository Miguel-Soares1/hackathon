# Checklist de Prontidão para Produção (DoD)

Estado verificado no desenvolvimento. Itens abertos estão desmarcados.

- [x] **Fundamentos:** estrutura `src/`, `db/`, `docs/`, `tests/`; README com execução passo a passo; `.env` fora do Git.
- [x] **Produto mínimo:** API sobe conectada ao MySQL; webhook, classificação, SLA, correções, incidentes e painel operam de ponta a ponta (validado com o simulador e as 34 mensagens de demo).
- [x] **Evidência de qualidade:** SQL 100% parametrizado; `pytest` com testes unitários e de integração passando.
- [x] **Decisões documentadas:** 14 ADRs em `management/adr.md` (mínimo exigido: 2).
- [x] **Evidência de requisitos:** specs 1 a 8 com critérios de aceitação mapeados para rotas e testes (pendências da Spec 8 abaixo).
- [x] **Governança:** matriz de riscos (`risks.md`), SLO e política de error budget (`slo.md`).
- [x] **Segurança:** sem segredos no código; schema versionado em `db/`; threat modeling (`threat-model.md`).
- [x] **Limiar de similaridade calibrado com o modelo de embeddings real:** 0,60, com 2/2 incidentes e 0 falsos em 200 ordens aleatórias (`docs/calibracao_limiar.md`).
- [x] **Auditoria cruzada (ensaio):** clone limpo seguindo só o README, no Windows: ~3 min até a API rodar com 34 mensagens e 2 incidentes, com PyTorch e o modelo já em cache (numa máquina nova, some o download, de ~5 a 8 min). Achado corrigido: o README mandava `cd Hackathon`, uma pasta que não existe. **Pendente:** repetir com outra pessoa do grupo.
- [x] **Teste com a chave real do LLM** (DeepSeek), 34 mensagens: 89,2% de acerto agregado (assunto 94,1%, urgência 82,4%, sentimento 91,2%), JSON válido 34/34, prompt injection resistido 3/3; plano B por regras: 80,4% (`scripts/avaliar_triagem.py`).
- [x] **Ensaio com falha:** API do LLM inacessível → 2 tentativas → plano B (`origem = fallback`) em ~5 s.
- [x] **Aprendizado com correções (Spec 6, ADR-014):** few-shot dinâmico com testes (`tests/test_exemplos.py`), versão do prompt gravada em cada triagem e conjunto de avaliação separado com 60 mensagens.
- [ ] **Linha de base do prompt `v2` × `v2+fewshot`** com a chave real: `python scripts/avaliar_triagem.py --saida data/avaliacoes/v2.json`.
- [ ] **Deploy em produção:** seguir `docs/deploy.md`; conferir HTTPS, 401 sem chave, formulário público e login do painel.
- [ ] **Teste de carga no ambiente real:** `scripts/teste_carga.py` com a chave do LLM (medir tempo até classificar e proporção de `fallback`).
- [ ] **Backup agendado** (`scripts/backup.sh` no cron) e testado com uma restauração.

