$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "database-common.ps1")

$settings = Get-GymDatabaseSettings
$dumpTool = Find-MySqlTool "mysqldump"
$outputPath = Join-Path $PSScriptRoot "database-backup.sql"
$arguments = @(
    "--protocol=TCP",
    "--host=$($settings.Host)",
    "--port=$($settings.Port)",
    "--user=$($settings.User)",
    "--default-character-set=utf8mb4",
    "--single-transaction",
    "--routines",
    "--triggers",
    "--events",
    "--databases",
    $settings.Name,
    "--result-file=$outputPath"
)

Use-MySqlPassword $settings.Password {
    & $dumpTool @arguments
    if ($LASTEXITCODE -ne 0) { throw "mysqldump thất bại với mã $LASTEXITCODE." }
}

Write-Host "Đã backup database '$($settings.Name)' vào $outputPath" -ForegroundColor Green
