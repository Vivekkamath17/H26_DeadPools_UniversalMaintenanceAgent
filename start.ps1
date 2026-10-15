#!/usr/bin/env pwsh
# start.ps1 — Starts both FastAPI backend and Vite frontend concurrently

Write-Host "🚀 Starting Universal Maintenance Agent Platform..." -ForegroundColor Cyan

# Start FastAPI backend
$backend = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "main:app", "--reload", "--port", "8000" `
  -WorkingDirectory "$PSScriptRoot\backend" -PassThru -WindowStyle Normal

Write-Host "  ✓ Backend  → http://localhost:8000  (PID $($backend.Id))" -ForegroundColor Green

# Give backend 2s to start
Start-Sleep -Seconds 2

# Start Vite frontend
$frontend = Start-Process -FilePath "npm" -ArgumentList "run", "dev" `
  -WorkingDirectory "$PSScriptRoot\frontend" -PassThru -WindowStyle Normal

Write-Host "  ✓ Frontend → http://localhost:5173  (PID $($frontend.Id))" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C or close these windows to stop." -ForegroundColor Gray

# Open browser
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"
