#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  ZerithSys  –  one-liner installer  (Debian / Ubuntu / Arch / Fedora / macOS)
#
#  Usage:
#    curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash
#    curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash -s -- --update
#    curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash -s -- --system
# ════════════════════════════════════════════════════════════════════════════
set -e

# ── config ─────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/zerithsys/zerithsys"
RAW_URL="https://raw.githubusercontent.com/zerithsys/zerithsys/main"
BRANCH="main"
PY_MIN="3.8"

# ── flags ──────────────────────────────────────────────────────────────────
DO_UPDATE=0
DO_SYSTEM=0
for arg in "$@"; do
    case "$arg" in
        --update|-u) DO_UPDATE=1 ;;
        --system|-s) DO_SYSTEM=1 ;;
        --help|-h)
            echo "Usage: install.sh [--update] [--system]"
            echo "  --update   Re-install / update an existing copy"
            echo "  --system   Install system-wide (requires sudo)"
            exit 0
            ;;
    esac
done

# ── colours ────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    B='\033[1m'; RED='\033[0;31m'; GRN='\033[0;32m'
    YLW='\033[1;33m'; BLU='\033[0;34m'; DIM='\033[2m'; NC='\033[0m'
else
    B=''; RED=''; GRN=''; YLW=''; BLU=''; DIM=''; NC=''
fi

# ── helpers ────────────────────────────────────────────────────────────────
log()  { printf "${BLU}[*]${NC} %s\n" "$*"; }
ok()   { printf "${GRN}[+]${NC} %s\n" "$*"; }
warn() { printf "${YLW}[!]${NC} %s\n" "$*"; }
die()  { printf "${RED}[x]${NC} %s\n" "$*" >&2; exit 1; }

header() {
    printf "${B}${BLU}\n"
    printf "  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    printf "  ┃            ZerithSys installer            ┃\n"
    printf "  ┃   a real-time system monitor for *nix     ┃\n"
    printf "  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
    printf "${NC}\n"
}

# ── detect OS / pkg manager ───────────────────────────────────────────────
detect_os() {
    if   command -v apt-get >/dev/null 2>&1; then
        OS="debian"; PKG_INSTALL="sudo apt-get install -y"
    elif command -v dnf     >/dev/null 2>&1; then
        OS="fedora"; PKG_INSTALL="sudo dnf install -y"
    elif command -v yum     >/dev/null 2>&1; then
        OS="rhel";   PKG_INSTALL="sudo yum install -y"
    elif command -v pacman  >/dev/null 2>&1; then
        OS="arch";   PKG_INSTALL="sudo pacman -S --noconfirm"
    elif command -v apk     >/dev/null 2>&1; then
        OS="alpine"; PKG_INSTALL="sudo apk add"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        if   command -v brew >/dev/null 2>&1; then
            PKG_INSTALL="brew install"
        else
            die "Homebrew not found. Install it from https://brew.sh"
        fi
    else
        OS="unknown"; PKG_INSTALL=""
    fi
    log "Detected OS family: ${B}${OS}${NC}"
}

# ── python check ──────────────────────────────────────────────────────────
check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        warn "Python 3 not found — installing it now"
        case "$OS" in
            debian)  $PKG_INSTALL python3 python3-pip python3-venv ;;
            fedora)  $PKG_INSTALL python3 python3-pip ;;
            rhel)    $PKG_INSTALL python3 python3-pip ;;
            arch)    $PKG_INSTALL python python-pip ;;
            alpine)  $PKG_INSTALL python3 py3-pip ;;
            macos)   brew install python ;;
            *)       die "Cannot auto-install Python on this OS — please install manually" ;;
        esac
    fi

    PY=$(command -v python3)
    VER=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    ok "Found Python $VER  (${DIM}$PY${NC})"

    if ! $PY -m pip --version >/dev/null 2>&1; then
        warn "pip missing — bootstrapping"
        $PY -m ensurepip --upgrade || {
            case "$OS" in
                debian) $PKG_INSTALL python3-pip ;;
                fedora) $PKG_INSTALL python3-pip ;;
                *)      die "Cannot install pip — please install it manually" ;;
            esac
        }
    fi
}

# ── install destination ───────────────────────────────────────────────────
choose_paths() {
    if [ "$DO_SYSTEM" -eq 1 ]; then
        INSTALL_DIR="/opt/zerithsys"
        BIN_DIR="/usr/local/bin"
        PIP_FLAGS="--break-system-packages"
        SUDO="sudo"
    else
        INSTALL_DIR="${ZERITHSYS_HOME:-$HOME/.zerithsys}"
        BIN_DIR="${ZERITHSYS_BIN:-$HOME/.local/bin}"
        PIP_FLAGS="--user"
        SUDO=""
    fi
}

# ── try PyPI first, then source ───────────────────────────────────────────
install_zerithsys() {
    log "Trying pip install zerithsys ${PIP_FLAGS}"
    if $PY -m pip install $PIP_FLAGS --quiet zerithsys 2>/dev/null; then
        ok "Installed via PyPI"
        return 0
    fi

    warn "PyPI install failed — falling back to source from GitHub"

    # Need git or curl+tar
    if command -v git >/dev/null 2>&1; then
        if [ -d "$INSTALL_DIR/.git" ]; then
            log "Updating existing repo in $INSTALL_DIR"
            (cd "$INSTALL_DIR" && git pull --depth 1 --quiet)
        else
            log "Cloning $REPO_URL to $INSTALL_DIR"
            $SUDO rm -rf "$INSTALL_DIR"
            $SUDO git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_DIR"
        fi
    else
        # Fallback: download tarball
        if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
            die "Need git OR (curl OR wget) to download ZerithSys"
        fi
        log "Downloading tarball from $REPO_URL"
        TMP=$(mktemp -d)
        TARBALL="$TMP/zerithsys.tar.gz"
        if command -v curl >/dev/null 2>&1; then
            curl -sSL "$REPO_URL/archive/$BRANCH.tar.gz" -o "$TARBALL"
        else
            wget -q "$REPO_URL/archive/$BRANCH.tar.gz" -O "$TARBALL"
        fi
        $SUDO mkdir -p "$INSTALL_DIR"
        $SUDO tar -xzf "$TARBALL" -C "$INSTALL_DIR" --strip-components=1
        rm -rf "$TMP"
    fi

    log "Installing Python dependencies"
    $PY -m pip install $PIP_FLAGS --quiet -r "$INSTALL_DIR/requirements.txt"

    # Install our package so we get a proper console_script entry point
    log "Installing zerithsys package"
    $PY -m pip install $PIP_FLAGS --quiet "$INSTALL_DIR"

    ok "Installed from source to $INSTALL_DIR"
}

# ── post-install PATH hint ───────────────────────────────────────────────
post_install() {
    printf "\n${B}${GRN}"
    printf "  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    printf "  ┃   ZerithSys installed successfully!       ┃\n"
    printf "  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛\n"
    printf "${NC}\n"

    # Locate the binary (pip creates it as a console_script)
    if [ "$DO_SYSTEM" -eq 1 ]; then
        BIN_PATH="$BIN_DIR/zerithsys"
    else
        # The user-site bin is usually ~/.local/bin on Linux, ~/Library/Python/X.Y/bin on macOS
        BIN_PATH=$($PY -c "import sysconfig; print(sysconfig.get_path('scripts', f'{sysconfig.get_preferred_scheme()}user' if '--user' in '$PIP_FLAGS' else 'posix_user'))" 2>/dev/null || echo "$BIN_DIR")
        BIN_PATH="$BIN_PATH/zerithsys"
    fi

    if [ -x "$BIN_PATH" ]; then
        ok "Binary: ${B}$BIN_PATH${NC}"
    else
        warn "Binary not at expected location — try: ${B}$PY -m pip show zerithsys${NC}"
    fi

    # PATH warning
    BIN_PARENT=$(dirname "$BIN_PATH" 2>/dev/null || echo "$BIN_DIR")
    if [[ ":$PATH:" != *":$BIN_PARENT:"* ]]; then
        printf "\n${YLW}[NOTE]${NC} $BIN_PARENT is not in your PATH.\n"
        printf "Add this to your ~/.bashrc / ~/.zshrc:\n"
        printf "  ${B}export PATH=\"$BIN_PARENT:\$PATH\"${NC}\n\n"
        printf "Or run it directly with:  ${B}$BIN_PATH${NC}\n"
    else
        printf "Run it with:  ${B}zerithsys${NC}\n"
    fi
}

# ── main ──────────────────────────────────────────────────────────────────
header
detect_os
check_python
choose_paths
install_zerithsys
post_install
