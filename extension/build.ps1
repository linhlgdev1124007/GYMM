$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m pip install -r requirements.txt

$PythonRoot = Split-Path -Parent (Get-Command python).Source
$env:TCL_LIBRARY = Join-Path $PythonRoot "tcl\tcl8.6"
$env:TK_LIBRARY = Join-Path $PythonRoot "tcl\tk8.6"

if (Test-Path ".\build") {
  Remove-Item -LiteralPath ".\build" -Recurse -Force
}
if (Test-Path ".\app") {
  Remove-Item -LiteralPath ".\app" -Recurse -Force
}

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name PulseFitDahAgent `
  --hidden-import tkinter `
  --hidden-import _tkinter `
  --add-data "$PythonRoot\tcl\tcl8.6;tcl\tcl8.6" `
  --add-data "$PythonRoot\tcl\tk8.6;tcl\tk8.6" `
  --add-binary "$PythonRoot\DLLs\tcl86t.dll;." `
  --add-binary "$PythonRoot\DLLs\tk86t.dll;." `
  --add-binary "$PythonRoot\DLLs\_tkinter.pyd;." `
  --distpath app `
  dah_agent.py

Write-Host "Built: $Root\app\PulseFitDahAgent.exe"
