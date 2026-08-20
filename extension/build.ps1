$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Dừng các tiến trình cũ nếu đang chạy để tránh khóa file exe
python -c "import psutil; [p.kill() for p in psutil.process_iter() if any(k in p.name().lower() for k in ['pulsefit', 'uninstall'])]" 2>$null

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

Write-Host "--- 1/2 Đang build PulseFitDahAgent.exe ---"
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --uac-admin `
  --name PulseFitDahAgent `
  --hidden-import tkinter `
  --hidden-import _tkinter `
  --hidden-import pystray `
  --hidden-import PIL `
  --hidden-import PIL.Image `
  --hidden-import PIL.ImageDraw `
  --add-data "$PythonRoot\tcl\tcl8.6;tcl\tcl8.6" `
  --add-data "$PythonRoot\tcl\tk8.6;tcl\tk8.6" `
  --add-binary "$PythonRoot\DLLs\tcl86t.dll;." `
  --add-binary "$PythonRoot\DLLs\tk86t.dll;." `
  --add-binary "$PythonRoot\DLLs\_tkinter.pyd;." `
  --distpath app `
  dah_agent.py

Write-Host "--- 2/2 Đang build uninstall.exe ---"
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --uac-admin `
  --name uninstall `
  --hidden-import tkinter `
  --hidden-import _tkinter `
  --hidden-import psutil `
  --add-data "$PythonRoot\tcl\tcl8.6;tcl\tcl8.6" `
  --add-data "$PythonRoot\tcl\tk8.6;tcl\tk8.6" `
  --add-binary "$PythonRoot\DLLs\tcl86t.dll;." `
  --add-binary "$PythonRoot\DLLs\tk86t.dll;." `
  --add-binary "$PythonRoot\DLLs\_tkinter.pyd;." `
  --distpath app `
  uninstall.py

Write-Host "Build thành công hoàn tất:"
Write-Host "1. $Root\app\PulseFitDahAgent.exe"
Write-Host "2. $Root\app\uninstall.exe"
