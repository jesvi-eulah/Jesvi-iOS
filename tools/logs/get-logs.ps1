# Jesvi iOS: collect the phone's logs into one ZIP on the Desktop (Windows).
#   Phone: hold a volume key at the iOS logo -> "Log access (USB)" -> plug in the cable.
#   PowerShell: irm https://raw.githubusercontent.com/jesvi-eulah/Jesvi-iOS/main/tools/logs/get-logs.ps1 | iex
# Downloads Google's platform-tools if fastboot is missing. Reads logs only; writes nothing to the phone.
$ErrorActionPreference = 'Stop'
$work = Join-Path $env:TEMP ("jesvi-logs-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $fb = (Get-Command fastboot.exe -ErrorAction SilentlyContinue).Source
    if (-not $fb) {
        Write-Host "`n==> Downloading fastboot (Google platform-tools)"
        Invoke-WebRequest -UseBasicParsing -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile "$work\pt.zip"
        Expand-Archive "$work\pt.zip" -DestinationPath $work
        $fb = "$work\platform-tools\fastboot.exe"
    }
    Write-Host "`n==> Waiting for the phone (menu -> Log access (USB), cable plugged in)"
    $found = $false
    for ($i = 0; $i -lt 120; $i++) {
        if ((& $fb devices 2>$null) -match 'fastboot') { $found = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $found) {
        Write-Host "Phone not found. Check the menu shows Log access, try another cable/port."
        Write-Host "If Windows shows an unknown device, install Google's USB driver (Android SDK) and retry."
        return
    }
    $out = "$work\jesvi-logs"; New-Item -ItemType Directory -Path $out | Out-Null
    function Grab($name, [string[]]$cmd) {
        & $fb @cmd 2>&1 | Out-Null
        & $fb get_staged "$out\$name.bin" 2>&1 | Out-Null
        if (Test-Path "$out\$name.bin") { Write-Host "   got $name" }
        } else { Write-Host "   (no $name)" }
    }
    Write-Host "`n==> Reading logs"
    Grab 'last-run' @('oem', 'lastlog')
    Grab 'loader' @('oem', 'log')
    & $fb oem memmap 2>&1 | Out-Null
    Grab 'memory-map' @('oem', 'log')
    & $fb getvar all *> "$out\phone-info.txt"
    $zip = Join-Path ([Environment]::GetFolderPath('Desktop')) ("jesvi-logs-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".zip")
    Compress-Archive -Path $out -DestinationPath $zip
    Write-Host "`n==> Done: $zip"
    Write-Host "Send this file to the Jesvi iOS group. It holds logs only: no IMEI, accounts or photos."
} finally {
    Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
}
