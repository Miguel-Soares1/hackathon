-- Bancos criados antes do atendimento pela IA (ADR-019): modo do atendimento e limites da IA.
-- Rode uma vez (ou deixe o python scripts/criar_banco.py aplicar sozinho, que também recria a visão vw_tickets).
ALTER TABLE tickets ADD COLUMN modo VARCHAR(10) NULL AFTER sugestao_mensagem_id;
ALTER TABLE tickets ADD COLUMN escalado_em DATETIME NULL AFTER modo;
ALTER TABLE tickets ADD COLUMN motivo_escalada VARCHAR(160) NULL AFTER escalado_em;
INSERT IGNORE INTO app_config (chave, valor) VALUES ('ia_auto_ativo', '1'), ('ia_max_minutos', '15'), ('ia_max_respostas', '5');
