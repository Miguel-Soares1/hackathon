-- Esquema do banco (MySQL 8 / compatível com MariaDB). Idempotente: pode rodar mais de uma vez.
-- Datas em UTC.

CREATE TABLE IF NOT EXISTS tickets (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  canal VARCHAR(30) NOT NULL,
  cliente VARCHAR(120) NULL,
  texto TEXT NOT NULL,
  external_id VARCHAR(190) NULL,
  conversa_id VARCHAR(190) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pendente',
  received_at DATETIME NOT NULL,
  first_response_at DATETIME NULL,
  desfecho VARCHAR(12) NULL,
  encerrado_em DATETIME NULL,
  encerrado_por VARCHAR(120) NULL,
  sugestao_contexto TEXT NULL,
  sugestao_em DATETIME NULL,
  sugestao_mensagem_id BIGINT UNSIGNED NULL,
  modo VARCHAR(10) NULL,
  escalado_em DATETIME NULL,
  motivo_escalada VARCHAR(160) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tickets_received (received_at),
  INDEX idx_tickets_status (status),
  UNIQUE KEY uq_tickets_canal_externo (canal, external_id),
  INDEX idx_tickets_conversa (canal, conversa_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Conversa (chat do atendimento): mensagens do cliente (entrada) e respostas do atendente (saida).
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

CREATE TABLE IF NOT EXISTS classifications (
  ticket_id BIGINT UNSIGNED PRIMARY KEY,
  assunto VARCHAR(30) NOT NULL,
  urgencia VARCHAR(10) NOT NULL,
  sentimento VARCHAR(10) NOT NULL,
  equipe VARCHAR(30) NOT NULL,
  resposta_sugerida TEXT NOT NULL,
  -- Idioma do cliente (ISO 639-1); a resposta sugerida sai no mesmo idioma (ADR-015).
  idioma VARCHAR(5) NOT NULL DEFAULT 'pt',
  conf_assunto DECIMAL(4,3) NOT NULL,
  conf_urgencia DECIMAL(4,3) NOT NULL,
  conf_sentimento DECIMAL(4,3) NOT NULL,
  conf_equipe DECIMAL(4,3) NOT NULL,
  origem VARCHAR(10) NOT NULL,
  -- Versão do prompt (ex.: 'v2', 'v2+fewshot', 'regras') e ids dos tickets revisados usados como exemplo.
  prompt_version VARCHAR(30) NOT NULL DEFAULT 'v1',
  exemplos VARCHAR(255) NULL,
  -- "Por que essa prioridade?": frase da IA (ou do plano B) sobre o impacto que definiu a urgência.
  justificativa VARCHAR(300) NULL,
  classified_at DATETIME NOT NULL,
  CONSTRAINT fk_class_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Áudios e fotos enviados pelo cliente (ADR-015). A IA de mídia grava em `conteudo` a transcrição ou a descrição.
CREATE TABLE IF NOT EXISTS ticket_midias (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ticket_id BIGINT UNSIGNED NOT NULL,
  -- Mensagem do chat que levou a mídia (resposta do atendente); NULL = mídia do cliente, lida pela IA.
  mensagem_id BIGINT UNSIGNED NULL,
  tipo VARCHAR(10) NOT NULL,
  mime VARCHAR(60) NOT NULL,
  tamanho INT UNSIGNED NOT NULL,
  dados MEDIUMBLOB NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'pendente',
  conteudo TEXT NULL,
  processed_at DATETIME NULL,
  INDEX idx_midias_ticket (ticket_id),
  INDEX idx_midias_mensagem (mensagem_id),
  CONSTRAINT fk_midia_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
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
  -- Nome e resumo do incidente escritos pela IA a partir das mensagens agrupadas (NULL = sem o LLM).
  titulo_ia VARCHAR(120) NULL,
  resumo_ia TEXT NULL,
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

-- Relatório final do atendimento, gerado quando o atendente encerra a conversa.
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
  ('slo_janela_dias', '7'),
  -- Atendimento pela IA (ADR-019): urgência baixa e média; vai para um atendente se passar destes limites.
  ('ia_auto_ativo', '1'),
  ('ia_max_minutos', '15'),
  ('ia_max_respostas', '5');

-- Visão com os valores efetivos (predição da IA ou última correção do atendente).
-- Usuários do painel e sessões de login (ADR-018). Senha só como hash PBKDF2; sessão só como hash do token.
CREATE TABLE IF NOT EXISTS usuarios (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  usuario VARCHAR(60) NOT NULL,
  nome VARCHAR(120) NOT NULL,
  senha_hash VARCHAR(200) NOT NULL,
  papel VARCHAR(20) NOT NULL DEFAULT 'atendente',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
  de_plantao TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  ultimo_login DATETIME NULL,
  UNIQUE KEY uq_usuarios_usuario (usuario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessoes (
  token_hash CHAR(64) PRIMARY KEY,
  usuario_id INT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL,
  expira_em DATETIME NOT NULL,
  INDEX idx_sessoes_usuario (usuario_id),
  INDEX idx_sessoes_expira (expira_em),
  CONSTRAINT fk_sessao_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CREATE OR REPLACE VIEW vw_tickets AS
SELECT
  t.id AS ticket_id, t.canal, t.cliente, t.texto, t.status, t.received_at, t.first_response_at,
  t.desfecho, t.encerrado_em, t.encerrado_por, t.modo, t.escalado_em, t.motivo_escalada,
  cl.origem, cl.prompt_version, cl.exemplos, cl.idioma, cl.justificativa, cl.classified_at,
  cl.assunto AS assunto_original, cl.urgencia AS urgencia_original,
  cl.sentimento AS sentimento_original, cl.equipe AS equipe_original,
  cl.resposta_sugerida AS resposta_original,
  cl.conf_assunto, cl.conf_urgencia, cl.conf_sentimento, cl.conf_equipe,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'assunto' ORDER BY c.id DESC LIMIT 1), cl.assunto) AS assunto,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'urgencia' ORDER BY c.id DESC LIMIT 1), cl.urgencia) AS urgencia,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'sentimento' ORDER BY c.id DESC LIMIT 1), cl.sentimento) AS sentimento,
  COALESCE((SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'equipe' ORDER BY c.id DESC LIMIT 1), cl.equipe) AS equipe,
  -- Resposta sugerida: a da última mensagem do cliente (ADR-016) ou, se não houver, a correção do atendente ou a da triagem.
  -- Uma correção da resposta apaga a sugestão atualizada; a próxima mensagem do cliente gera outra.
  COALESCE(t.sugestao_contexto,
    (SELECT c.valor_corrigido FROM corrections c WHERE c.ticket_id = t.id AND c.dimensao = 'resposta_sugerida' ORDER BY c.id DESC LIMIT 1),
    cl.resposta_sugerida) AS resposta_sugerida,
  (t.sugestao_contexto IS NOT NULL) AS sugestao_atualizada,
  t.sugestao_mensagem_id,
  (rv.ticket_id IS NOT NULL) AS revisado
FROM tickets t
LEFT JOIN classifications cl ON cl.ticket_id = t.id
LEFT JOIN reviews rv ON rv.ticket_id = t.id;
