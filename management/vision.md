# Vision

Documento de visão do produto. Organizado em blocos de versão (V1, V2, ...). Cada bloco descreve o que uma versão entrega, o problema que resolve e quais specs a implementam.

---

## V1: Plataforma de Triagem, Detecção de Incidentes e Monitoramento com IA

O produto classifica automaticamente cada solicitação de cliente por **assunto**, **urgência** e **sentimento**; agrupa mensagens semelhantes para alertar possíveis incidentes; registra as correções feitas pelo atendente para medir a taxa de acerto da triagem; e reúne em um painel os principais motivos de contato, os incidentes detectados, os prazos de resposta em risco e a precisão de triagem.

**Problema resolvido:** a triagem manual de solicitações é lenta, inconsistente e sem visibilidade sobre incidentes, prazos de resposta e qualidade da própria triagem.

**Entregue por:** Spec 1 (Classificação), Spec 2 (Agrupamento/Incidentes), Spec 3 (Correções/Taxa de Acerto), Spec 5 (Prazos de Resposta) e Spec 4 (Painel).

**Status:** entregue.

---

## V2: Demanda real e IA que aprende com o atendente

O produto passa a receber mensagens de **canais reais** (WhatsApp, e-mail e um formulário web público com limite de uso),
pode ser **colocado no ar** em um servidor com HTTPS, e a triagem **melhora com o uso**: cada ticket revisado pelo
atendente vira exemplo para as próximas mensagens parecidas, e a melhora é medida por versão do prompt e num conjunto de
avaliação separado. Clientes que escrevem em outros idiomas são identificados e recebem a resposta sugerida no
mesmo idioma.

**Problema resolvido:** na V1 a demanda era simulada, o sistema só rodava em uma máquina e as correções do atendente
apenas mediam a qualidade, sem melhorar a IA; e toda resposta saía em português.

**Entregue por:** Spec 6 (Aprendizado com correções), Spec 7 (Canais reais e entrada pública), Spec 8 (Deploy em produção) e Spec 9 (Idiomas).

**Status:** entregue; pendentes a linha de base `v3` × `v3+fewshot` com a chave real e o deploy em um servidor (ver `docs/release_checklist_final.md`).
