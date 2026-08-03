[CmdletBinding()]
param([switch]$System)

$ErrorActionPreference = "Stop"

Write-Host "[*] Removing ZerithSys..." -ForegroundColor Blue

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Write-Host "[*] pip uninstall zerithsys" -ForegroundColor Blue
    & python -m pip uninstall -y zerithsys 2>$null | Out-Null
}

$dir = if ($System)             { "$env:ProgramFiles\ZerithSys" }
       elseif ($env:ZERITHSYS_HOME) { $env:ZERITHSYS_HOME" }
       else                     { "$env:USERPROFILE\.zerithsys" }

if (Test-Path $dir) {
    Write-Host "[*] Removing $dir" -ForegroundColor Blue
    Remove-Item -Recurse -Force $dir
}

$scripts = & python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt' if '$System' else 'nt_user'))" 2>$null
if ($scripts -and (Test-Path "$scripts\zerithsys.bat")) {
    Remove-Item -Force "$scripts\zerithsys.bat"
}

if ($scripts) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -match [regex]::Escape($scripts)) {
        $newPath = ($userPath -split ";" | Where-Object { $_ -ne $scripts }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "[*] Removed $scripts from PATH" -ForegroundColor Blue
    }
}

Write-Host "[+] ZerithSys removed." -ForegroundColor Green
Write-Host ""
Write-Host "Note: dependencies (textual, psutil, etc.) were NOT removed." -ForegroundColor Yellow
Write-Host "Uninstall them with:  python -m pip uninstall textual psutil py-cpuinfo rich requests"
