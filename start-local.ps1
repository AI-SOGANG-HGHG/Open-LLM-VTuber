[CmdletBinding()]
param(
    [switch]$VerboseLog
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$ffmpegDirectory = Join-Path $PSScriptRoot 'tmp\tools\ffmpeg\bin'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'The project virtual environment is missing. Install dependencies with uv sync --locked first.'
}
if (-not (Test-Path -LiteralPath 'conf.yaml')) {
    throw 'conf.yaml is missing. Create the local configuration before starting the server.'
}
if (Test-Path -LiteralPath (Join-Path $ffmpegDirectory 'ffmpeg.exe')) {
    $env:PATH = "$ffmpegDirectory;$env:PATH"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw 'FFmpeg is missing. Install it or place the portable build in tmp\tools\ffmpeg\bin.'
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$serverArguments = @('-u', 'run_server.py')
if ($VerboseLog) {
    $serverArguments += '--verbose'
}

& $pythonPath @serverArguments
exit $LASTEXITCODE
