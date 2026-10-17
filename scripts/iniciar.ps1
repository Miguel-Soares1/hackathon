# Sobe tudo para a demo local: MySQL (docker compose) + API e painel em http://localhost:8000.
# Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
# Para parar: Ctrl+C (API) e depois "docker compose stop" (banco).
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if (-not (Test-Path ".env")) { throw "Falta o .env. Copie o .env.example para .env e preencha API_KEY." }
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Falta o venv. Rode: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt" }

docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "O Docker Desktop não está aberto. Abra-o, espere ficar 'running' e rode de novo." }

Write-Host "Subindo o MySQL e esperando ficar pronto..."
docker compose up -d --wait
if ($LASTEXITCODE -ne 0) { throw "O MySQL não subiu. Veja: docker compose logs db" }

Write-Host "Atualizando o banco (migrações que faltarem)..."
& $python scripts\criar_banco.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao atualizar o banco. Veja a mensagem acima." }

Write-Host "Painel: http://localhost:8000 (entre com a API_KEY do .env). Ctrl+C para parar."
Start-Job { Start-Sleep 8; Start-Process "http://localhost:8000" } | Out-Null
& $python -m uvicorn triagem.api:app --app-dir src --port 8000
