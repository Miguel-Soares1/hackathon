# Lições Aprendidas

Padrões que funcionaram, anti-padrões a evitar e gotchas de implementação.

Formato: `L1`, `L2`, ... referenciados pelas specs.

---

## L1: Deadlock entre classificação em background e registro de resposta

Ao gravar a classificação, inserir em `classifications` (FK para `tickets`) antes de atualizar `tickets` fazia as duas
transações pegarem travas em ordem oposta e o MySQL abortava uma com erro 1213. Detectado no teste ponta a ponta com o
simulador. **Regra:** atualizar a linha pai (`tickets`) primeiro e inserir nas filhas depois; operações de escrita
usam `com_retry_deadlock` como rede de segurança.

## L2: O embedder `hash` não serve para validar o agrupamento

O `HashEmbedder` é lexical: não reconhece paráfrases ("Pix fora do ar" vs "o Pix não está passando"). Serve para testes e
para rodar offline, mas o limiar de incidente só pode ser calibrado com o modelo real (`onnx`, ou `sbert`, que dá o mesmo resultado). Use
`scripts/calibrar_limiar.py` com o modelo antes da demo.

## L3: Testes com vetores controlados

Para testar o agrupamento sem depender de modelo, os testes injetam um embedder com vetores pré-definidos.
Isso valida a lógica (limiar, janela, volume mínimo) de forma determinística.

## L4: `pkill -f` com o padrão na própria linha de comando mata o shell

Ao parar o servidor em scripts, use arquivo de PID (`kill $(cat arquivo.pid)`) em vez de `pkill -f <padrão>`.

## L5: `CREATE TABLE IF NOT EXISTS` não adiciona colunas novas

Ao acrescentar `prompt_version` e `exemplos`, o banco de testes antigo continuou com a tabela velha e os testes quebraram
com "Unknown column". **Regra:** o `conftest` recria as tabelas do banco `*_test` a cada sessão, e toda coluna nova ganha
uma migração em `db/migrations/` para os bancos que já existem.

## L6: Avaliar só nas mensagens de demo engana

As regras acertam 80,4% nas 34 mensagens de demo, que foram usadas para escrever as próprias regras, mas só 58,3% em 60
mensagens novas (`data/avaliacao.json`). **Regra:** ajustar prompt e regras olhando o demo e medir no conjunto separado.
