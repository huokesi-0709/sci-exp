param(
    [Parameter(Mandatory = $true)]
    [string]$Queries,
    [int]$Seed = 42,
    [ValidateRange(0, 2)]
    [int]$AugmentTrainCopies = 0,
    [switch]$PreserveExistingSplits
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"
$queryPath = if ([IO.Path]::IsPathRooted($Queries)) {
    $Queries
} else {
    Join-Path $projectRoot $Queries
}

$arguments = @(
    "-m", "sci_exp.cli", "preprocess-queries",
    "--input", $queryPath,
    "--output-directory", (Join-Path $projectRoot "data"),
    "--seed", $Seed,
    "--augment-train-copies", $AugmentTrainCopies,
    "--fail-on-quarantine"
)
if ($PreserveExistingSplits) {
    $arguments += "--preserve-existing-splits"
}

python @arguments

exit $LASTEXITCODE
