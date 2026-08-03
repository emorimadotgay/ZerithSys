#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
#  ZerithSys  –  uninstaller  (Debian / Ubuntu / Arch / Fedora / macOS)
#  Usage:
#    curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.sh | bash
#    curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.sh | bash -s -- --system
# ════════════════════════════════════════════════════════════════════════════
set -e

B='\033[1m'; RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'

DO_SYSTEM=0
[ "${1:-}" = "--system" ] || [ "${1:-}" = "-s" ] && DO_SYSTEM=1

echo -e "${BLU}[*]${NC} Removing ZerithSys..."

# pip uninstall
PY=$(command -v python3 || command -v python || true)
if [ -n "$PY" ]; then
    echo -e "${BLU}[*]${NC} pip uninstall zerithsys"
    $PY -m pip uninstall -y zerithsys 2>/dev/null || true
fi

# remove user install dir
if [ "$DO_SYSTEM" -eq 1 ]; then
    echo -e "${BLU}[*]${NC} Removing /opt/zerithsys (sudo)"
    sudo rm -rf /opt/zerithsys
    sudo rm -f /usr/local/bin/zerithsys
else
    echo -e "${BLU}[*]${NC} Removing ~/.zerithsys"
    rm -rf "$HOME/.zerithsys"
    rm -f "$HOME/.local/bin/zerithsys"
fi

echo -e "${GRN}[+]${NC} ZerithSys removed."
echo ""
echo "Note: dependencies (textual, psutil, etc.) were NOT removed — uninstall with:"
echo "  $PY -m pip uninstall textual psutil py-cpuinfo rich requests"
