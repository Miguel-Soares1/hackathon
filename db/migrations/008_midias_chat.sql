-- Bancos criados antes do envio de imagem e áudio pelo atendente no chat (ADR-017): liga a mídia à mensagem.
-- Rode uma vez:  docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon < db/migrations/008_midias_chat.sql
ALTER TABLE ticket_midias ADD COLUMN mensagem_id BIGINT UNSIGNED NULL AFTER ticket_id;
ALTER TABLE ticket_midias ADD INDEX idx_midias_mensagem (mensagem_id);
