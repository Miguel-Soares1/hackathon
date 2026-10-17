-- Esquema do banco (MySQL 8 / compatível com MariaDB). Idempotente: pode rodar mais de uma vez.
-- Datas em UTC.

CREATE TABLE IF NOT EXISTS tickets (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  canal VARCHAR(30) NOT NULL,
  cliente VARCHAR(120) NULL,
  texto TEXT NOT NULL,
  external_id VARCHAR(190) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pendente',
  received_at DATETIME NOT NULL,
  first_response_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tickets_received (received_at),
  INDEX idx_tickets_status (status),
  UNIQUE KEY uq_tickets_canal_externo (canal, external_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS classifications (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  assunto VARCHAR(30) NOT NULL,
  urgencia VARCHAR(10) NOT NULL,
  sentimento VARCHAR(10) NOT NULL,
  equipe VARCHAR(30) NOT NULL,
  resposta_sugerida TEXT NOT NULL,
  conf_assunto DECIMAL(4,3) NOT NULL,
  conf_urgencia DECIMAL(4,3) NOT NULL,
  conf_sentimento DECIMAL(4,3) NOT NULL,
  conf_equipe DECIMAL(4,3) NOT NULL,
  origem VARCHAR(10) NOT NULL,
  classified_at DATETIME NOT NULL,
  CONSTRAINT fk_class_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Histórico append-only de correções do atendente (valor original = predição da IA).
CREATE TABLE IF NOT EXISTS corrections (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_id BIGINT UNSIGNED NOT NULL,
  dimensao VARCHAR(20) NOT NULL,
  valor_original TEXT NOT NULL,
  valor_corrigido TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_corr_ticket_dim (ticket_id, dimensao),
  CONSTRAINT fk_corr_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Um ticket revisado (confirmado ou corrigido) entra no cálculo da taxa de acerto.
CREATE TABLE IF NOT EXISTS reviews (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  reviewed_at DATETIME NOT NULL,
  CONSTRAINT fk_rev_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ticket_embeddings (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  modelo VARCHAR(120) NOT NULL,
  vetor MEDIUMBLOB NOT NULL,
  CONSTRAINT fk_emb_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS incident_groups (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  centroid MEDIUMBLOB NOT NULL,
  size INT NOT NULL,
  first_at DATETIME NOT NULL,
  last_at DATETIME NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'grupo',
  incident_opened_at DATETIME NULL,
  justificativa TEXT NULL,
  assunto_predominante VARCHAR(30) NULL,
  INDEX idx_groups_last (last_at),
  INDEX idx_groups_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS group_members (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  group_id BIGINT UNSIGNED NOT NULL,
  similarity DECIMAL(5,4) NOT NULL,
  joined_at DATETIME NOT NULL,
  INDEX idx_members_group (group_id),
  CONSTRAINT fk_mem_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
  CONSTRAINT fk_mem_group FOREIGN KEY (group_id) REFERENCES incident_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Política de SLA (ADR-007): prazo da primeira resposta por urgência.
CREATE TABLE IF NOT EXISTS sla_policy (
  urgencia VARCHAR(10) PRIMARY KEY,
  prazo_minutos INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO sla_policy (urgencia, prazo_minutos) VALUES
  ('critica', 15), ('alta', 60), ('media', 240), ('baixa', 1440);

-- Parâmetros configuráveis (Specs 2 e 5, ver docs/slo.md).
CREATE TABLE IF NOT EXISTS app_config (
  chave VARCHAR(60) PRIMARY KEY,
  valor VARCHAR(60) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO app_config (chave, valor) VALUES
  ('sla_risco_pct', '75'),
  ('similarity_threshold', '0.60'),
  ('window_minutes', '30'),
  ('min_group_size', '3'),
  ('slo_alvo_pct', '95'),
  ('slo_janela_dias', '7');

-- Visão com os valores efetivos (predição da IA ou última correção do atendente).
CREATE OR REPLACE VIEW vw_tickets AS
SELECT
  t.id AS ticket_id, t.canal, t.cliente, t.texto, t.status, t.received_at, t.first_response_at,
  cl.origem,
  cl.assunto AS assunto_original, cl.urgencia AS urgencia_original,
  cl.sentimento AS sentimento_original, cl.equipe AS equipe_original,
  cl.resposta_sugerida AS resposta_original,
  cl.conf_assunto, cl.conf_urgencia, cl.conf_sentimento, cl.conf_equipe,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'assunto' ORDER BY c.id DESC LIMIT 1), cl.assunto) AS assunto,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'urgencia' ORDER BY c.id DESC LIMIT 1), cl.urgencia) AS urgencia,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'sentimento' ORDER BY c.id DESC LIMIT 1), cl.sentimento) AS sentimento,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'equipe' ORDER BY c.id DESC LIMIT 1), cl.equipe) AS equipe,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'resposta_sugerida' ORDER BY c.id DESC LIMIT 1), cl.resposta_sugerida) AS resposta_sugerida,
  (rv.ticket_id IS NOT NULL) AS revisado
FROM tickets t
LEFT JOIN classifications cl ON cl.ticket_id = t.id
LEFT JOIN reviews rv ON rv.ticket_id = t.id;
