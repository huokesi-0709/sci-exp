param(
    [Parameter(Mandatory = $true)]
    [string]$OutputArchive
)

$ErrorActionPreference = "Stop"
$Source = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputPath = [System.IO.Path]::GetFullPath($OutputArchive)
$OutputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
}

tar -czf $OutputPath `
    --exclude="./.venv" `
    --exclude="./.pytest_cache" `
    --exclude="*/__pycache__" `
    --exclude="./hardware/esp32s3_ina226_power_meter/.pio" `
    --exclude="./hardware/esp32s3_ina226_power_meter/.vscode" `
    --exclude="./results/*.jsonl" `
    --exclude="./results/*.json" `
    --exclude="./results/*.csv" `
    --exclude="./results/*.txt" `
    -C $Source .

if ($LASTEXITCODE -ne 0) {
    throw "tar打包失败，退出码：$LASTEXITCODE"
}

$Hash = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant()
[pscustomobject]@{
    archive = $OutputPath
    bytes = (Get-Item -LiteralPath $OutputPath).Length
    sha256 = $Hash
    target = "/home/radxa/sci-exp"
} | ConvertTo-Json
