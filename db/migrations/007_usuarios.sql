-- Bancos criados antes do login por usuário e senha (ADR-018): cria as tabelas de usuários e sessões.
-- Rode uma vez:  docker exec -i hackathon-mysql mysql -uhackathon -phackathon hackathon < db/migrations/007_usuarios.sql
-- (equivale a rodar o schema de novo: python scripts/criar_banco.py). O 1º administrador é criado na tela de login.
CREATE TABLE IF NOT EXISTS usuarios (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  usuario VARCHAR(60) NOT NULL,
  nome VARCHAR(120) NOT NULL,
  senha_hash VARCHAR(200) NOT NULL,
  papel VARCHAR(20) NOT NULL DEFAULT 'atendente',
  ativo TINYINT(1) NOT NULL DEFAULT 1,
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
