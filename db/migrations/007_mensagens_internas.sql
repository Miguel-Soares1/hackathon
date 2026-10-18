-- Mensagens internas (chat da equipe). Rode uma vez (depois da 006):
--   mysql -u root -p hackathon < db/migrations/007_mensagens_internas.sql
-- Mensagens internas (chat da equipe): atendentes e conversas diretas entre eles.
CREATE TABLE IF NOT EXISTS team_members (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nome VARCHAR(60) NOT NULL,
  ultima_atividade DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_team_nome (nome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS internal_messages (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  de_id BIGINT UNSIGNED NOT NULL,
  para_id BIGINT UNSIGNED NOT NULL,
  texto TEXT NULL,
  anexo_nome VARCHAR(160) NULL,
  anexo_tipo VARCHAR(100) NULL,
  anexo_dados MEDIUMBLOB NULL,
  created_at DATETIME NOT NULL,
  lida_em DATETIME NULL,
  INDEX idx_interna_par (de_id, para_id, id),
  INDEX idx_interna_para (para_id, lida_em),
  CONSTRAINT fk_interna_de FOREIGN KEY (de_id) REFERENCES team_members(id) ON DELETE CASCADE,
  CONSTRAINT fk_interna_para FOREIGN KEY (para_id) REFERENCES team_members(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
