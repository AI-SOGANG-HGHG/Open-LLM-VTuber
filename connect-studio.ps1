[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Connect Persona Studio to your existing Gemini API.'
Write-Host 'The key is hidden, used only by the local server, and is not saved to a file.'
$studioGeminiKey = Read-Host 'Gemini API key (paste and press Enter)' -AsSecureString
try {
    $env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $studioGeminiKey).Password
    if ([string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)) { throw 'An API key is required.' }
    & (Join-Path $PSScriptRoot 'restart-local.ps1')
    Write-Host 'Studio conversation server is ready. You may close this input window.'
    Write-Host 'Return to Persona Studio and select a character, or press Reconnect.'
} finally {
    Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
    if ($studioGeminiKey) { $studioGeminiKey.Dispose() }
    Remove-Variable studioGeminiKey -ErrorAction SilentlyContinue
}
