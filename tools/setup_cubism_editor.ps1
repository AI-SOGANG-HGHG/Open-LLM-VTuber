[CmdletBinding()]
param([switch]$Install, [switch]$OpenEditor)

$ErrorActionPreference = 'Stop'
$repository = Split-Path -Parent $PSScriptRoot
$installerPath = Join-Path $repository 'tmp/cubism-setup/Live2D_Cubism_Setup_5.1.03.exe'
$installationDirectory = Join-Path $repository 'tmp/tools/cubism-editor-5.1.03'
$reportPath = Join-Path $repository 'tmp/cubism-setup/setup-status.json'
$expectedHash = '65DC89790E81366BA6DAC13960BACEA45DC9F5BD27CEBB6A367E210FFF799DA8'
$officialUrl = 'https://cubism.live2d.com/editor/bin/Live2D_Cubism_Setup_5.1.03.exe'

function Find-Editor {
    if (-not (Test-Path -LiteralPath $installationDirectory)) { return $null }
    $candidate = @(Get-ChildItem -LiteralPath $installationDirectory -Filter '*.exe' -File |
        Where-Object { $_.BaseName -match 'Editor' -and $_.BaseName -notmatch 'Viewer|Uninstall' })
    if ($candidate.Count -eq 1) { return $candidate[0].FullName }
    return $null
}

function Write-SetupStatus([string]$State, [string]$Detail) {
    $report = [ordered]@{
        version = '5.1.03'
        state = $State
        detail = $Detail
        source_url = $officialUrl
        installer_sha256 = $expectedHash.ToLowerInvariant()
        installation_directory = $installationDirectory
        editor_executable = (Find-Editor)
        scope = 'Installer and executable checks only; model verification is separate.'
        model_verification_file = $(if (Test-Path -LiteralPath (Join-Path $repository 'live2d-models/sogangi-minimum/verification.json')) { 'live2d-models/sogangi-minimum/verification.json' } else { $null })
    }
    $report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $report | ConvertTo-Json -Depth 3 | Write-Output
}

if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "Official installer is missing. Download $officialUrl to $installerPath first."
}
if ((Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Installer SHA-256 differs from the reviewed official download.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $installerPath
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike 'CN=Live2D Inc.*') {
    throw 'Official Live2D installer signature did not validate.'
}

if ($Install -and -not (Find-Editor)) {
    Write-SetupStatus 'awaiting_windows_and_installer_confirmation' 'Complete Windows UAC and the official installer; the installer will be visible.'
    try {
        # The official wizard is interactive so the user can read its terms and
        # confirm components. NSIS requires /D to be last, without extra quotes.
        $installer = Start-Process -FilePath $installerPath -ArgumentList "/D=$installationDirectory" -WindowStyle Normal -PassThru
        $installerDeadline = [DateTime]::UtcNow.AddMinutes(10)
        while (-not $installer.WaitForExit(1000)) {
            if ([DateTime]::UtcNow -ge $installerDeadline) {
                Write-SetupStatus 'installer_still_open' 'Finish the official installer, then run this script again with -OpenEditor.'
                exit 2
            }
        }
        if ($installer.ExitCode -ne 0 -or -not (Find-Editor)) {
            Write-SetupStatus 'installation_not_verified' "Installer exited with code $($installer.ExitCode); no unique Editor launcher was found."
            exit 2
        }
    } catch {
        $failureState = 'installer_start_failed'
        $failureDetail = 'Windows did not complete the installer action. Inspect the PowerShell error before trying again.'
        $nativeException = $_.Exception
        while ($null -ne $nativeException) {
            if ($nativeException -is [ComponentModel.Win32Exception] -and $nativeException.NativeErrorCode -eq 1223) {
                $failureState = 'windows_confirmation_not_completed'
                $failureDetail = 'Windows UAC confirmation did not complete. Run -Install only when the user can handle the confirmation.'
                break
            }
            $nativeException = $nativeException.InnerException
        }
        Write-SetupStatus $failureState $failureDetail
        throw
    }
}

$editorPath = Find-Editor
if (-not $editorPath) {
    Write-SetupStatus 'installer_verified_editor_not_installed' 'Run with -Install to open the official installer. Windows UAC requires a user action.'
    if ($OpenEditor) { exit 2 }
    exit 0
}
Write-SetupStatus 'editor_files_present_not_import_verified' 'Editor launcher found; opening/importing a PSD is a separate check.'
if ($OpenEditor) {
    # This is the actual interactive application the user needs to inspect.
    $editor = Start-Process -FilePath $editorPath -WorkingDirectory $installationDirectory -WindowStyle Normal -PassThru
    [ordered]@{ pid=$editor.Id; executable=$editorPath; started_at=$editor.StartTime.ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $repository 'tmp/cubism-setup/editor-process.json') -Encoding UTF8
}
