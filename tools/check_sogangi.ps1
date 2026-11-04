[CmdletBinding()]
param([switch]$WithBrowser, [switch]$Live)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repository
$pythonPath = Join-Path $repository '.venv\Scripts\python.exe'
$ruffPath = Join-Path $repository '.venv\Scripts\ruff.exe'
$browserPython = Join-Path $repository 'tmp\browser-tools\Scripts\python.exe'
$ffmpegDirectory = Join-Path $repository 'tmp\tools\ffmpeg\bin'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if (Test-Path -LiteralPath $ffmpegDirectory) { $env:PATH = "$ffmpegDirectory;$env:PATH" }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Prepare the project .venv first. See docs/local-gemini-setup.md.' }
if (-not (Test-Path -LiteralPath $ruffPath)) { throw 'Install the project development dependencies including Ruff.' }
if (($WithBrowser -or $Live) -and -not (Test-Path -LiteralPath $browserPython)) { throw 'Prepare the optional Playwright environment. See tests/browser/README.md.' }

Write-Output 'Checking Python source...'
& $ruffPath check .
if ($LASTEXITCODE -ne 0) { throw 'Ruff failed.' }
Write-Output 'Checking backend regressions without API calls...'
& $pythonPath -c 'from loguru import logger; logger.remove(); import unittest,sys; result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(''tests'')); sys.exit(not result.wasSuccessful())'
if ($LASTEXITCODE -ne 0) { throw 'Backend regressions failed.' }
Write-Output 'Checking persona case selection without API calls...'
& $pythonPath tools/evaluate_sogangi.py
if ($LASTEXITCODE -ne 0) { throw 'Persona case validation failed.' }

if ($WithBrowser -or $Live) {
    foreach ($testFile in @('tests/browser/sogangi_smoke.py', 'tests/browser/sogangi_product.py', 'tests/browser/live2d_preview.py', 'tests/browser/sogangi_art_review.py', 'tests/browser/sogangi_motion.py', 'tests/browser/sogangi_expressions.py', 'tests/browser/sogangi_live2d_chat.py', 'tests/browser/sogangi_visual.py')) {
        Write-Output "Checking $testFile against the running local server..."
        & $browserPython $testFile
        if ($LASTEXITCODE -ne 0) { throw "Browser regression failed: $testFile" }
    }
}
if ($Live) {
    Write-Output 'Live checks enabled: up to 9 real model calls across persona and audio checks.'
    & $browserPython tests/browser/sogangi_live.py --live
    if ($LASTEXITCODE -ne 0) { throw 'Live browser/audio recovery check failed; skipping other API calls.' }
    & $pythonPath tools/evaluate_sogangi.py --live --max-calls 8
    if ($LASTEXITCODE -ne 0) { throw 'Persona evaluation needs review; see tmp/sogangi-persona/report.json.' }
}
Write-Output 'Selected checks passed. See docs/sogangi-release.md for release scope and manual checks.'
