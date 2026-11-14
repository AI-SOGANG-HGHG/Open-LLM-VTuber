$ErrorActionPreference = 'Stop'
$metadataPath = Join-Path $PSScriptRoot 'tmp\server-process.json'

if (-not (Test-Path -LiteralPath $metadataPath)) {
    Write-Output 'No recorded background server. Use Ctrl+C for a server running in your terminal.'
    exit 0
}

$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$serverProcess = Get-Process -Id ([int]$metadata.pid) -ErrorAction SilentlyContinue
if (-not $serverProcess) {
    Write-Output 'The recorded background server is already stopped.'
    exit 0
}

$expectedStart = [string]$metadata.startTimeUtcTicks
$actualStart = [string]$serverProcess.StartTime.ToUniversalTime().Ticks
if ($actualStart -ne $expectedStart -or
    -not $serverProcess.Path.StartsWith($PSScriptRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The recorded process no longer matches this project server. No process was stopped.'
}

Stop-Process -Id $serverProcess.Id -ErrorAction Stop
Remove-Item -LiteralPath $metadataPath
Write-Output 'Stopped the project background server.'
