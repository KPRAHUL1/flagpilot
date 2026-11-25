$ErrorActionPreference = "Stop"

Write-Host "Starting FlagPilot Backend (:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot'; .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000"

Write-Host "Starting FlagPilot Mission Control (:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host "Starting Target Demo App (:5174)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PSScriptRoot\demo-app'; npm run dev"

Write-Host "All services launched!" -ForegroundColor Green
Write-Host "Mission Control: http://localhost:5173" -ForegroundColor Yellow
Write-Host "Demo Target App: http://localhost:5174" -ForegroundColor Yellow
