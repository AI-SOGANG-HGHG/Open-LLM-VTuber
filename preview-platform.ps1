param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 12401
)

$ErrorActionPreference = 'Stop'
$platformPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$platformPreview = Join-Path $PSScriptRoot 'tools/platform_preview.py'
if (-not (Test-Path -LiteralPath $platformPython)) {
    throw 'The project Python environment is missing. See web_tool/platform/README.md.'
}

Write-Host "Persona Studio demo: http://localhost:$Port/platform/"
Write-Host 'Local preview only. No model/API calls. Press Ctrl+C to stop.'
& $platformPython $platformPreview --port $Port
exit $LASTEXITCODE
