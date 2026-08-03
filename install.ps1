# ════════════════════════════════════════════════════════════════════════════
#  ZerithSys  –  one-liner installer  (Windows PowerShell)
#
#  Usage (run in PowerShell as Administrator for system install):
#    irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex
#    irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex -Args @('--user')
# ════════════════════════════════════════════════════════════════════════════
[CmdletBinding()]
param(
    [switch]$Update,
    [switch]$System,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "Usage: install.ps1 [-Update] [-System]"
    Write-Host "  -Update   Re-install / update an existing copy"
    Write-Host "  -System   Install system-wide (run as Administrator)"
    exit 0
}

# ── config ───────────────────────────────────────────────────────────────
$RepoUrl    = "https://github.com/zerithsys/zerithsys"
$RawUrl     = "https://raw.githubusercontent.com/zerithsys/zerithsys/main"
$Branch     = "main"

# ── helpers ──────────────────────────────────────────────────────────────
function Write-Header {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "            ZerithSys installer               " -ForegroundColor Cyan
    Write-Host "   a real-time system monitor for Windows     " -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step   { param($msg) Write-Host "[*] $msg" -ForegroundColor Blue }
function Write-Ok     { param($msg) Write-Host "[+] $msg" -ForegroundColor Green }
function Write-Warn   { param($msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err    { param($msg) Write-Host "[x] $msg" -ForegroundColor Red }

# ── locate Python ────────────────────────────────────────────────────────
function Find-Python {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        $p = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($p) {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver) {
                Write-Ok "Found Python $ver  ($($p.Source))"
                return $cmd
            }
        }
    }
    return $null
}

# ── install Python if missing ───────────────────────────────────────────
function Install-Python {
    Write-Warn "Python not found on PATH"
    Write-Host ""
    $ans = Read-Host "    Auto-install Python 3.12 from python.org? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        $url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
        $installer = "$env:TEMP\python-installer.exe"
        Write-Step "Downloading $url"
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        Write-Step "Running installer (silent, add-to-PATH)…"
        $proc = Start-Process -FilePath $installer -ArgumentList @(
            "/quiet", "InstallAllUsers=1", "PrependPath=1",
            "Include_test=0", "Include_doc=0", "Include_launcher=1"
        ) -Wait -PassThru
        Remove-Item $installer -Force
        if ($proc.ExitCode -ne 0) { Write-Err "Installer exited with code $($proc.ExitCode)"; exit 1 }
        # refresh env
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        Write-Ok "Python installed. Please re-run this script in a NEW terminal."
        exit 0
    } else {
        Write-Err "Install Python manually from https://www.python.org/downloads/ (tick 'Add to PATH')"
        exit 1
    }
}

# ── install ZerithSys ───────────────────────────────────────────────────
function Install-ZerithSys {
    $python = Find-Python
    if (-not $python) { Install-Python }
    $python = Find-Python   # re-resolve

    $pipFlag = if ($System) { "" } else { "--user" }
    $flags   = @($pipFlag) | Where-Object { $_ -ne "" }

    # Try PyPI first
    Write-Step "Trying pip install zerithsys"
    $pypi = & $python -m pip install @flags --quiet zerithsys 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "Installed via PyPI"
        return
    }

    Write-Warn "PyPI install failed — falling back to GitHub source"

    $installDir = if ($env:ZERITHSYS_HOME) { $env:ZERITHSYS_HOME }
                  elseif ($System)          { "$env:ProgramFiles\ZerithSys" }
                  else                      { "$env:USERPROFILE\.zerithsys" }

    if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null

    # Download tarball
    $zip = "$env:TEMP\zerithsys.zip"
    Write-Step "Downloading from $RawUrl"
    Invoke-WebRequest -Uri "$RepoUrl/archive/$Branch.zip" -OutFile $zip -UseBasicParsing
    Write-Step "Extracting to $installDir"
    Expand-Archive -Path $zip -DestinationPath $installDir -Force
    Move-Item -Path (Join-Path $installDir "zerithsys-$Branch\*") -Destination $installDir -Force
    Remove-Item (Join-Path $installDir "zerithsys-$Branch") -Recurse -Force
    Remove-Item $zip

    Write-Step "Installing dependencies"
    & $python -m pip install @flags --quiet -r (Join-Path $installDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install requirements"; exit 1 }

    Write-Step "Installing zerithsys package"
    & $python -m pip install @flags --quiet $installDir
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install package"; exit 1 }

    Write-Ok "Installed from source to $installDir"
}

# ── post-install: create launcher + PATH hint ───────────────────────────
function Post-Install {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "    ZerithSys installed successfully!         " -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host ""

    # Find the binary
    $python   = Find-Python
    $scripts  = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt' if '$System' else 'nt_user'))"
    $batPath  = Join-Path $scripts "zerithsys.bat"

    if (Test-Path $batPath) {
        Write-Ok "Launcher: $batPath"
    } else {
        Write-Warn "Launcher not found at expected location"
    }

    # Add to user PATH if not present
    $scriptsLower = $scripts.ToLower()
    $userPath     = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notmatch [regex]::Escape($scriptsLower)) {
        $addIt = Read-Host "    Add $scripts to your user PATH? [Y/n]"
        if ($addIt -eq "" -or $addIt -match "^[Yy]") {
            [Environment]::SetEnvironmentVariable("Path", "$userPath;$scripts", "User")
            $env:Path = "$env:Path;$scripts"
            Write-Ok "PATH updated. Restart your terminal for it to take effect."
        }
    }

    Write-Host ""
    Write-Host "    Run it with:  " -NoNewline
    Write-Host "zerithsys" -ForegroundColor Cyan
    Write-Host ""
}

# ── main ────────────────────────────────────────────────────────────────
Write-Header
Install-ZerithSys
Post-Install
