# Roteiro da apresentação para a banca (5 minutos)

Uma ideia só: **a IA tira a triagem das mãos do atendente. Ela classifica, prioriza e detecta incidentes sozinha.**
Tudo o que aparece na tela serve a essa frase. O roteiro operacional completo (comandos, plano B, perguntas da
banca) está em [`roteiro_demo.md`](roteiro_demo.md).

## Preparação (15 min antes)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1 -Celular   # banco, API e painel; QR codes em /demo/celular
python scripts/resetar_demo.py --sim                                     # outro terminal: zera a demo
python scripts/simular.py                                                # a fila "do dia" (34 mensagens)
```

- [ ] Painel na **Central de Triagem**, com zoom do navegador em 110–125% para o projetor
- [ ] Celular com o WhatsApp de demonstração aberto (QR code em `/demo/celular`), na mesma rede Wi-Fi
- [ ] Terminal com a rajada **digitada, sem Enter**:
      `python scripts/simular.py --arquivo data/rajada_demo.json --tempo-real --intervalo 2`
- [ ] `DEEPSEEK_API_KEY` no `.env` (sem ela tudo funciona, mas o selo das mensagens vira **plano B** e o resumo vira "automático")
- [ ] Notificações do Windows desligadas

---

## 0:00–0:45 · O problema

> "Hoje as mensagens de clientes chegam por WhatsApp, e-mail, chat e Instagram e caem numa fila só, na ordem de
> chegada. O lojista que **parou de receber Pix e está perdendo vendas** espera atrás de quem quer a segunda via do
> boleto. Alguém precisa ler mensagem por mensagem, decidir o que é urgente e para qual equipe vai. E quando vinte
> clientes reclamam da mesma falha, cada atendente vê só o seu cliente: ninguém percebe que é um incidente."

Três dores: **urgente misturado com dúvida simples**, **triagem manual e lenta**, **incidente invisível**.

## 0:45–1:00 · A solução em uma frase

> "O NEXUS lê cada mensagem no momento em que ela chega, define assunto, urgência, sentimento e equipe, coloca o
> caso no lugar certo da fila e percebe sozinho quando vários clientes falam do mesmo problema."

Mostrar a **Central de Triagem** parada por 5 segundos: o **Resumo da IA** no topo já diz o que importa agora.

## 1:00–3:30 · Demo ao vivo

| Tempo | O que fazer | O que falar |
|---|---|---|
| 1:00 | Apontar os **4 números** do topo | "Quantas a IA triou hoje e em quantos segundos cada uma; quantos urgentes estão na frente; quantos incidentes ela detectou; e quanto ela acerta." |
| 1:20 | No **celular**, mandar pelo WhatsApp: *"O Pix parou de cair aqui na loja, estou perdendo venda agora!"* | "Eu sou o cliente. Do lado dele é só o WhatsApp de sempre." |
| 1:35 | Na **Fila priorizada pela IA**, a mensagem aparece em segundos **no topo**, com selo *crítica* e *classificado pela IA* | "Ninguém tocou nessa mensagem. A IA leu, classificou como crítica, mandou para o financeiro e ela passou na frente de todo mundo." |
| 1:50 | Abrir **Por que essa prioridade?** no item | "E ela explica a decisão: cliente perdendo vendas agora, negócio parado. O atendente não precisa confiar às cegas." |
| 2:05 | Clicar no item: abre o **Atendimento** com a conversa, a triagem e a **resposta sugerida**; responder com um clique | "O atendente já começa com a equipe certa e uma resposta pronta, no idioma do cliente." |
| 2:30 | **Momento principal.** Voltar à Central e dar Enter na **rajada** no terminal | "Agora vários clientes, por canais diferentes, vão escrever do mesmo problema, cada um com palavras diferentes." |
| 2:50 | Em segundos aparece o bloco vermelho **Incidente em andamento**, com nome e resumo escritos pela IA | "Sem palavra-chave: a IA entendeu que é o **mesmo problema**, abriu o incidente, deu nome a ele e resumiu o impacto. Antes de virar crise, e não depois." |
| 3:10 | Clicar em **Ver as mensagens** (página Incidentes) | "Aqui estão as mensagens agrupadas e a evidência: quantas, em quanto tempo, quão parecidas." |

## 3:30–4:15 · Os números

Mostrar o cartão **Precisão da IA** e falar dos números medidos com `scripts/avaliar_triagem.py`
(ver [`avaliacao_triagem.md`](avaliacao_triagem.md)):

- **89% de acerto** na triagem em mensagens rotuladas (assunto 94%, sentimento 91%, urgência 82%)
- **100% de respostas válidas** do LLM e **3 de 3** tentativas de prompt injection classificadas corretamente
- **Plano B:** se a IA externa cair, regras assumem (80% de acerto) e **nenhuma mensagem se perde**; o selo muda para *plano B*
- **Incidentes:** limiar calibrado; 2 de 2 incidentes reais detectados, **zero falsos alarmes** em 200 simulações

> Antes da banca, rode `python scripts/avaliar_triagem.py` de novo: o prompt mudou para `v4` (agora a IA também
> escreve a justificativa da urgência) e os números acima foram medidos na `v3`.

## 4:15–4:50 · A IA aprende com as correções

Na fila, abrir um ticket e **corrigir a urgência** (Atendimento → Triagem da IA → Corrigir triagem).

> "A IA pode errar. O atendente corrige com um clique, e essa correção vira exemplo: a próxima mensagem parecida já
> chega com o critério que o time ensinou. Não é fine-tuning: o sistema busca os casos já revisados mais parecidos
> e mostra à IA antes de ela decidir. Cada correção também entra na taxa de acerto, separada por versão do prompt,
> então a gente mede se a IA está melhorando de verdade."

Se der tempo, mandar pelo celular uma mensagem parecida com a corrigida e mostrar a linha 🧠 no ticket novo.

## 4:50–5:00 · Fechamento

> "Urgente sai da fila em minutos, incidente é visto antes de virar crise e a qualidade da triagem é medida todo
> dia. A triagem deixou de ser trabalho do atendente."

---

## Se algo der errado

| Situação | O que fazer |
|---|---|
| Sem internet ou DeepSeek fora | Seguir: selo *plano B*, resumo *automático*, incidente nomeado pelo assunto. Falar: "a IA externa caiu e o sistema continuou triando." |
| A rajada não abriu incidente | Rodar a rajada de novo ou mostrar os incidentes já existentes na página Incidentes |
| Celular não conecta | Usar `/demo` numa segunda janela do navegador, lado a lado com o painel |
| Recomeçar do zero | `python scripts/resetar_demo.py --sim` e `python scripts/simular.py` |
