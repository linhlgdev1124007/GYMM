param(
    [int]$Port = 8100
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "PulseFit Studio starting at http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray

& .\.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port $Port
