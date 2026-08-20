param(
    [string]$UploadPort = "",
    [switch]$BuildOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FirmwareRoot = Join-Path $ProjectRoot "hardware\esp32s3_ina226_power_meter"
$LogRoot = Join-Path $ProjectRoot "data\logs"
$Pio = Get-Command pio -ErrorAction SilentlyContinue

if (-not $Pio) {
    throw "未找到PlatformIO命令pio；请先安装PlatformIO Core。"
}

Push-Location $FirmwareRoot
try {
    & $Pio.Source run
    if ($LASTEXITCODE -ne 0) {
        throw "PlatformIO编译失败，退出码：$LASTEXITCODE"
    }
    $Binary = Join-Path $FirmwareRoot ".pio\build\esp32-s3-n16r8\firmware.bin"
    if (-not (Test-Path -LiteralPath $Binary -PathType Leaf)) {
        throw "编译成功但未找到firmware.bin：$Binary"
    }
    if (-not $BuildOnly) {
        if ([string]::IsNullOrWhiteSpace($UploadPort)) {
            throw "烧录需要提供-UploadPort COM号；只编译请使用-BuildOnly。"
        }
        & $Pio.Source run --target upload --upload-port $UploadPort
        if ($LASTEXITCODE -ne 0) {
            throw "PlatformIO烧录失败，退出码：$LASTEXITCODE"
        }
    }
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    $Record = [ordered]@{
        schema_version = "esp32s3-ina226-build-v1.0"
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        environment = "esp32-s3-n16r8"
        upload_port = if ($BuildOnly) { $null } else { $UploadPort }
        build_only = [bool]$BuildOnly
        firmware_path = $Binary.Substring($ProjectRoot.Length + 1).Replace("\", "/")
        firmware_size_bytes = (Get-Item -LiteralPath $Binary).Length
        firmware_sha256 = (Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash.ToLower()
        platformio = (& $Pio.Source --version | Out-String).Trim()
        wiring_photo_confirmed = $false
        hardware_calibrated = $false
    }
    $LogPath = Join-Path $LogRoot "ESP32S3_INA226固件构建_v1.0.json"
    $Record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $LogPath -Encoding utf8
    $Record | ConvertTo-Json -Depth 5
}
finally {
    Pop-Location
}
