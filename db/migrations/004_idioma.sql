-- Bancos criados antes do suporte a idiomas (ADR-015): guarda o idioma do cliente em cada classificação.
-- Rode uma vez:  docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon < db/migrations/004_idioma.sql
-- Depois rode o schema de novo (python scripts/criar_banco.py) para recriar a visão vw_tickets.
ALTER TABLE classifications ADD COLUMN idioma VARCHAR(5) NOT NULL DEFAULT 'pt' AFTER resposta_sugerida;
