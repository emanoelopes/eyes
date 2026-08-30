$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python Launcher (py) não encontrado. Instale Python 3.11+ primeiro."
}

if (-not (Test-Path .venv)) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
}

Write-Host "Dependências instaladas."
Write-Host "Agora configure .env e coloque credentials\client_secret.json."
