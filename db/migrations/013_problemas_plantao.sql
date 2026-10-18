-- Bancos criados antes do relatório de problemas e do plantão (ADR-020).
-- Rode uma vez (ou deixe o python scripts/criar_banco.py aplicar sozinho).
ALTER TABLE usuarios ADD COLUMN de_plantao TINYINT(1) NOT NULL DEFAULT 1 AFTER ativo;

-- Relatório de problemas (ADR-020): o atendente registra um problema e cada vez que ele acontece (cliente afetado).
CREATE TABLE IF NOT EXISTS problemas (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  titulo VARCHAR(160) NOT NULL,
  caracteristicas TEXT NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'aberto',
  criado_por VARCHAR(120) NULL,
  created_at DATETIME NOT NULL,
  resolvido_em DATETIME NULL,
  INDEX idx_problemas_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS problema_ocorrencias (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  problema_id BIGINT UNSIGNED NOT NULL,
  cliente_id VARCHAR(190) NOT NULL,
  ticket_id BIGINT UNSIGNED NULL,
  observacao VARCHAR(500) NULL,
  registrado_por VARCHAR(120) NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_ocorr_problema (problema_id, id),
  CONSTRAINT fk_ocorr_problema FOREIGN KEY (problema_id) REFERENCES problemas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
