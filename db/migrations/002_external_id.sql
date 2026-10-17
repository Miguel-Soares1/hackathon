-- Bancos criados antes dos canais reais (WhatsApp/e-mail): adiciona o id externo e a idempotência.
-- Rode uma vez:  mysql -u root -p hackathon < db/migrations/002_external_id.sql
ALTER TABLE tickets ADD COLUMN external_id VARCHAR(190) NULL AFTER texto;
ALTER TABLE tickets ADD UNIQUE KEY uq_tickets_canal_externo (canal, external_id);
