[CmdletBinding()]
param([switch]$OpenBrowser)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$metadataPath = Join-Path $PSScriptRoot 'tmp\server-process.json'
$ffmpegDirectory = Join-Path $PSScriptRoot 'tmp\tools\ffmpeg\bin'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath 'conf.yaml')) {
    throw 'The project environment and conf.yaml must exist before restarting.'
}
$portReader = @'
from pathlib import Path
import yaml
print(int(yaml.safe_load(Path('conf.yaml').read_text(encoding='utf-8'))['system_config']['port']))
'@
$portOutput = & $pythonPath -c $portReader
if ($LASTEXITCODE -ne 0) { throw 'Could not read the local server port.' }
$serverPort = [int]$portOutput
if ($serverPort -lt 1 -or $serverPort -gt 65535) { throw 'Invalid local server port.' }
if (Test-Path -LiteralPath (Join-Path $ffmpegDirectory 'ffmpeg.exe')) {
    $env:PATH = "$ffmpegDirectory;$env:PATH"
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'FFmpeg is missing.' }
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'tmp') -Force | Out-Null

function Save-ServerMetadata($serverProcess) {
    @{pid=$serverProcess.Id;startTimeUtcTicks=[string]$serverProcess.StartTime.ToUniversalTime().Ticks} |
        ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'tmp\server.pid') -Value $serverProcess.Id
}

$listenerIds = @(Get-NetTCPConnection -LocalPort $serverPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
if ($listenerIds.Count -gt 0) {
    if (-not (Test-Path -LiteralPath $metadataPath)) {
        throw 'The port is in use without project process metadata. No process was stopped.'
    }
    $metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
    foreach ($listenerId in $listenerIds) {
        $existing = Get-Process -Id $listenerId -ErrorAction Stop
        $info = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerId"
        if ($listenerId -ne [int]$metadata.pid -or
            [string]$existing.StartTime.ToUniversalTime().Ticks -ne [string]$metadata.startTimeUtcTicks -or
            -not $existing.Path.StartsWith($PSScriptRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
            $info.CommandLine -notmatch 'run_server\.py') {
            throw 'The listener does not match the recorded project server. No process was stopped.'
        }
        Stop-Process -Id $listenerId -ErrorAction Stop
        Wait-Process -Id $listenerId -Timeout 15 -ErrorAction SilentlyContinue
        Write-Output "Stopped project server PID $listenerId"
    }
}

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$launcher = Start-Process -FilePath $pythonPath -ArgumentList @('-u', 'run_server.py') `
    -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $PSScriptRoot 'tmp\server.stdout.log') `
    -RedirectStandardError (Join-Path $PSScriptRoot 'tmp\server.stderr.log') -PassThru
Save-ServerMetadata $launcher

$ready = $false
$deadline = [DateTime]::UtcNow.AddSeconds(45)
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$serverPort/" -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}
$listeners = @(Get-NetTCPConnection -LocalPort $serverPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
if ($listeners.Count -eq 1) {
    $actual = Get-Process -Id $listeners[0]
    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $($actual.Id)"
    if ($actual.Path.StartsWith($PSScriptRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -and
        ($actual.Id -eq $launcher.Id -or $info.ParentProcessId -eq $launcher.Id) -and
        $info.CommandLine -match 'run_server\.py') {
        Save-ServerMetadata $actual
    } else { throw 'An unexpected process is using the port after startup.' }
}
if (-not $ready) { throw 'The server did not become ready in 45 seconds. Inspect redacted local logs.' }
$url = "http://localhost:$serverPort/web-tool/sogangi/"
Write-Output "Server HTTP ready: $url"
if ($OpenBrowser) { Start-Process $url }
