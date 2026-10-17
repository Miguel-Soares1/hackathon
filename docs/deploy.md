# Publicação gratuita (Render + Aiven)

O sistema é **um único serviço**: a API FastAPI serve também o painel (`frontend/`, ADR-010). O banco fica num MySQL gratuito na nuvem.

| Peça | Onde | Plano grátis |
|---|---|---|
| API + painel (imagem Docker) | [Render](https://render.com) | 512 MB de RAM; dorme após ~15 min sem acesso |
| MySQL 8 | [Aiven](https://aiven.io/free-tier) | 1 CPU, 1 GB de RAM e 1 GB de disco, sem cartão |
| LLM | DeepSeek | pago por uso (frações de centavo por mensagem) |

**Memória medida** num container limitado a 512 MB, processando as 34 mensagens de demo mais a rajada com o LLM real: pico de **365 MB**, sem estouro (ADR-011). Em repouso, ~65 MB.

## 1. Banco no Aiven (5 min)

1. Crie uma conta em https://console.aiven.io e um serviço **MySQL** no plano **Free**.
2. Quando o serviço estiver *Running*, copie da aba **Overview**: `Host`, `Port`, `User` (`avnadmin`), `Password` e `Database name` (`defaultdb`).
3. Baixe o **CA certificate** (botão na mesma tela).
4. Monte a URL de conexão:
   ```
   mysql+pymysql://avnadmin:SENHA@HOST:PORTA/defaultdb
   ```
5. Crie as tabelas **a partir do seu computador** (na raiz do repositório, com o venv ativo):
   ```powershell
   $env:DATABASE_URL="mysql+pymysql://avnadmin:SENHA@HOST:PORTA/defaultdb"
   $env:MYSQL_SSL_CA="C:\caminho\para\ca.pem"
   python scripts/criar_banco.py
   ```
   A saída deve listar as 9 tabelas e a view `vw_tickets`.

## 2. API + painel no Render (10 min)

1. Crie uma conta em https://render.com (pode entrar com o GitHub).
2. **New → Blueprint** e aponte para o repositório. O Render lê o `render.yaml`.
   Sem acesso ao repositório? Use **New → Web Service → Public Git Repository** com a URL do GitHub, *Language: Docker* e *Instance type: Free*.
3. Preencha as variáveis de ambiente:

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | a URL do passo 1.4 |
   | `MYSQL_SSL_CA` | o **conteúdo** do `ca.pem` (cole o texto inteiro, de `-----BEGIN CERTIFICATE-----` até `-----END CERTIFICATE-----`) |
   | `DEEPSEEK_API_KEY` | a chave do DeepSeek (sem ela, o sistema usa o plano B por regras) |
   | `API_KEY` | gerada pelo Render; é a senha para entrar no painel |

4. Aguarde o build (~5 min na primeira vez). Teste `https://SEU-APP.onrender.com/health`, que deve retornar `{"status":"ok"}`.
5. Abra `https://SEU-APP.onrender.com`, entre com a `API_KEY` e carregue a demo **do seu computador**:
   ```powershell
   python scripts/simular.py --url https://SEU-APP.onrender.com
   ```
   (o `API_KEY` do seu `.env` precisa ser igual ao do Render para o simulador funcionar)

## Antes da apresentação

- O plano grátis do Render **dorme após ~15 min sem acesso**, e o primeiro acesso depois disso leva cerca de 1 min. **Abra o painel uns 5 minutos antes.**
- Zere e recarregue a demo apontando para o banco da nuvem: `DATABASE_URL` + `MYSQL_SSL_CA` no ambiente, depois `python scripts/resetar_demo.py --sim` e `python scripts/simular.py --url https://SEU-APP.onrender.com`.
- A rajada ao vivo também pode ser enviada pelo navegador: aba **✉️ Nova mensagem** do painel.

## Rodar a imagem localmente (opcional)

```powershell
docker build -t triagem-ia .
docker run --rm -p 8001:8000 --memory=512m --network hackathon-novo_default `
  -e DATABASE_URL=mysql+pymysql://hackathon:hackathon@hackathon-mysql:3306/hackathon `
  -e API_KEY=sua-chave triagem-ia
```
