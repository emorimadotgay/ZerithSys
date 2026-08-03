# ZerithSys

> A modern, real-time system monitor — what `neofetch` should have been.

Cross-platform TUI dashboard with deep hardware inspection, network traffic
history, container/VM awareness, and four built-in TrueColor themes.

---

## One-line install

### Debian / Ubuntu / Arch / Fedora / macOS

```bash
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex
```

That's it. Run `zerithsys` from any terminal.

### From PyPI

```bash
pip install --user zerithsys
```

### From source

```bash
git clone https://github.com/zerithsys/zerithsys
cd zerithsys
pip install --user .
zerithsys
```

---

## Usage

```bash
zerithsys                    # launch with default Tokyo Night theme
zerithsys --theme dracula    # Dracula palette
zerithsys --theme nord       # Nord palette
zerithsys --theme gruvbox    # Gruvbox palette
```

### Keyboard

| Key | Action              |
|-----|---------------------|
| `q` | Quit                |
| `t` | Cycle theme         |
| `r` | Force refresh       |
| `c` | Sort by CPU         |
| `s` | Sort by memory      |
| `k` | Kill selected PID   |
| `↑↓` | Navigate processes |

### Mouse

- scroll inside the dashboard
- click a process row to focus it, then press `k` to kill

---

## Features

| Area            | What's shown                                                 |
|-----------------|--------------------------------------------------------------|
| **Header**      | distro ASCII art, OS, kernel, uptime, host, user, arch       |
| **CPU**         | per-core usage, frequency, temperature, sparkline, fan RPM   |
| **Memory**      | RAM / swap with cached, bus speed (MT/s), 60-sample history  |
| **GPU**         | NVIDIA / AMD / Intel — VRAM, load, temperature, fan %        |
| **Storage**     | mount points, free / total, R/W speed, SMART disk temps      |
| **Network**     | IPv4 / IPv6 / MAC, WAN IP, live ↓/↑ speed, session totals    |
| **Processes**   | top-20 by CPU or memory, running / sleeping count            |

### Auto-detect & fallback

- Detects Linux (Debian / Ubuntu / Arch / Fedora), macOS and Windows
- Reads CPU temps from `psutil.sensors_temperatures()` (coretemp / k10temp / zenpower / acpitz …)
- Reads GPU data from `nvidia-smi` / `rocm-smi` when present, otherwise Intel iGPU basic
- Reads SMART disk temps via `smartctl` (Linux only)
- Detects container runtime (Docker, LXC) and hypervisor (QEMU, VMware, VirtualBox, Hyper-V, Xen)

### Performance

- All system calls run on a background thread — the UI never blocks
- GPU / SMART data cached for 30 s (rarely changes)
- Panel refreshes are staggered: 2 / 2.5 / 3 / 4 / 5 / 10 s
- Process iteration cached for 5 s

---

## Update / Uninstall

### Update

```bash
# Linux / macOS
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash -s -- --update
```

```powershell
# Windows
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex -Args @('--Update')
```

### Uninstall

```bash
# Linux / macOS
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.sh | bash
```

```powershell
# Windows
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.ps1 | iex
```

---

## Requirements

- Python ≥ 3.8
- ~30 MB disk space
- Windows: Windows 10+
- Linux: any modern distro (Debian 10+, Ubuntu 18.04+, Arch, Fedora 30+, Alpine)

Optional (for extra sensors):
- `nvidia-smi` for NVIDIA GPU telemetry
- `rocm-smi` for AMD GPU telemetry
- `smartctl` (smartmontools) for SMART disk temperatures
- `sudo` for RAM bus speed (Linux)

---

## File map

```
zerithsys/
├── main.py                 ← Textual app entry point
├── app.tcss                ← stylesheet
├── pyproject.toml          ← pip-installable package definition
├── install.sh              ← Linux / macOS installer
├── install.ps1             ← Windows installer
├── uninstall.sh            ← Linux / macOS uninstaller
├── uninstall.ps1           ← Windows uninstaller
├── requirements.txt        ← pip dependency list
├── README.md
└── modules/
    ├── __init__.py
    ├── ascii_art.py        ← per-distro logos
    └── data_collector.py   ← background-threaded data collection
```

---

## License

MIT
