-- Bancos criados antes do envio de áudio e foto (ADR-017): cria a tabela das mídias.
-- Rode uma vez:  docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon < db/migrations/006_midias.sql
-- (equivale a rodar o schema de novo: python scripts/criar_banco.py)
CREATE TABLE IF NOT EXISTS ticket_midias (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_id BIGINT UNSIGNED NOT NULL,
  tipo VARCHAR(10) NOT NULL,
  mime VARCHAR(60) NOT NULL,
  tamanho INT UNSIGNED NOT NULL,
  dados MEDIUMBLOB NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'pendente',
  conteudo TEXT NULL,
  processed_at DATETIME NULL,
  INDEX idx_midias_ticket (ticket_id),
  CONSTRAINT fk_midia_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
