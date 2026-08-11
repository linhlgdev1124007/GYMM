$ErrorActionPreference = "Stop"

function Get-GymDatabaseSettings {
    $port = if ($env:GYM_DB_PORT) { [int]$env:GYM_DB_PORT } else { 3306 }
    $name = if ($env:GYM_DB_NAME) { $env:GYM_DB_NAME } else { "pulsefit_gym" }
    if ($name -notmatch '^[A-Za-z0-9_]+$') {
        throw "GYM_DB_NAME chỉ được chứa chữ, số và dấu gạch dưới."
    }
    [PSCustomObject]@{
        Host = if ($env:GYM_DB_HOST) { $env:GYM_DB_HOST } else { "127.0.0.1" }
        Port = $port
        User = if ($env:GYM_DB_USER) { $env:GYM_DB_USER } else { "root" }
        Password = if ($null -ne $env:GYM_DB_PASSWORD) { $env:GYM_DB_PASSWORD } else { "" }
        Name = $name
    }
}

function Find-MySqlTool([string]$Name) {
    if ($env:GYM_MYSQL_BIN) {
        $candidate = Join-Path $env:GYM_MYSQL_BIN "$Name.exe"
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $commonPaths = @(
        "C:\xampp\mysql\bin\$Name.exe",
        "C:\Program Files\MySQL\MySQL Server 8.4\bin\$Name.exe",
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\$Name.exe"
    )
    foreach ($candidate in $commonPaths) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw "Không tìm thấy $Name. Hãy thêm MySQL bin vào PATH hoặc đặt GYM_MYSQL_BIN."
}

function Use-MySqlPassword([string]$Password, [scriptblock]$Action) {
    $hadPassword = Test-Path Env:MYSQL_PWD
    $previousPassword = $env:MYSQL_PWD
    try {
        if ($Password) { $env:MYSQL_PWD = $Password } else { Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue }
        & $Action
    }
    finally {
        if ($hadPassword) { $env:MYSQL_PWD = $previousPassword } else { Remove-Item Env:MYSQL_PWD -ErrorAction SilentlyContinue }
    }
}
