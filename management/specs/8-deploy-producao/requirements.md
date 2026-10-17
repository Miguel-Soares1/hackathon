---
name: Deploy em Produção
status: implemented
references: [4, 7]
---

# Deploy em Produção

## Objetivo

Permitir colocar o sistema no ar em um único servidor, com HTTPS e segredos fortes, sem depender de quem o desenvolveu
(ADR-012).

## Escopo

- **Empacotamento:** uma imagem Docker (`Dockerfile`) sem PyTorch, com o modelo de embeddings ONNX baixado na construção.
  A API serve também o painel (ADR-010).
- **Orquestração:** `docker-compose.prod.yml` com MySQL (sem porta exposta), API, Caddy (HTTPS automático) e o leitor de
  e-mail opcional (`--profile email`).
- **Configuração:** `.env.production` a partir de `.env.production.example`; a API recusa subir com segredos fracos.
- **Operação:** `scripts/backup.sh` (backup do MySQL), `scripts/teste_carga.py` e migrações em `db/migrations/`.

## Critérios de Aceitação

- [x] Em produção, a API recusa subir com `API_KEY` curta ou de exemplo ou com a senha padrão do banco.
- [x] Com segredos fortes, a API sobe normalmente.
- [x] A documentação interativa pode ser desligada (`DOCS_ENABLED=0`).
- [x] As respostas trazem cabeçalhos de segurança; o Caddy acrescenta HSTS.
- [x] Só as portas 80 e 443 são publicadas (Caddy); MySQL e API ficam na rede interna.
- [ ] Deploy executado em um servidor real seguindo `docs/deploy.md` (HTTPS, 401 sem chave, formulário e painel).
- [ ] Backup agendado e testado com uma restauração.

Testes: `test_producao_recusa_segredos_fracos`, `test_producao_aceita_segredos_fortes`, `test_docs_podem_ser_desligados`
e `test_cabecalhos_de_seguranca_presentes` (`tests/test_api.py`). Guia: `docs/deploy.md`.

## Fora de Escopo (V2)

- Alta disponibilidade (servidor único; risco R12).
- Mais de um worker da API (o limitador de taxa é em memória).
