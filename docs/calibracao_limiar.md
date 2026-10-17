# Calibração do limiar de incidentes

Critério de aceitação da Spec 2: o limiar padrão foi calibrado com o conjunto de demo rotulado (`data/mensagens_demo.json`, 34 mensagens).

- **Modelo:** `paraphrase-multilingual-MiniLM-L12-v2` (ADR-008). Calibrado com a versão PyTorch e **recalibrado com a versão ONNX int8 usada em produção (ADR-011): mesma tabela, mesmo limiar.**
- **Regra de incidente:** 3 ou mais mensagens no mesmo grupo em 30 minutos
- **Incidentes esperados no conjunto:** `pix_fora` (5 mensagens) e `login_bloqueado` (5 mensagens). `cobranca_dupla` tem só 2 mensagens e **não** deve virar incidente.
- **Como reproduzir:** `python scripts/calibrar_limiar.py`

## Resultado da simulação ponta a ponta

O script reproduz o algoritmo real (centroide + janela), em ordem de chegada.

| Limiar | Incidentes certos | Falsos incidentes | Grupos que viraram incidente (rótulo: acertos/tamanho) |
|---|---|---|---|
| 0,40 | 2/2 | 1 | sem rótulo 8/10, login 5/6, pix 5/5 |
| 0,45–0,50 | 2/2 | 1 | cobranca_dupla 2/3, login 5/6, pix 5/5 |
| 0,55 | 2/2 | 0 | login 5/6, pix 4/4 |
| **0,60** | **2/2** | **0** | **login 5/5, pix 4/4** |
| 0,65 | 2/2 | 0 | login 5/5, pix 4/4 |
| 0,70 (valor inicial) | 2/2 | 0 | login 4/4, pix 3/3 (no limite) |
| 0,75 | 0/2 | 0 | nenhum |

## Decisão

O limiar passa de **0,70 para 0,60**. É o ponto no meio da faixa segura (0,55 a 0,65): detecta os dois incidentes, não abre nenhum falso e mantém os grupos quase completos.

Com 0,70, a detecção acontecia por pouco: o incidente do Pix ficava com só 3 mensagens, exatamente o mínimo, e qualquer variação de texto na demo poderia fazê-lo sumir. Já com 0,75 nenhum incidente é detectado.

Análise por pares, que é mais pessimista porque não usa o centroide: os pares do mesmo problema têm similaridade média de 0,62 e os pares de problemas diferentes, 0,20 (p95 = 0,46).

## Robustez à ordem de processamento

Na API, as tarefas em background classificam e agrupam os tickets **fora da ordem de chegada**. Por isso o grupo formado depende de qual mensagem chega primeiro ao agrupador. Na execução real com o DeepSeek, por exemplo, o incidente do Pix abriu com 3 das 5 mensagens.

Para medir esse efeito, o agrupamento foi simulado em 200 ordens aleatórias:

| Limiar | Rodadas com os 2 incidentes | Falsos incidentes por rodada | Tamanho médio (pix / login) |
|---|---|---|---|
| 0,50 | 100% | 0,34 | 4,5 / 4,7 |
| 0,55 | 100% | 0,00 | 4,1 / 4,7 |
| **0,60** | **100%** | **0,00** | **3,6 / 4,4** |
| 0,65 | 100% | 0,00 | 3,5 / 3,9 |

Com 0,60, a detecção não depende da ordem e há folga em relação à faixa que gera falsos incidentes (até 0,525). Só o tamanho do grupo varia entre as execuções.

Valor gravado em `app_config.similarity_threshold` e como padrão em `db/schema.sql`.
