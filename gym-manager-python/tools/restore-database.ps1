$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "database-common.ps1")

$inputPath = Join-Path $PSScriptRoot "database.sql"
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
    Write-Host "Không tìm thấy $inputPath; bỏ qua khôi phục database." -ForegroundColor Yellow
    exit 0
}

$settings = Get-GymDatabaseSettings
$mysqlTool = Find-MySqlTool "mysql"
$connectionArguments = @(
    "--protocol=TCP",
    "--host=$($settings.Host)",
    "--port=$($settings.Port)",
    "--user=$($settings.User)",
    "--default-character-set=utf8mb4"
)
$sourcePath = $inputPath.Replace('\', '/')

Use-MySqlPassword $settings.Password {
    & $mysqlTool @connectionArguments "--execute=CREATE DATABASE IF NOT EXISTS ``$($settings.Name)`` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if ($LASTEXITCODE -ne 0) { throw "Không thể tạo hoặc truy cập database '$($settings.Name)'." }
    & $mysqlTool @connectionArguments $settings.Name "--execute=source $sourcePath"
    if ($LASTEXITCODE -ne 0) { throw "Khôi phục database thất bại với mã $LASTEXITCODE." }
}

Write-Host "Đã khôi phục database '$($settings.Name)' từ $inputPath" -ForegroundColor Green
