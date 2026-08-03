"""
ascii_art.py  –  OS/distro ASCII logos for ZerithSys.
Each logo is a plain string; colours are applied by the caller.
"""
from __future__ import annotations

# ── logos ────────────────────────────────────────────────────────────────────

_UBUNTU = r"""
         _
     ---(_)
 _/  ---  \
(_) |   |
 \  --- _/
     ---(_)
"""

_DEBIAN = r"""
   ___
  (   )
  / . \
 ( (   )
  \ \ /
   ` -'
"""

_WINDOWS = r"""
 ██  ██
 ██  ██
 ─────
 ██  ██
 ██  ██
"""

_ARCH = r"""
     /\
    /  \
   / /\ \
  / /  \ \
 /_/ __ \_\
    /  \
"""

_FEDORA = r"""
  ___
 / __)
| ( _
 \ \_)
  \__)
"""

_LINUX = r"""
   /\
  /  \
 / /\ \
/______\
  |  |
  |__|
"""

_MACOS = r"""
    ___
  _/   \_
 (  o o  )
  \_   _/
    ---
"""

_GENERIC = r"""
  _____
 |     |
 | SYS |
 |_____|
"""

# ── distro mapping ────────────────────────────────────────────────────────────

_MAP: dict[str, tuple[str, str]] = {
    # (art, primary_rich_color)
    "ubuntu":   (_UBUNTU,  "#E95420"),
    "debian":   (_DEBIAN,  "#A80030"),
    "arch":     (_ARCH,    "#1793D1"),
    "fedora":   (_FEDORA,  "#294172"),
    "centos":   (_LINUX,   "#932279"),
    "rhel":     (_LINUX,   "#EE0000"),
    "linux":    (_LINUX,   "#FFD700"),
    "windows":  (_WINDOWS, "#00ADEF"),
    "darwin":   (_MACOS,   "#999999"),
    "macos":    (_MACOS,   "#999999"),
}


def get_ascii_art(os_name: str, distro: str) -> tuple[str, str]:
    """
    Return (art_string, rich_color) for the given OS / distro.

    Parameters
    ----------
    os_name  : platform.system() value  e.g. 'Linux', 'Windows'
    distro   : pretty distro string     e.g. 'Ubuntu 22.04 LTS'
    """
    key = distro.lower()

    for name, (art, color) in _MAP.items():
        if name in key:
            return art, color

    # Fallback by OS family
    os_lower = os_name.lower()
    if "windows" in os_lower:
        return _WINDOWS, "#00ADEF"
    if "darwin" in os_lower:
        return _MACOS, "#999999"

    return _LINUX, "#FFD700"
