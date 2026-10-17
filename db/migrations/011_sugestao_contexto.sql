-- Bancos criados antes da resposta sugerida para a última mensagem do cliente: guarda a sugestão atualizada.
-- Rode uma vez (ou deixe o python scripts/criar_banco.py aplicar sozinho, que também recria a visão vw_tickets).
ALTER TABLE tickets ADD COLUMN sugestao_contexto TEXT NULL AFTER encerrado_por;
ALTER TABLE tickets ADD COLUMN sugestao_em DATETIME NULL AFTER sugestao_contexto;
ALTER TABLE tickets ADD COLUMN sugestao_mensagem_id BIGINT UNSIGNED NULL AFTER sugestao_em;
