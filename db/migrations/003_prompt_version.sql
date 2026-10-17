-- Bancos criados antes do few-shot dinâmico (ADR-014): guarda a versão do prompt e os exemplos usados.
-- Rode uma vez:  docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon < db/migrations/003_prompt_version.sql
-- Depois rode o schema de novo (python scripts/criar_banco.py) para recriar a visão vw_tickets.
ALTER TABLE classifications ADD COLUMN prompt_version VARCHAR(30) NOT NULL DEFAULT 'v1' AFTER origem;
ALTER TABLE classifications ADD COLUMN exemplos VARCHAR(255) NULL AFTER prompt_version;
UPDATE classifications SET prompt_version = 'regras' WHERE origem = 'fallback';
