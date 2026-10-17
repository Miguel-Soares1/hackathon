-- Atendimento encerrado ou cancelado (cartões do Dashboard). Rode uma vez (depois da 007):
--   mysql -u root -p hackathon < db/migrations/008_desfecho.sql
ALTER TABLE tickets ADD COLUMN desfecho VARCHAR(12) NULL AFTER first_response_at;
ALTER TABLE tickets ADD COLUMN encerrado_em DATETIME NULL AFTER desfecho;
CREATE OR REPLACE VIEW vw_tickets AS
SELECT
  t.id AS ticket_id, t.canal, t.cliente, t.texto, t.status, t.received_at, t.first_response_at,
  t.desfecho, t.encerrado_em,
  cl.origem, cl.prompt_version, cl.exemplos, cl.idioma,
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
