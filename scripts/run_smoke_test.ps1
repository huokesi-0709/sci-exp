$ErrorActionPreference = "Stop"

$ProjectRoot = "D:\projects\RAG-sci\docs\sci-exp"
Set-Location $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

python -m sci_exp.cli smoke --config configs\windows.smoke.json
exit $LASTEXITCODE
