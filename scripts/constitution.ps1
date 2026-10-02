# Thin entry point: all behavior lives in the portable, tested Python CLI.
$ErrorActionPreference = 'Stop'
$constitutionScript = Join-Path $PSScriptRoot 'constitution.py'
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $constitutionScript @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $constitutionScript @args
} else {
    throw 'Python 3.11+ is required. Install Python, then rerun this command.'
}
exit $LASTEXITCODE
