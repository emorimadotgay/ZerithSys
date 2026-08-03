[CmdletBinding()]
param(
    [switch]$Update,
    [switch]$System,
    [switch]$Help
)

$ErrorActionPreference = "Continue"

if ($Help) {
    Write-Host "Usage: install.ps1 [-Update] [-System]"
    Write-Host "  -Update   Re-install / update an existing copy"
    Write-Host "  -System   Install system-wide (run as Administrator)"
    exit 0
}

$RepoUrl    = "https://github.com/emorimadotgay/ZerithSys"
$RawUrl     = "https://raw.githubusercontent.com/emorimadotgay/ZerithSys/main"
$Branch     = "main"

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

function Find-Python {
    $candidates = @("python", "python3", "py")
    foreach ($cmd in $candidates) {
        $p = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($p) {
            try {
                $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            } catch {
                $ver = $null
            }
            if ($ver) {
                Write-Ok "Found Python $ver  ($($p.Source))"
                return $cmd
            }
        }
    }
    return $null
}

function Install-Python {
    Write-Warn "Python not found on PATH"
    Write-Host ""
    $ans = Read-Host "    Auto-install Python 3.12 from python.org? [Y/n]"
    if ($ans -eq "" -or $ans -match "^[Yy]") {
        $url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe"
        $installer = "$env:TEMP\python-installer.exe"
        Write-Step "Downloading $url"
        try {
            Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
        } catch {
            Write-Err "Download failed: $_"
            exit 1
        }
        Write-Step "Running installer (silent, add-to-PATH)…"
        $proc = Start-Process -FilePath $installer -ArgumentList @(
            "/quiet", "InstallAllUsers=1", "PrependPath=1",
            "Include_test=0", "Include_doc=0", "Include_launcher=1"
        ) -Wait -PassThru
        Remove-Item $installer -Force
        if ($proc.ExitCode -ne 0) { Write-Err "Installer exited with code $($proc.ExitCode)"; exit 1 }
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
        Write-Ok "Python installed. Please re-run this script in a NEW terminal."
        exit 0
    } else {
        Write-Err "Install Python manually from https://www.python.org/downloads/ (tick 'Add to PATH')"
        exit 1
    }
}

function Invoke-Pip {
    param(
        [string]$Python,
        [string[]]$Flags,
        [string[]]$Args
    )
    $allArgs = @("-m", "pip", "install") + $Flags + $Args
    $p = Start-Process -FilePath $Python -ArgumentList $allArgs -NoNewWindow -Wait -PassThru -RedirectStandardError "$env:TEMP\zerithsys-pip.err" -RedirectStandardOutput "$env:TEMP\zerithsys-pip.out"
    $LASTEXITCODE = $p.ExitCode
    if ($p.ExitCode -ne 0 -and (Test-Path "$env:TEMP\zerithsys-pip.err")) {
        $errOut = Get-Content "$env:TEMP\zerithsys-pip.err" -Raw -ErrorAction SilentlyContinue
        if ($errOut) { Write-Host $errOut.Trim() -ForegroundColor DarkGray }
    }
    Remove-Item "$env:TEMP\zerithsys-pip.err","$env:TEMP\zerithsys-pip.out" -ErrorAction SilentlyContinue
    return $p.ExitCode
}

function Install-ZerithSys {
    $python = Find-Python
    if (-not $python) { Install-Python }
    $python = Find-Python
    if (-not $python) { Write-Err "Python still not found. Aborting."; exit 1 }

    $pipFlag = if ($System) { "" } else { "--user" }
    $flags   = @($pipFlag) | Where-Object { $_ -ne "" }

    Write-Step "Trying pip install zerithsys"
    $rc = Invoke-Pip -Python $python -Flags $flags -Args @("zerithsys")
    if ($rc -eq 0) {
        Write-Ok "Installed via PyPI"
        return
    }
    Write-Warn "PyPI install failed (exit $rc) — falling back to GitHub source"

    $installDir = if ($env:ZERITHSYS_HOME) { $env:ZERITHSYS_HOME }
                  elseif ($System)          { "$env:ProgramFiles\ZerithSys" }
                  else                      { "$env:USERPROFILE\.zerithsys" }

    if (Test-Path $installDir) { Remove-Item -Recurse -Force $installDir }
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null

    $zip = "$env:TEMP\zerithsys.zip"
    Write-Step "Downloading from $RawUrl"
    try {
        Invoke-WebRequest -Uri "$RepoUrl/archive/$Branch.zip" -OutFile $zip -UseBasicParsing
    } catch {
        Write-Err "Download failed: $_"
        exit 1
    }
    Write-Step "Extracting to $installDir"
    Expand-Archive -Path $zip -DestinationPath $installDir -Force
    if (Test-Path (Join-Path $installDir "ZerithSys-$Branch")) {
        Move-Item -Path (Join-Path $installDir "ZerithSys-$Branch\*") -Destination $installDir -Force
        Remove-Item (Join-Path $installDir "ZerithSys-$Branch") -Recurse -Force
    } elseif (Test-Path (Join-Path $installDir "zerithsys-$Branch")) {
        Move-Item -Path (Join-Path $installDir "zerithsys-$Branch\*") -Destination $installDir -Force
        Remove-Item (Join-Path $installDir "zerithsys-$Branch") -Recurse -Force
    }
    Remove-Item $zip

    Write-Step "Installing dependencies"
    $rc = Invoke-Pip -Python $python -Flags $flags -Args @("-r", (Join-Path $installDir "requirements.txt"))
    if ($rc -ne 0) { Write-Err "Failed to install requirements (exit $rc)"; exit 1 }

    Write-Step "Installing zerithsys package"
    $rc = Invoke-Pip -Python $python -Flags $flags -Args @($installDir)
    if ($rc -ne 0) { Write-Err "Failed to install package (exit $rc)"; exit 1 }

    Write-Ok "Installed from source to $installDir"
}

function Find-Scripts-Path {
    param([string]$Python, [bool]$IsSystem)
    $scheme = if ($IsSystem) { "nt" } else { "nt_user" }
    try {
        $p = & $Python -c "import sysconfig; print(sysconfig.get_path('scripts', '$scheme'))" 2>$null
        if ($p) { return $p }
    } catch {}
    if ($IsSystem) { return "$env:ProgramFiles\Python314\Scripts" }
    return Join-Path $env:APPDATA "Python\Python314\Scripts"
}

function Post-Install {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "    ZerithSys installed successfully!         " -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host ""

    $python   = Find-Python
    $scripts  = Find-Scripts-Path -Python $python -IsSystem ([bool]$System)
    $batPath  = Join-Path $scripts "zerithsys.exe"
    $batAlt   = Join-Path $scripts "zerithsys.bat"

    if (Test-Path $batPath) {
        Write-Ok "Launcher: $batPath"
    } elseif (Test-Path $batAlt) {
        Write-Ok "Launcher: $batAlt"
    } else {
        Write-Warn "Launcher not found at expected location ($scripts)"
    }

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

Write-Header
Install-ZerithSys
Post-Install
