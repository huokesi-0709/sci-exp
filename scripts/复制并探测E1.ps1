param(
    [Parameter(Mandatory = $true)]
    [string]$E1Host,
    [string]$User = "radxa",
    [int]$Port = 22
)

$ErrorActionPreference = "Stop"
$LocalRoot = "D:\projects\RAG-sci\docs\sci-exp"
$Remote = "${User}@${E1Host}"
$RemoteRoot = "/home/radxa/sci-exp"

if (-not (Test-Path -LiteralPath $LocalRoot -PathType Container)) {
    throw "Local directory is missing: $LocalRoot"
}

$Model = Join-Path $LocalRoot "models\qwen1_5-0_5b-chat-q4_k_m.gguf"
if (-not (Test-Path -LiteralPath $Model -PathType Leaf)) {
    throw "Candidate GGUF is missing: $Model"
}

Write-Host "1/4 Check E1 identity and target directory"
ssh -p $Port -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 `
    $Remote "test -d /home/radxa && printf 'host=' && hostname && printf 'arch=' && uname -m && test ! -e '$RemoteRoot'"
if ($LASTEXITCODE -ne 0) {
    throw "Cannot verify E1, or the target directory already exists. Copy stopped to avoid overwrite."
}

Write-Host "2/4 Copy the complete sci-exp directory to E1"
scp -P $Port -r $LocalRoot "${Remote}:/home/radxa/"
if ($LASTEXITCODE -ne 0) {
    throw "Copy failed."
}

Write-Host "3/4 Run device and power-path probes"
ssh -p $Port $Remote `
    "cd '$RemoteRoot' && chmod +x scripts/*.sh && python3 scripts/探测E1设备与功率路径.py --output results/E1设备与功率路径探测_v1.0.json && bash scripts/detect_power_paths.sh > results/E1功率路径原始探测_v1.0.txt"
if ($LASTEXITCODE -ne 0) {
    throw "E1 probe failed."
}

Write-Host "4/4 Copy probe results back to Windows"
scp -P $Port "${Remote}:${RemoteRoot}/results/E1设备与功率路径探测_v1.0.json" `
    (Join-Path $LocalRoot "data\logs\E1设备与功率路径探测_v1.0.json")
scp -P $Port "${Remote}:${RemoteRoot}/results/E1功率路径原始探测_v1.0.txt" `
    (Join-Path $LocalRoot "data\logs\E1功率路径原始探测_v1.0.txt")

Write-Host "Copy and probe completed. Inspect the returned JSON before locking the runtime."
