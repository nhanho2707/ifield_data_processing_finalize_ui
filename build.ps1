# Build the desktop application.
#   powershell -ExecutionPolicy Bypass -File build.ps1
# Output:
#   dist\iFieldDataProcessing\                  the application folder
#   dist\iFieldDataProcessing-<version>.zip     portable copy to share
#   dist\iFieldDataProcessing-Setup-<version>.exe  installer (only when Inno Setup 6.3+ is installed)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = (python -c "from app import __version__; print(__version__)").Trim()
Write-Host "Building iField Data Processing $version"

python -m PyInstaller --noconfirm --clean ifield.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = "dist\iFieldDataProcessing\iField Data Processing.exe"
$report = "dist\self_test.txt"
$test = Start-Process -FilePath $exe -ArgumentList "--self-test", $report -Wait -PassThru
Get-Content $report
if ($test.ExitCode -ne 0) { throw "Self-test of the built application failed" }

# Freshly built files can stay locked for a few seconds (antivirus scan): retry.
function Invoke-WithRetry([scriptblock]$action, [string]$what) {
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try { & $action; return } catch {
            if ($attempt -eq 5) { throw }
            Write-Host "$what failed ($($_.Exception.Message)), retrying..."
            Start-Sleep -Seconds 5
        }
    }
}

$zip = "dist\iFieldDataProcessing-$version.zip"
Invoke-WithRetry { Compress-Archive -Path "dist\iFieldDataProcessing" -DestinationPath $zip -Force } "Zip"
Write-Host "Portable zip: $zip"

# Inno Setup: winget install JRSoftware.InnoSetup --scope user
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
foreach ($candidate in @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
                         "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                         "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
    if (-not $iscc -and (Test-Path $candidate)) { $iscc = $candidate }
}
if ($iscc) {
    Invoke-WithRetry {
        & $iscc /Q "/DAppVersion=$version" installer.iss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    } "Installer"
    Write-Host "Installer: dist\iFieldDataProcessing-Setup-$version.exe"
} else {
    Write-Host "Inno Setup not found: installer skipped (winget install JRSoftware.InnoSetup --scope user)."
}
