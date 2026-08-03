#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SysInfo Pro
===========
Neofetch-killer: real-time, interactive, cross-platform system monitor.

- Auto-detect OS (Linux/Debian/Ubuntu/macOS/Windows) + Smart Fallback
- Deep hardware health: CPU/GPU/disk temps, fan RPM, per-core clocks
- Network traffic HISTORY (session + today), not just instant speed
- Container / VM awareness (Docker, LXC, Podman, KVM, VMware, Hyper-V...)
- Custom TrueColor (24-bit) themes + ASCII art engine
- Live refresh (giống btop/htop) + điều khiển bằng phím tắt

Only hard dependency: psutil (pip install psutil --break-system-packages)
Everything else (nvidia-smi, wmic, rocm-smi, lm-sensors...) is optional
and used only if found -> never crashes if missing (Smart Fallback).

Author: generated for user by Claude
License: MIT - free to modify
"""

import argparse
import ctypes
import json
import os
import platform
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque, OrderedDict
from datetime import datetime, date
from pathlib import Path

try:
    import psutil
except ImportError:
    sys.stderr.write(
        "\n[LOI] Thieu thu vien 'psutil'.\n"
        "Cai bang: pip install psutil --break-system-packages\n"
        "(hoac: pip install psutil  neu khong dung Debian/Ubuntu he thong)\n\n"
    )
    sys.exit(1)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MACOS = platform.system() == "Darwin"

APP_DIR = Path.home() / ".sysinfo_pro"
APP_DIR.mkdir(exist_ok=True)
NET_LOG_DIR = APP_DIR / "netlog"
NET_LOG_DIR.mkdir(exist_ok=True)
THEME_FILE_DEFAULT = APP_DIR / "theme.json"


# =====================================================================
#  ANSI / TrueColor engine (khong phu thuoc rich/colorama)
# =====================================================================

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
ALT_SCREEN_ON = "\x1b[?1049h"
ALT_SCREEN_OFF = "\x1b[?1049l"
CLEAR_HOME = "\x1b[H\x1b[2J"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def supports_truecolor() -> bool:
    if os.environ.get("SYSINFO_NO_COLOR"):
        return False
    ct = os.environ.get("COLORTERM", "")
    if "truecolor" in ct or "24bit" in ct:
        return True
    # Windows Terminal / modern cmd co ho tro ANSI tu Windows 10 1809+
    if IS_WINDOWS:
        return True
    return True  # da so terminal hien dai deu OK; nguoi dung co the --no-color


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fg(hexcolor: str, text: str, bold=False) -> str:
    if not COLOR_ENABLED:
        return text
    r, g, b = hex_to_rgb(hexcolor)
    prefix = BOLD if bold else ""
    return f"{prefix}\x1b[38;2;{r};{g};{b}m{text}{RESET}"


def visible_len(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def pad_visible(s: str, width: int) -> str:
    vlen = visible_len(s)
    if vlen >= width:
        return s
    return s + " " * (width - vlen)


def truncate_visible(s: str, width: int) -> str:
    """Cat chuoi theo do dai hien thi thuc (bo qua ma ANSI)."""
    if visible_len(s) <= width:
        return s
    out = []
    cur = 0
    i = 0
    while i < len(s) and cur < width:
        m = _ANSI_RE.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        out.append(s[i])
        cur += 1
        i += 1
    tail = RESET if COLOR_ENABLED else ""
    return "".join(out) + tail


COLOR_ENABLED = True  # se duoc set trong main() theo --no-color


# =====================================================================
#  Theme
# =====================================================================

DEFAULT_THEME = {
    "name": "aurora",
    "accent": "#7DD3FC",     # xanh cyan - tieu de panel / vien
    "accent2": "#C084FC",    # tim - nhan phu
    "text": "#E5E7EB",       # trang xam - chu thuong
    "muted": "#6B7280",      # xam mo - chu it quan trong
    "ok": "#4ADE80",         # xanh la - binh thuong
    "warn": "#FACC15",       # vang - canh bao
    "crit": "#F87171",       # do - nguy hiem
    "bar_bg": "#1F2937",
    "ascii_art": None        # duong dan file .txt ascii art tuy chinh (rong = dung mac dinh theo distro)
}


def load_theme(path: str = None) -> dict:
    theme = dict(DEFAULT_THEME)
    p = Path(path) if path else THEME_FILE_DEFAULT
    if p.exists():
        try:
            user_theme = json.loads(p.read_text(encoding="utf-8"))
            theme.update(user_theme)
        except Exception:
            pass
    return theme


def save_default_theme_if_missing():
    if not THEME_FILE_DEFAULT.exists():
        THEME_FILE_DEFAULT.write_text(
            json.dumps(DEFAULT_THEME, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def level_color(theme, percent: float) -> str:
    if percent >= 85:
        return theme["crit"]
    if percent >= 60:
        return theme["warn"]
    return theme["ok"]


# =====================================================================
#  ASCII Art (nho, gon, xep canh panel thong tin - kieu neofetch)
# =====================================================================

ASCII_ART = {
    "ubuntu": r"""
      .-/+oossssoo+/-.
  `:+ssssssssssssssssss+:`
-+ssssssssssssssssssyyssss+-
.ossssssssssssssssssdMMMNysssso.
/sssssssssssshdmmNNmmyNMMMMhssssss/
+sssssssssshmydMMMMMMMNddddyssssssss+
/sssssssshNMMMyhhyyyyhmNMMMNhssssssss/
.ssssssssdMMMNhsssssssssshNMMMdssssssss.
+sssshhhyNMMNyssssssssssssyNMMMysssssss+
ossyNMMMNyMMhsssssssssssssshmmmhssssssso
+sssshhhyNMMNyssssssssssssyNMMMysssssss+
.ssssssssdMMMNhsssssssssshNMMMdssssssss.
/sssssssshNMMMyhhyyyyhdNMMMNhssssssss/
+sssssssssdmydMMMMMMMMddddyssssssss+
/sssssssssssshdmNNNNmyNMMMMhssssss/
.ossssssssssssssssssdMMMNysssso.
""",
    "debian": r"""
       _,met$$$$$gg.
    ,g$$$$$$$$$$$$$$$P.
  ,g$$P""       ""6$$$.
 ,$$P'              `$$$.
',$$P       ,ggs.     `$$b:
`d$$'     ,$P"'   .    $$$
 $$P      d$'     ,    $$P
 $$:      $$.   -    ,d$$'
 $$;      Y$b._   _,d$P'
 Y$$.    `.`"Y$$$$P"'
 `$$b      "-.__
  `Y$$
   `Y$$.
""",
    "windows": r"""
        ,.=:^!^!t3Z3z.,
       :tt:::tt333EE3
       Et:::ztt33EEEL
      ;tt:::tt333EE7
     :Et:::zt333EEQ.
     it::::tt333EEF
    ;3=*^```"*4EEV
    ,.=::::it=.,
   ;::::::::zt33)
  :t::::::::tt33.
  i::::::::zt33F
 ;:::::::::t33V
 E::::::::zt33L
{3=*^```"*4E3)
""",
    "macos": r"""
                    'c.
                 ,xNMM.
               .OMMMMo
               OMMM0,
     .;loddo:' loolloddol;.
   cKMMMMMMMMMMNWMMMMMMMMMM0:
 .KMMMMMMMMMMMMMMMMMMMMMMMWd.
 XMMMMMMMMMMMMMMMMMMMMMMMX.
;MMMMMMMMMMMMMMMMMMMMMMMM:
:MMMMMMMMMMMMMMMMMMMMMMMM:
.MMMMMMMMMMMMMMMMMMMMMMMMX.
 kMMMMMMMMMMMMMMMMMMMMMMMMWd.
  .XMMMMMMMMMMMMMMMMMMMMMMMMK.
""",
    "container": r"""
      ______________
     /|            |\
    / |  DOCKER    | \
   /__|  CONTAINER |__\
   |   ~~~~~~~~~~~~~   |
   |  [x][x][x] [x][x] |
   |_____________________|
""",
    "generic_linux": r"""
        #####
       #######
       ##O#O##
       #######
     ###########
    #############
   ###############
   ################
""",
}


def get_ascii_art(distro_id: str, virt_type: str, custom_path: str = None):
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p.read_text(encoding="utf-8").splitlines()
    if virt_type in ("Container",):
        return ASCII_ART["container"].strip("\n").splitlines()
    key = distro_id or ""
    if "ubuntu" in key:
        art = ASCII_ART["ubuntu"]
    elif "debian" in key:
        art = ASCII_ART["debian"]
    elif "windows" in key:
        art = ASCII_ART["windows"]
    elif "macos" in key or "darwin" in key:
        art = ASCII_ART["macos"]
    else:
        art = ASCII_ART["generic_linux"]
    return art.strip("\n").splitlines()


# =====================================================================
#  Box ve bo tron + thanh bar + sparkline
# =====================================================================

BOX_TL, BOX_TR, BOX_BL, BOX_BR = "\u256d", "\u256e", "\u2570", "\u256f"
BOX_H, BOX_V = "\u2500", "\u2502"

BLOCKS_V = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"   # 8 muc, dung cho sparkline
BLOCKS_H_FULL = "\u2588"
BLOCKS_H_PARTIAL = " \u258f\u258e\u258d\u258c\u258b\u258a\u2589\u2588"  # 8 muc phu cho thanh bar muot


def sparkline(values, width: int) -> str:
    """Ve bieu do dang song tu danh sach so thuc, do dai = width ky tu."""
    if not values:
        return " " * width
    vals = list(values)[-width:]
    if len(vals) < width:
        vals = [0] * (width - len(vals)) + vals
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    chars = []
    for v in vals:
        idx = int((v - lo) / span * (len(BLOCKS_V) - 1))
        idx = max(0, min(len(BLOCKS_V) - 1, idx))
        chars.append(BLOCKS_V[idx])
    return "".join(chars)


def smooth_bar(percent: float, width: int, color: str = None) -> str:
    """Thanh % muot ma (1/8 buoc) dung block Unicode, khong chi la ky tu don gian."""
    percent = max(0.0, min(100.0, percent))
    total_eighths = int(round(percent / 100.0 * width * 8))
    full_cells, remainder = divmod(total_eighths, 8)
    full_cells = min(full_cells, width)
    bar = BLOCKS_H_FULL * full_cells
    if full_cells < width and remainder > 0:
        bar += BLOCKS_H_PARTIAL[remainder]
        full_cells += 1
    bar += " " * max(0, width - full_cells)
    if color and COLOR_ENABLED:
        return fg(color, bar)
    return bar


def make_panel(title: str, lines, width: int, theme, accent_color=None) -> list:
    """Tra ve list cac dong (str) tao thanh 1 panel bo tron."""
    accent = accent_color or theme["accent"]
    inner_w = width - 2
    title_disp = f" {title} "
    dash_count = max(0, inner_w - visible_len(title_disp) - 1)
    top_line = (fg(accent, BOX_TL) + fg(accent, BOX_H) +
                fg(theme["text"], title_disp, bold=True) +
                fg(accent, BOX_H * dash_count) + fg(accent, BOX_TR))
    out = [top_line]
    for line in lines:
        content = pad_visible(line, inner_w)
        content = truncate_visible(content, inner_w)
        out.append(fg(accent, BOX_V) + content + fg(accent, BOX_V))
    bottom_line = fg(accent, BOX_BL + BOX_H * inner_w + BOX_BR)
    out.append(bottom_line)
    return out


def columns_layout(panels_rendered, gap=1):
    """Ghep nhieu panel (da can bang chieu cao) thanh 1 hang ngang."""
    max_h = max(len(p) for p in panels_rendered)
    out_rows = []
    for i in range(max_h):
        row_parts = []
        for p in panels_rendered:
            if i < len(p):
                row_parts.append(p[i])
            else:
                row_parts.append(" " * visible_len(p[0]))
        out_rows.append((" " * gap).join(row_parts))
    return out_rows


def equalize_height(panels_rendered, accents):
    """Chen dong trong (giua vien) de cac panel cung hang cao bang nhau."""
    max_h = max(len(p) for p in panels_rendered)
    result = []
    for p, accent in zip(panels_rendered, accents):
        if len(p) < max_h:
            width = visible_len(p[0])
            inner_w = width - 2
            blank_row = fg(accent, BOX_V) + " " * inner_w + fg(accent, BOX_V)
            body, bottom = p[:-1], p[-1]
            body = body + [blank_row] * (max_h - len(p))
            p = body + [bottom]
        result.append(p)
    return result


# =====================================================================
#  Thu thap thong tin: OS / Virtualization / Container limits
# =====================================================================

def run_cmd(cmd, timeout=2):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def detect_virtualization():
    """Nhan dien: Physical / Virtual Machine / Container. Khong bao gio raise loi."""
    info = {"type": "May vat ly (Bare-metal)", "engine": None}
    try:
        if IS_LINUX:
            if Path("/.dockerenv").exists():
                return {"type": "Container", "engine": "Docker"}
            try:
                cgroup = Path("/proc/1/cgroup").read_text()
                if "docker" in cgroup:
                    return {"type": "Container", "engine": "Docker"}
                if "lxc" in cgroup:
                    return {"type": "Container", "engine": "LXC"}
                if "kubepods" in cgroup:
                    return {"type": "Container", "engine": "Kubernetes Pod"}
            except Exception:
                pass
            v = run_cmd(["systemd-detect-virt"])
            if v and v != "none":
                if v in ("docker", "lxc", "lxc-libvirt", "podman", "container-other", "oci"):
                    return {"type": "Container", "engine": v}
                return {"type": "May ao (VM)", "engine": v}
        elif IS_WINDOWS:
            out = run_cmd(["wmic", "computersystem", "get", "model"])
            if out:
                for hint in ("Virtual", "VMware", "VirtualBox", "KVM", "Hyper-V"):
                    if hint.lower() in out.lower():
                        return {"type": "May ao (VM)", "engine": hint}
        elif IS_MACOS:
            out = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
            # macOS hiem khi chay trong container/VM theo cach nay; giu Physical
    except Exception:
        pass
    return info


def get_container_limits():
    """Doc gioi han cgroup (v1 & v2) neu dang trong container."""
    limits = {}
    if not IS_LINUX:
        return limits
    try:
        v2_mem = Path("/sys/fs/cgroup/memory.max")
        v1_mem = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if v2_mem.exists():
            val = v2_mem.read_text().strip()
            if val != "max":
                limits["mem_limit"] = int(val)
        elif v1_mem.exists():
            val = int(v1_mem.read_text().strip())
            if val < psutil.virtual_memory().total:
                limits["mem_limit"] = val
    except Exception:
        pass
    try:
        v2_cpu = Path("/sys/fs/cgroup/cpu.max")
        v1_quota = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        v1_period = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if v2_cpu.exists():
            quota, period = v2_cpu.read_text().split()
            if quota != "max":
                limits["cpu_limit_cores"] = round(int(quota) / int(period), 2)
        elif v1_quota.exists() and v1_period.exists():
            quota = int(v1_quota.read_text().strip())
            period = int(v1_period.read_text().strip())
            if quota > 0:
                limits["cpu_limit_cores"] = round(quota / period, 2)
    except Exception:
        pass
    return limits


def get_os_info():
    system = platform.system()
    data = {
        "system": system,
        "kernel": platform.release(),
        "arch": platform.machine(),
        "hostname": socket.gethostname(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
        "distro": system,
        "distro_id": system.lower(),
    }
    if IS_LINUX:
        try:
            os_release = {}
            for line in Path("/etc/os-release").read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    os_release[k] = v.strip('"')
            data["distro"] = os_release.get("PRETTY_NAME", "Linux")
            data["distro_id"] = os_release.get("ID", "linux")
        except Exception:
            data["distro"], data["distro_id"] = "Linux", "linux"
    elif IS_MACOS:
        try:
            ver = platform.mac_ver()[0]
        except Exception:
            ver = ""
        data["distro"] = f"macOS {ver}".strip()
        data["distro_id"] = "macos"
    elif IS_WINDOWS:
        data["distro"] = f"Windows {platform.release()}"
        data["distro_id"] = "windows"
    return data


def get_uptime_str():
    seconds = int(time.time() - psutil.boot_time())
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d} ngay")
    if h or d:
        parts.append(f"{h} gio")
    parts.append(f"{m} phut")
    return " ".join(parts)


# =====================================================================
#  CPU
# =====================================================================

def get_cpu_name():
    if IS_LINUX:
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
    elif IS_WINDOWS:
        name = run_cmd(["wmic", "cpu", "get", "name"])
        if name:
            lines = [l.strip() for l in name.splitlines() if l.strip() and "Name" not in l]
            if lines:
                return lines[0]
    elif IS_MACOS:
        name = run_cmd(["sysctl", "-n", "machdep.cpu.brand_string"])
        if name:
            return name
    name = platform.processor()
    return name if name else "CPU khong xac dinh"


def get_cpu_info(percpu_percent, cpu_limit_cores=None):
    info = {
        "name": get_cpu_name(),
        "cores_physical": psutil.cpu_count(logical=False) or 1,
        "cores_logical": psutil.cpu_count(logical=True) or 1,
        "percent_total": psutil.cpu_percent(percpu=False),
        "percent_percpu": percpu_percent,
        "freq_current": None,
        "freq_percpu": None,
        "cpu_limit_cores": cpu_limit_cores,
    }
    try:
        freq = psutil.cpu_freq()
        if freq:
            info["freq_current"] = freq.current
    except Exception:
        pass
    try:
        freqs = psutil.cpu_freq(percpu=True)
        if freqs:
            info["freq_percpu"] = [f.current for f in freqs]
    except Exception:
        pass
    try:
        t = psutil.cpu_times_percent(percpu=False)
        info["times_percent"] = {
            "user": getattr(t, "user", 0), "system": getattr(t, "system", 0),
            "idle": getattr(t, "idle", 0), "iowait": getattr(t, "iowait", 0),
        }
    except Exception:
        info["times_percent"] = None
    try:
        info["load_avg"] = os.getloadavg() if hasattr(os, "getloadavg") else None
    except Exception:
        info["load_avg"] = None
    return info


# =====================================================================
#  Cam bien: nhiet do CPU/GPU/O cung, quat, dien ap
# =====================================================================

def get_sensors():
    """Tra ve dict: {temps: {...}, fans: {...}, note: str-or-None}"""
    result = {"temps": {}, "fans": {}, "note": None}
    if IS_LINUX:
        try:
            temps = psutil.sensors_temperatures()
            for name, entries in (temps or {}).items():
                for e in entries:
                    label = e.label or name
                    result["temps"][f"{name}:{label}"] = e.current
        except Exception:
            pass
        try:
            fans = psutil.sensors_fans()
            for name, entries in (fans or {}).items():
                for e in entries:
                    label = e.label or name
                    result["fans"][f"{name}:{label}"] = e.current
        except Exception:
            pass
        if not result["temps"] and not result["fans"]:
            result["note"] = "Khong doc duoc sensor (thu: sudo apt install lm-sensors && sudo sensors-detect)"
    elif IS_WINDOWS:
        # Windows khong co API chuan mien phi; can OpenHardwareMonitor/LibreHardwareMonitor + WMI namespace rieng.
        try:
            out = run_cmd([
                "powershell", "-Command",
                "Get-WmiObject -Namespace root/LibreHardwareMonitor -Class Sensor "
                "| Select-Object Name,SensorType,Value | ConvertTo-Json"
            ], timeout=3)
            if out:
                data = json.loads(out)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    stype = item.get("SensorType", "")
                    name = item.get("Name", "?")
                    val = item.get("Value")
                    if stype == "Temperature":
                        result["temps"][name] = val
                    elif stype == "Fan":
                        result["fans"][name] = val
        except Exception:
            pass
        if not result["temps"] and not result["fans"]:
            result["note"] = "Windows can LibreHardwareMonitor dang chay de doc nhiet do/quat"
    elif IS_MACOS:
        result["note"] = "macOS can 'osx-cpu-temp' hoac 'istats' (khong co san trong he thong)"
    return result


# =====================================================================
#  GPU (khong bat buoc cai them thu vien - dung tool CLI co san)
# =====================================================================

def get_gpu_info():
    gpus = []
    nvsmi = shutil.which("nvidia-smi")
    if nvsmi:
        out = run_cmd([
            nvsmi,
            "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,fan.speed,power.draw",
            "--format=csv,noheader,nounits",
        ], timeout=3)
        if out:
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    gpus.append({
                        "vendor": "NVIDIA", "name": parts[0],
                        "temp": _safe_float(parts[1]), "util": _safe_float(parts[2]),
                        "mem_used": _safe_float(parts[3]), "mem_total": _safe_float(parts[4]),
                        "fan": _safe_float(parts[5]), "power": _safe_float(parts[6]),
                    })
    rocmsmi = shutil.which("rocm-smi")
    if rocmsmi and not gpus:
        out = run_cmd([rocmsmi, "--showtemp", "--showuse", "--json"], timeout=3)
        if out:
            try:
                data = json.loads(out)
                for card, vals in data.items():
                    gpus.append({
                        "vendor": "AMD", "name": card,
                        "temp": _safe_float(vals.get("Temperature (Sensor edge) (C)")),
                        "util": _safe_float(vals.get("GPU use (%)")),
                        "mem_used": None, "mem_total": None, "fan": None, "power": None,
                    })
            except Exception:
                pass
    if not gpus and IS_WINDOWS:
        out = run_cmd(["wmic", "path", "win32_VideoController", "get", "name"])
        if out:
            for line in out.splitlines():
                line = line.strip()
                if line and "Name" not in line:
                    gpus.append({"vendor": "?", "name": line, "temp": None, "util": None,
                                 "mem_used": None, "mem_total": None, "fan": None, "power": None})
    if not gpus and IS_MACOS:
        out = run_cmd(["system_profiler", "SPDisplaysDataType"])
        if out:
            for line in out.splitlines():
                if "Chipset Model" in line:
                    gpus.append({"vendor": "Apple/?", "name": line.split(":", 1)[1].strip(),
                                 "temp": None, "util": None, "mem_used": None,
                                 "mem_total": None, "fan": None, "power": None})
    return gpus


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# =====================================================================
#  RAM & Swap
# =====================================================================

def get_ram_speed_mts():
    """Toc do bus RAM (MT/s) - chi Linux + can quyen root de dmidecode."""
    if not IS_LINUX:
        return None
    dmidecode = shutil.which("dmidecode")
    if not dmidecode:
        return None
    out = run_cmd(["dmidecode", "-t", "memory"], timeout=3)
    if not out:
        return None
    speeds = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Speed:") and "Unknown" not in line:
            m = re.search(r"(\d+)\s*MT/s", line)
            if m:
                speeds.append(int(m.group(1)))
    return max(speeds) if speeds else None


def get_memory_info(mem_limit_container=None):
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    total = mem_limit_container if mem_limit_container else vm.total
    used = min(vm.used, total) if mem_limit_container else vm.used
    return {
        "total": total, "used": used, "available": vm.available,
        "cached": getattr(vm, "cached", 0), "buffers": getattr(vm, "buffers", 0),
        "percent": (used / total * 100) if total else 0,
        "swap_total": sw.total, "swap_used": sw.used, "swap_percent": sw.percent,
        "is_container_limited": bool(mem_limit_container),
    }


# =====================================================================
#  Disk / Storage / I/O realtime
# =====================================================================

def get_disk_partitions():
    parts = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
        except Exception:
            continue
        parts.append({
            "device": p.device, "mountpoint": p.mountpoint, "fstype": p.fstype,
            "total": usage.total, "used": usage.used, "free": usage.free,
            "percent": usage.percent,
        })
    return parts


def get_disk_io_delta(prev_io, dt):
    """Tinh toc do doc/ghi (bytes/s) tu 2 lan do disk_io_counters(perdisk=True)."""
    speeds = {}
    try:
        cur_io = psutil.disk_io_counters(perdisk=True)
    except Exception:
        return {}, prev_io
    if prev_io and dt > 0:
        for disk, cur in cur_io.items():
            prev = prev_io.get(disk)
            if prev:
                read_bps = max(0, (cur.read_bytes - prev.read_bytes) / dt)
                write_bps = max(0, (cur.write_bytes - prev.write_bytes) / dt)
                speeds[disk] = {"read_bps": read_bps, "write_bps": write_bps}
    return speeds, cur_io


def get_disk_temps(sensors_temps):
    """lm-sensors thuong tra nvme/drivetemp voi ten dang 'nvme-...:Composite'."""
    disk_temps = {}
    for key, val in sensors_temps.items():
        low = key.lower()
        if "nvme" in low or "drivetemp" in low or "hdd" in low:
            disk_temps[key] = val
    return disk_temps


# =====================================================================
#  Network: toc do realtime + LICH SU bang thong (session & hom nay)
# =====================================================================

class NetHistory:
    """Ghi lich su bang thong: giu trong RAM (session, sparkline) va ghi
    log ra dia (~/.sysinfo_pro/netlog/YYYY-MM-DD.csv) de tinh TONG hom nay,
    thay vi chi do tuc thoi nhu neofetch."""

    def __init__(self, max_points=120, flush_every_n=5):
        self.down_hist = deque(maxlen=max_points)
        self.up_hist = deque(maxlen=max_points)
        self.session_down_bytes = 0
        self.session_up_bytes = 0
        self._prev = None
        self._prev_t = None
        self._tick = 0
        self.flush_every_n = flush_every_n
        self.today_file = NET_LOG_DIR / f"{date.today().isoformat()}.csv"
        self.today_total_down, self.today_total_up = self._load_today_totals()

    def _load_today_totals(self):
        d, u = 0, 0
        if self.today_file.exists():
            try:
                last = self.today_file.read_text().strip().splitlines()[-1]
                _, d, u = last.split(",")
                d, u = int(d), int(u)
            except Exception:
                d, u = 0, 0
        return d, u

    def sample(self):
        try:
            cur = psutil.net_io_counters()
        except Exception:
            return 0.0, 0.0
        now = time.time()
        down_bps, up_bps = 0.0, 0.0
        if self._prev is not None:
            dt = max(0.001, now - self._prev_t)
            down_bps = max(0, (cur.bytes_recv - self._prev.bytes_recv) / dt)
            up_bps = max(0, (cur.bytes_sent - self._prev.bytes_sent) / dt)
            self.session_down_bytes += max(0, cur.bytes_recv - self._prev.bytes_recv)
            self.session_up_bytes += max(0, cur.bytes_sent - self._prev.bytes_sent)
        self._prev = cur
        self._prev_t = now
        self.down_hist.append(down_bps)
        self.up_hist.append(up_bps)
        self._tick += 1
        if self._tick % self.flush_every_n == 0:
            self._flush()
        return down_bps, up_bps

    def _flush(self):
        try:
            total_d = self.today_total_down + self.session_down_bytes
            total_u = self.today_total_up + self.session_up_bytes
            with open(self.today_file, "a") as f:
                f.write(f"{int(time.time())},{total_d},{total_u}\n")
        except Exception:
            pass

    def today_totals(self):
        return (self.today_total_down + self.session_down_bytes,
                self.today_total_up + self.session_up_bytes)


def get_network_interfaces():
    ifaces = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception:
        return ifaces
    for name, addr_list in addrs.items():
        if name.startswith("lo") or name == "Loopback Pseudo-Interface 1":
            continue
        is_up = stats.get(name).isup if name in stats else False
        ipv4 = next((a.address for a in addr_list if a.family == socket.AF_INET), None)
        if ipv4:
            ifaces.append({"name": name, "ip": ipv4, "is_up": is_up})
    return ifaces


def get_public_ip(timeout=1.5):
    """Chi goi khi nguoi dung bat --public-ip (can Internet)."""
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return r.read().decode().strip()
    except Exception:
        return None


# =====================================================================
#  Processes
# =====================================================================

def get_top_processes(n=6, sort_by="cpu"):
    procs = []
    for p in psutil.process_iter(["pid", "name", "username"]):
        try:
            cpu = p.cpu_percent(interval=None)
            mem = p.memory_percent()
            procs.append({"pid": p.pid, "name": p.info.get("name") or "?",
                          "cpu": cpu, "mem": mem})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    key = "cpu" if sort_by == "cpu" else "mem"
    procs.sort(key=lambda x: x[key], reverse=True)
    total_procs = len(procs)
    running = sum(1 for p in psutil.pids())
    return procs[:n], total_procs


# =====================================================================
#  Helpers dinh dang
# =====================================================================

def human_bytes(n, per_sec=False):
    if n is None:
        return "N/A"
    n = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(n) < 1024.0:
            s = f"{n:.1f}{unit}"
            return s + "/s" if per_sec else s
        n /= 1024.0
    return f"{n:.1f}EB"


def human_temp(c):
    if c is None:
        return "N/A"
    return f"{c:.0f}\u00b0C"


# =====================================================================
#  Ban phim (khong khoa terminal, cross-platform) - cho Interactive mode
# =====================================================================

class KeyListener(threading.Thread):
    """Doc phim khong dong (non-blocking) tren rieng 1 thread, day vao queue."""

    def __init__(self, key_queue: queue.Queue):
        super().__init__(daemon=True)
        self.key_queue = key_queue
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        if IS_WINDOWS:
            self._run_windows()
        else:
            self._run_unix()

    def _run_windows(self):
        try:
            import msvcrt
        except ImportError:
            return
        while not self._stop.is_set():
            if msvcrt.kbhit():
                try:
                    ch = msvcrt.getch().decode(errors="ignore")
                    self.key_queue.put(ch)
                except Exception:
                    pass
            time.sleep(0.05)

    def _run_unix(self):
        try:
            import termios
            import tty
            import select
        except ImportError:
            return
        if not sys.stdin.isatty():
            return
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not self._stop.is_set():
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if r:
                    ch = sys.stdin.read(1)
                    self.key_queue.put(ch)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def kill_process_by_pid(pid: int) -> str:
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.terminate()
        try:
            p.wait(timeout=2)
        except psutil.TimeoutExpired:
            p.kill()
        return f"Da terminate PID {pid} ({name})"
    except psutil.NoSuchProcess:
        return f"Khong tim thay PID {pid}"
    except psutil.AccessDenied:
        return f"Khong co quyen kill PID {pid} (thu chay lai voi sudo/Administrator)"
    except Exception as e:
        return f"Loi: {e}"


# =====================================================================
#  App state (giu du lieu giua cac lan refresh)
# =====================================================================

class AppState:
    def __init__(self, theme, top_n=6, sort_by="cpu"):
        self.theme = theme
        self.top_n = top_n
        self.sort_by = sort_by
        self.prev_disk_io = None
        self.net_hist = NetHistory()
        self.cpu_hist = deque(maxlen=60)
        self.ram_hist = deque(maxlen=60)
        self.status_msg = ""
        self.status_until = 0
        self.paused = False
        self.interval = 1.5
        self.virt = detect_virtualization()
        self.container_limits = get_container_limits()
        self.os_info = get_os_info()
        self.kill_input_mode = False
        self.kill_input_buf = ""

    def set_status(self, msg, secs=4):
        self.status_msg = msg
        self.status_until = time.time() + secs


# =====================================================================
#  Xay dung tung panel
# =====================================================================

def panel_header(state: AppState, width_total: int):
    theme = state.theme
    os_info = state.os_info
    art_lines = get_ascii_art(os_info["distro_id"], state.virt["type"].split()[0] if state.virt["type"] != "May vat ly (Bare-metal)" else "", theme.get("ascii_art"))
    art_w = max((visible_len(l) for l in art_lines), default=0) + 2

    info_lines = [
        fg(theme["accent2"], f"{state.os_info['user']}", bold=True) + fg(theme["muted"], "@") + fg(theme["accent2"], state.os_info["hostname"]),
        fg(theme["muted"], "-" * 20),
        f"{fg(theme['accent'], 'He dieu hanh', bold=True)}  : {os_info['distro']}",
        f"{fg(theme['accent'], 'Kernel', bold=True)}       : {os_info['kernel']}",
        f"{fg(theme['accent'], 'Kien truc', bold=True)}    : {os_info['arch']}",
        f"{fg(theme['accent'], 'Uptime', bold=True)}       : {get_uptime_str()}",
        f"{fg(theme['accent'], 'May / Container', bold=True)} : {state.virt['type']}" + (f" ({state.virt['engine']})" if state.virt.get("engine") else ""),
    ]
    if state.container_limits.get("mem_limit"):
        info_lines.append(f"{fg(theme['warn'], 'RAM gioi han', bold=True)} : {human_bytes(state.container_limits['mem_limit'])} (container)")
    if state.container_limits.get("cpu_limit_cores"):
        info_lines.append(f"{fg(theme['warn'], 'CPU gioi han', bold=True)} : {state.container_limits['cpu_limit_cores']} core (container)")
    info_lines.append(f"{fg(theme['accent'], 'Gio he thong', bold=True)}  : {datetime.now().strftime('%H:%M:%S  %d/%m/%Y')}")

    max_h = max(len(art_lines), len(info_lines)) + 2
    art_block = [fg(theme["accent2"], l) for l in art_lines] + [""] * (max_h - len(art_lines))
    info_block = info_lines + [""] * (max_h - len(info_lines))

    lines = []
    for a, b in zip(art_block, info_block):
        lines.append(pad_visible(a, art_w) + " " + b)
    return make_panel("SYSINFO PRO  •  " + os_info["distro"], lines, width_total, theme, theme["accent2"])


def panel_cpu(state: AppState, cpu_info: dict, width: int):
    theme = state.theme
    lines = [
        truncate_visible(cpu_info["name"], width - 4),
        f"Nhan/Luong: {cpu_info['cores_physical']}C / {cpu_info['cores_logical']}T" +
        (f"   (gioi han container: {cpu_info['cpu_limit_cores']} core)" if cpu_info.get("cpu_limit_cores") else ""),
    ]
    if cpu_info.get("freq_current"):
        lines.append(f"Xung nhip hien tai: {cpu_info['freq_current']:.0f} MHz")
    total_pct = cpu_info["percent_total"]
    color = level_color(theme, total_pct)
    lines.append(f"Tong dung: {smooth_bar(total_pct, 24, color)} {total_pct:5.1f}%")

    tp = cpu_info.get("times_percent")
    if tp:
        lines.append(fg(theme["muted"], f"User {tp['user']:.0f}% | Sys {tp['system']:.0f}% | Idle {tp['idle']:.0f}% | IO-wait {tp['iowait']:.0f}%"))

    percpu = cpu_info.get("percent_percpu") or []
    freqs = cpu_info.get("freq_percpu") or []
    for i, pct in enumerate(percpu[:8]):
        c = level_color(theme, pct)
        f_str = f" {freqs[i]:.0f}MHz" if i < len(freqs) else ""
        lines.append(f"Core{i:<2}: {smooth_bar(pct, 14, c)} {pct:5.1f}%{f_str}")
    if len(percpu) > 8:
        lines.append(fg(theme["muted"], f"... va {len(percpu)-8} core khac"))

    # nhiet do CPU tu sensors (loc tu ten co 'core' / 'package' / 'cpu')
    return lines


def panel_sensors(state: AppState, sensors: dict, disk_temps: dict, width: int):
    theme = state.theme
    lines = []
    cpu_temps = {k: v for k, v in sensors["temps"].items() if k not in disk_temps}
    if cpu_temps:
        for k, v in list(cpu_temps.items())[:6]:
            label = k.split(":")[-1][:22]
            c = theme["crit"] if v and v >= 85 else (theme["warn"] if v and v >= 70 else theme["ok"])
            lines.append(f"{label:<22} {fg(c, human_temp(v))}")
    if disk_temps:
        for k, v in disk_temps.items():
            label = ("O cung " + k.split(":")[-1])[:22]
            c = theme["crit"] if v and v >= 60 else (theme["warn"] if v and v >= 50 else theme["ok"])
            lines.append(f"{label:<22} {fg(c, human_temp(v))}")
    if sensors["fans"]:
        for k, v in list(sensors["fans"].items())[:4]:
            label = ("Quat " + k.split(":")[-1])[:22]
            lines.append(f"{label:<22} {v:.0f} RPM")
    if not lines:
        lines.append(fg(theme["muted"], sensors.get("note") or "Khong co du lieu sensor"))
    return lines


def panel_memory(state: AppState, mem: dict, width: int):
    theme = state.theme
    c = level_color(theme, mem["percent"])
    lines = [
        f"RAM:  {smooth_bar(mem['percent'], 26, c)} {mem['percent']:5.1f}%",
        f"      {human_bytes(mem['used'])} / {human_bytes(mem['total'])}" + ("  [container]" if mem["is_container_limited"] else ""),
        f"Available: {human_bytes(mem['available'])}   Cached: {human_bytes(mem['cached'])}   Buffers: {human_bytes(mem['buffers'])}",
    ]
    ram_speed = getattr(state, "_ram_speed_cache", None)
    if ram_speed:
        lines.append(f"Toc do bus RAM: {ram_speed} MT/s")
    if mem["swap_total"] > 0:
        sc = level_color(theme, mem["swap_percent"])
        lines.append(f"Swap: {smooth_bar(mem['swap_percent'], 26, sc)} {mem['swap_percent']:5.1f}%  ({human_bytes(mem['swap_used'])}/{human_bytes(mem['swap_total'])})")
    else:
        lines.append(fg(theme["muted"], "Swap: khong co / 0B"))
    state.ram_hist.append(mem["percent"])
    lines.append("Lich su (60 mau gan nhat): " + fg(theme["accent2"], sparkline(state.ram_hist, min(40, width - 30))))
    return lines


def panel_disks(state: AppState, parts, io_speeds, sensors, width: int):
    theme = state.theme
    lines = []
    disk_temps = get_disk_temps(sensors["temps"])
    for p in parts[:6]:
        c = level_color(theme, p["percent"])
        mnt = p["mountpoint"]
        if len(mnt) > 18:
            mnt = mnt[:15] + "..."
        lines.append(f"{mnt:<18} {smooth_bar(p['percent'], 16, c)} {p['percent']:4.0f}%  {human_bytes(p['free'])} trong / {human_bytes(p['total'])}")
    if len(parts) > 6:
        lines.append(fg(theme["muted"], f"... va {len(parts)-6} phan vung khac"))
    lines.append(fg(theme["muted"], "-" * min(40, width - 4)))
    if io_speeds:
        for disk, sp in list(io_speeds.items())[:4]:
            lines.append(f"{disk:<10} Doc {human_bytes(sp['read_bps'], True):>10}   Ghi {human_bytes(sp['write_bps'], True):>10}")
    else:
        lines.append(fg(theme["muted"], "Dang do toc do I/O..."))
    if disk_temps:
        for k, v in disk_temps.items():
            lines.append(f"Nhiet do {k.split(':')[-1]}: {human_temp(v)}")
    return lines


def panel_network(state: AppState, ifaces, down_bps, up_bps, width: int):
    theme = state.theme
    lines = []
    for iface in ifaces[:4]:
        status = fg(theme["ok"], "UP") if iface["is_up"] else fg(theme["muted"], "DOWN")
        lines.append(f"{iface['name']:<12} {iface['ip']:<16} [{status}]")
    lines.append(fg(theme["muted"], "-" * min(40, width - 4)))
    lines.append(f"Download: {fg(theme['ok'], human_bytes(down_bps, True))}   " + sparkline(state.net_hist.down_hist, min(30, width - 34)))
    lines.append(f"Upload:   {fg(theme['accent2'], human_bytes(up_bps, True))}   " + sparkline(state.net_hist.up_hist, min(30, width - 34)))
    td, tu = state.net_hist.today_totals()
    lines.append(f"Da dung hom nay: {fg(theme['accent'], 'Down ' + human_bytes(td))}  /  {fg(theme['accent2'], 'Up ' + human_bytes(tu))}")
    lines.append(f"Da dung phien nay: Down {human_bytes(state.net_hist.session_down_bytes)} / Up {human_bytes(state.net_hist.session_up_bytes)}")
    return lines


def panel_gpu(state: AppState, gpus, width: int):
    theme = state.theme
    if not gpus:
        return [fg(theme["muted"], "Khong tim thay GPU (hoac khong co driver CLI: nvidia-smi/rocm-smi)")]
    lines = []
    for g in gpus:
        lines.append(f"{g['vendor']:<7} {truncate_visible(g['name'], width - 12)}")
        if g["util"] is not None:
            c = level_color(theme, g["util"])
            lines.append(f"  Su dung: {smooth_bar(g['util'], 18, c)} {g['util']:4.0f}%")
        if g["mem_used"] is not None and g["mem_total"]:
            mp = g["mem_used"] / g["mem_total"] * 100
            c2 = level_color(theme, mp)
            lines.append(f"  VRAM: {smooth_bar(mp, 18, c2)} {g['mem_used']:.0f}/{g['mem_total']:.0f} MiB")
        extras = []
        if g["temp"] is not None:
            extras.append(f"Nhiet: {human_temp(g['temp'])}")
        if g["fan"] is not None:
            extras.append(f"Quat: {g['fan']:.0f}%")
        if g["power"] is not None:
            extras.append(f"Cong suat: {g['power']:.0f}W")
        if extras:
            lines.append("  " + "  ".join(extras))
    return lines


def panel_processes(state: AppState, procs, total_procs, width: int):
    theme = state.theme
    sort_label = "CPU" if state.sort_by == "cpu" else "RAM"
    lines = [fg(theme["muted"], f"Tong tien trinh: {total_procs}   (sap xep theo {sort_label} - nhan 'p' de doi)")]
    lines.append(f"{'PID':<8}{'Ten':<22}{'CPU%':>7}{'MEM%':>7}")
    for p in procs:
        lines.append(f"{p['pid']:<8}{truncate_visible(p['name'], 21):<22}{p['cpu']:>7.1f}{p['mem']:>7.1f}")
    if state.kill_input_mode:
        lines.append(fg(theme["warn"], f"Nhap PID de KILL: {state.kill_input_buf}_  (Enter=xac nhan, Esc=huy)"))
    return lines


# =====================================================================
#  Ghep toan bo panel thanh 1 khung hinh (frame)
# =====================================================================

HELP_TEXT = (
    "[q] Thoat  [p] Doi sort CPU/RAM  [+/-] Toc do refresh  "
    "[k] Kill process  [t] Doi theme  [s] Luu snapshot JSON  [space] Pause"
)


def collect_all(state: AppState, tick: int):
    theme = state.theme
    term_w, term_h = shutil.get_terminal_size(fallback=(120, 40))
    term_w = max(70, term_w)

    percpu_pct = psutil.cpu_percent(percpu=True)
    if not percpu_pct:
        percpu_pct = [psutil.cpu_percent()]
    state.cpu_hist.append(sum(percpu_pct) / len(percpu_pct))

    cpu_info = get_cpu_info(percpu_pct, state.container_limits.get("cpu_limit_cores"))
    mem_info = get_memory_info(state.container_limits.get("mem_limit"))
    sensors = get_sensors()
    parts = get_disk_partitions()
    io_speeds, state.prev_disk_io = get_disk_io_delta(state.prev_disk_io, state.interval)
    down_bps, up_bps = state.net_hist.sample()
    ifaces = get_network_interfaces()
    gpus = get_gpu_info() if tick % 2 == 0 else getattr(state, "_gpu_cache", [])
    state._gpu_cache = gpus
    if tick % 20 == 0 or not hasattr(state, "_ram_speed_cache"):
        state._ram_speed_cache = get_ram_speed_mts()
    procs, total_procs = get_top_processes(state.top_n, state.sort_by)

    return {
        "term_w": term_w, "term_h": term_h,
        "cpu_info": cpu_info, "mem_info": mem_info, "sensors": sensors,
        "parts": parts, "io_speeds": io_speeds, "down_bps": down_bps, "up_bps": up_bps,
        "ifaces": ifaces, "gpus": gpus, "procs": procs, "total_procs": total_procs,
    }


def build_frame(state: AppState, data: dict) -> str:
    theme = state.theme
    term_w = data["term_w"]
    full_w = min(term_w - 1, 118)
    half_w = (full_w - 1) // 2

    out = []
    out.append("\n".join(panel_header(state, full_w)))

    cpu_panel = make_panel("CPU", panel_cpu(state, data["cpu_info"], half_w), half_w, theme)
    sens_panel = make_panel("CAM BIEN (Sensors)", panel_sensors(state, data["sensors"], get_disk_temps(data["sensors"]["temps"]), half_w), half_w, theme)
    cpu_panel, sens_panel = equalize_height([cpu_panel, sens_panel], [theme["accent"], theme["accent"]])
    out.extend(columns_layout([cpu_panel, sens_panel]))

    mem_panel = make_panel("RAM / SWAP", panel_memory(state, data["mem_info"], half_w), half_w, theme)
    gpu_panel = make_panel("GPU", panel_gpu(state, data["gpus"], half_w), half_w, theme)
    mem_panel, gpu_panel = equalize_height([mem_panel, gpu_panel], [theme["accent"], theme["accent"]])
    out.extend(columns_layout([mem_panel, gpu_panel]))

    disk_panel = make_panel("O CUNG / STORAGE / I-O", panel_disks(state, data["parts"], data["io_speeds"], data["sensors"], half_w), half_w, theme)
    net_panel = make_panel("MANG (Network)", panel_network(state, data["ifaces"], data["down_bps"], data["up_bps"], half_w), half_w, theme)
    disk_panel, net_panel = equalize_height([disk_panel, net_panel], [theme["accent"], theme["accent"]])
    out.extend(columns_layout([disk_panel, net_panel]))

    proc_panel = make_panel("TIEN TRINH (Processes)", panel_processes(state, data["procs"], data["total_procs"], full_w), full_w, theme)
    out.extend(proc_panel)

    status = state.status_msg if time.time() < state.status_until else HELP_TEXT
    out.append(fg(theme["muted"], truncate_visible(status, full_w)))
    return "\n".join(out)


# =====================================================================
#  Xuat snapshot JSON (cho script/monitoring khac doc lai)
# =====================================================================

def export_snapshot_json(state: AppState, data: dict, path: str):
    snap = {
        "timestamp": datetime.now().isoformat(),
        "os": state.os_info,
        "virtualization": state.virt,
        "container_limits": state.container_limits,
        "cpu": {k: v for k, v in data["cpu_info"].items() if k != "freq_percpu"},
        "memory": data["mem_info"],
        "sensors": data["sensors"],
        "disks": data["parts"],
        "disk_io": data["io_speeds"],
        "network": {"down_bps": data["down_bps"], "up_bps": data["up_bps"],
                    "today_totals": state.net_hist.today_totals()},
        "gpus": data["gpus"],
        "top_processes": data["procs"],
    }
    Path(path).write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")


# =====================================================================
#  Main loop
# =====================================================================

THEME_PRESETS = ["aurora", "matrix", "sunset", "mono"]

THEME_COLORS = {
    "aurora": {"accent": "#7DD3FC", "accent2": "#C084FC", "ok": "#4ADE80", "warn": "#FACC15", "crit": "#F87171", "text": "#E5E7EB", "muted": "#6B7280"},
    "matrix": {"accent": "#22C55E", "accent2": "#86EFAC", "ok": "#22C55E", "warn": "#EAB308", "crit": "#EF4444", "text": "#D1FAE5", "muted": "#4B5563"},
    "sunset": {"accent": "#FB923C", "accent2": "#F472B6", "ok": "#34D399", "warn": "#FBBF24", "crit": "#F43F5E", "text": "#FFF7ED", "muted": "#78716C"},
    "mono": {"accent": "#E5E7EB", "accent2": "#9CA3AF", "ok": "#D1D5DB", "warn": "#9CA3AF", "crit": "#F87171", "text": "#F3F4F6", "muted": "#6B7280"},
}


def apply_theme_preset(theme, preset_name):
    if preset_name in THEME_COLORS:
        theme.update(THEME_COLORS[preset_name])
        theme["name"] = preset_name
    return theme


def main():
    global COLOR_ENABLED
    parser = argparse.ArgumentParser(
        description="SysInfo Pro - neofetch tren steroid: real-time, interactive, sensors sau, mang co lich su."
    )
    parser.add_argument("--once", action="store_true", help="Chi in 1 lan (snapshot) roi thoat, khong live-refresh")
    parser.add_argument("--interval", type=float, default=1.5, help="Chu ky refresh (giay), mac dinh 1.5s")
    parser.add_argument("--theme", type=str, default=None, help="Duong dan file theme.json, hoac ten preset: aurora/matrix/sunset/mono")
    parser.add_argument("--no-color", action="store_true", help="Tat mau (dung cho terminal khong ho tro TrueColor)")
    parser.add_argument("--top", type=int, default=6, help="So tien trinh top hien thi, mac dinh 6")
    parser.add_argument("--sort", choices=["cpu", "mem"], default="cpu", help="Sap xep tien trinh theo cpu hoac mem")
    parser.add_argument("--export", type=str, default=None, help="Xuat 1 snapshot JSON ra duong dan chi dinh roi thoat")
    parser.add_argument("--no-interactive", action="store_true", help="Tat che do doc phim (dung khi chay trong pipe/log)")
    args = parser.parse_args()

    COLOR_ENABLED = supports_truecolor() and not args.no_color
    save_default_theme_if_missing()

    if args.theme in THEME_PRESETS:
        theme = load_theme(None)
        theme = apply_theme_preset(theme, args.theme)
    else:
        theme = load_theme(args.theme)

    state = AppState(theme, top_n=args.top, sort_by=args.sort)
    state.interval = args.interval

    if args.export:
        data = collect_all(state, 0)
        export_snapshot_json(state, data, args.export)
        print(f"Da xuat snapshot: {args.export}")
        return

    if args.once:
        data = collect_all(state, 0)
        print(build_frame(state, data))
        return

    # ---- Live mode ----
    key_q = queue.Queue()
    listener = None
    if not args.no_interactive:
        listener = KeyListener(key_q)
        listener.start()

    _restored = {"done": False}

    def restore_terminal(*_):
        if _restored["done"]:
            sys.exit(0)
        _restored["done"] = True
        sys.stdout.write(SHOW_CURSOR + ALT_SCREEN_OFF)
        sys.stdout.flush()
        if listener:
            listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, restore_terminal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, restore_terminal)

    sys.stdout.write(ALT_SCREEN_ON + HIDE_CURSOR)
    tick = 0
    theme_idx = THEME_PRESETS.index(theme.get("name")) if theme.get("name") in THEME_PRESETS else 0
    try:
        while True:
            if not state.paused:
                data = collect_all(state, tick)
                frame = build_frame(state, data)
                sys.stdout.write(CLEAR_HOME + frame + "\n")
                sys.stdout.flush()
                tick += 1

            # xu ly phim trong khoang thoi gian ngu (khong chan luong)
            t_end = time.time() + state.interval
            while time.time() < t_end:
                try:
                    ch = key_q.get(timeout=max(0.01, t_end - time.time()))
                except queue.Empty:
                    break
                if state.kill_input_mode:
                    if ch in ("\r", "\n"):
                        if state.kill_input_buf.isdigit():
                            msg = kill_process_by_pid(int(state.kill_input_buf))
                            state.set_status(msg)
                        state.kill_input_mode = False
                        state.kill_input_buf = ""
                    elif ch == "\x1b":
                        state.kill_input_mode = False
                        state.kill_input_buf = ""
                    elif ch in ("\x7f", "\b"):
                        state.kill_input_buf = state.kill_input_buf[:-1]
                    elif ch.isdigit():
                        state.kill_input_buf += ch
                    continue
                if ch in ("q", "Q"):
                    restore_terminal()
                elif ch in ("p", "P"):
                    state.sort_by = "mem" if state.sort_by == "cpu" else "cpu"
                elif ch == "+":
                    state.interval = min(10.0, state.interval + 0.5)
                    state.set_status(f"Refresh moi {state.interval:.1f}s")
                elif ch == "-":
                    state.interval = max(0.5, state.interval - 0.5)
                    state.set_status(f"Refresh moi {state.interval:.1f}s")
                elif ch in ("k", "K"):
                    state.kill_input_mode = True
                    state.kill_input_buf = ""
                elif ch in ("t", "T"):
                    theme_idx = (theme_idx + 1) % len(THEME_PRESETS)
                    apply_theme_preset(state.theme, THEME_PRESETS[theme_idx])
                    state.set_status(f"Theme: {THEME_PRESETS[theme_idx]}")
                elif ch in ("s", "S"):
                    out_path = str(APP_DIR / f"snapshot_{int(time.time())}.json")
                    export_snapshot_json(state, data, out_path)
                    state.set_status(f"Da luu snapshot: {out_path}")
                elif ch == " ":
                    state.paused = not state.paused
                    state.set_status("Da PAUSE" if state.paused else "Tiep tuc")
    finally:
        restore_terminal()


if __name__ == "__main__":
    main()