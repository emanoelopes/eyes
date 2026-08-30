$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) { throw "Execute scripts\setup.ps1 primeiro." }
if (-not (Test-Path .env)) { throw "Arquivo .env não existe." }
if (-not (Test-Path credentials\client_secret.json)) { throw "Falta credentials\client_secret.json." }

& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
