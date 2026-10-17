-- Bancos criados antes do encerramento do atendimento. Rode uma vez (depois da 005):
--   mysql -u root -p hackathon < db/migrations/006_encerramento.sql
-- e depois `python scripts/criar_banco.py` para recriar a view vw_tickets.
ALTER TABLE tickets ADD COLUMN encerrado_em DATETIME NULL AFTER first_response_at;
ALTER TABLE tickets ADD COLUMN encerrado_por VARCHAR(120) NULL AFTER encerrado_em;
CREATE TABLE IF NOT EXISTS relatorios (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  desfecho VARCHAR(20) NOT NULL,
  atendente VARCHAR(120) NULL,
  observacao TEXT NULL,
  resumo TEXT NOT NULL,
  proximos_passos TEXT NULL,
  origem_resumo VARCHAR(10) NOT NULL,
  dados JSON NOT NULL,
  gerado_em DATETIME NOT NULL,
  INDEX idx_relatorios_gerado (gerado_em),
  CONSTRAINT fk_rel_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
