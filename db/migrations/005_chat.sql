-- Bancos criados antes do chat de atendimento. Rode uma vez (depois da 004):
--   mysql -u root -p hackathon < db/migrations/005_chat.sql
ALTER TABLE tickets ADD COLUMN conversa_id VARCHAR(190) NULL AFTER external_id;
ALTER TABLE tickets ADD INDEX idx_tickets_conversa (canal, conversa_id, id);
CREATE TABLE IF NOT EXISTS messages (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_id BIGINT UNSIGNED NOT NULL,
  direcao VARCHAR(10) NOT NULL,
  autor VARCHAR(120) NULL,
  texto TEXT NOT NULL,
  external_id VARCHAR(220) NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_msg_ticket (ticket_id, id),
  UNIQUE KEY uq_msg_externo (external_id),
  CONSTRAINT fk_msg_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- Tickets antigos: copia o texto original como primeira mensagem da conversa.
INSERT INTO messages (ticket_id, direcao, autor, texto, created_at)
SELECT t.id, 'entrada', t.cliente, t.texto, t.received_at FROM tickets t
WHERE NOT EXISTS (SELECT 1 FROM messages m WHERE m.ticket_id = t.id);
