-- Bancos criados antes da Central de Triagem: justificativa da urgência e nome/resumo do incidente pela IA.
-- Rode uma vez (ou deixe o python scripts/criar_banco.py aplicar sozinho, que também recria a visão vw_tickets).
ALTER TABLE classifications ADD COLUMN justificativa VARCHAR(300) NULL AFTER exemplos;
ALTER TABLE incident_groups ADD COLUMN titulo_ia VARCHAR(120) NULL AFTER assunto_predominante;
ALTER TABLE incident_groups ADD COLUMN resumo_ia TEXT NULL AFTER titulo_ia;
