# Sobe tudo para a demo local: MySQL (docker compose) + API e painel em http://localhost:8000.
# Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
# Com -Celular, a API também escuta na rede local, liga o HTTPS do celular (porta 8443, necessário para gravar
# áudio no navegador do celular) e abre /demo/celular com os QR codes (celular na mesma rede Wi-Fi ou no hotspot
# do notebook). Use só em rede confiável: as telas /demo não pedem senha.
# Para parar: Ctrl+C (API) e depois "docker compose stop" (banco).
param([switch]$Celular)
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

$hostApi = "127.0.0.1"
Write-Host "Painel: http://localhost:8000 (entre com a API_KEY do .env). Ctrl+C para parar."
if ($Celular) {
    $hostApi = "0.0.0.0"
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" }
    foreach ($ip in $ips) { Write-Host ("Celular: http://{0}:8000/demo  ({1})" -f $ip.IPAddress, $ip.InterfaceAlias) }
    Write-Host "QR codes em http://localhost:8000/demo/celular. Se o Windows perguntar, permita o Python em redes privadas."
    # HTTPS do celular (8443 -> 8000): o navegador do celular só libera o microfone em página segura.
    $https = Start-Process -FilePath $python -ArgumentList "scripts\https_celular.py" -WorkingDirectory $raiz -PassThru -NoNewWindow
    Start-Job { Start-Sleep 10; Start-Process "http://localhost:8000/demo/celular" } | Out-Null
}
Start-Job { Start-Sleep 8; Start-Process "http://localhost:8000" } | Out-Null
try {
    & $python -m uvicorn triagem.api:app --app-dir src --host $hostApi --port 8000
} finally {
    if ($https -and -not $https.HasExited) { Stop-Process -Id $https.Id -Force -ErrorAction SilentlyContinue }
}
