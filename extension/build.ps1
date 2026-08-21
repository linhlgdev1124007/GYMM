$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Stop-AgentProcesses {
  Write-Host "--- Đang dừng Agent/Uninstaller cũ nếu còn chạy ---"
  $currentPid = $PID
  $processes = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $currentPid -and (
      $_.Name -in @("PulseFitDahAgent.exe", "uninstall.exe") -or
      ($_.CommandLine -and (
        $_.CommandLine -like "*dah_agent.py*" -or
        $_.CommandLine -like "*uninstall.py*" -or
        $_.CommandLine -like "*PulseFitDahAgent.exe*"
      ))
    )
  }

  foreach ($process in $processes) {
    try {
      Write-Host "Dừng process $($process.Name) PID=$($process.ProcessId)"
      Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    } catch {
      Write-Warning "Không dừng được PID=$($process.ProcessId): $($_.Exception.Message)"
    }
  }

  foreach ($process in $processes) {
    try {
      Wait-Process -Id $process.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
    } catch {
      # Process đã thoát.
    }
  }
}

function Remove-DirectoryForBuild {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [switch]$RenameIfLocked
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  for ($attempt = 1; $attempt -le 5; $attempt += 1) {
    try {
      Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
      return
    } catch {
      if ($attempt -eq 5) {
        break
      }
      Write-Warning "Chưa xóa được $Path, thử lại lần $($attempt + 1)/5: $($_.Exception.Message)"
      Start-Sleep -Seconds 2
    }
  }

  if ($RenameIfLocked) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $fallback = "$Path.old-$stamp"
    try {
      Move-Item -LiteralPath $Path -Destination $fallback -Force -ErrorAction Stop
      Write-Warning "Không xóa được $Path vì còn bị khóa. Đã đổi tên sang $fallback để tiếp tục build."
      return
    } catch {
      throw "Không thể xóa hoặc đổi tên $Path. Hãy đóng Agent, Explorer đang mở thư mục app, hoặc tạm dừng antivirus rồi chạy lại. Lỗi: $($_.Exception.Message)"
    }
  }

  throw "Không thể xóa $Path. Lỗi: thư mục hoặc file đang bị process khác giữ."
}

Stop-AgentProcesses

python -m pip install -r requirements.txt

$PythonRoot = Split-Path -Parent (Get-Command python).Source
$env:TCL_LIBRARY = Join-Path $PythonRoot "tcl\tcl8.6"
$env:TK_LIBRARY = Join-Path $PythonRoot "tcl\tk8.6"

Remove-DirectoryForBuild -Path ".\build"
Remove-DirectoryForBuild -Path ".\app" -RenameIfLocked

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
