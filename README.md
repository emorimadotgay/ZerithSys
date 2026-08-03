<p align="center">
  <img src="https://i.postimg.cc/jjSyjZDT/Zerith-Sys-removebg-preview.png" alt="ZerithSys" height="180px">
</p>

<h3 align="center">ZerithSys</h3>

<p align="center">
  System monitor for Linux, macOS and Windows. CPU, RAM, GPU, disk, network, sensors and processes in one terminal dashboard.
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.8+-blue.svg"></a>
</p>

<img src="https://i.postimg.cc/YC9SGVz4/Screenshot-2026-08-03-072655.png" align="right" height="220px">

## Install

Linux / macOS:
```bash
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash
```

Windows (PowerShell):
```powershell
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex
```

Then run `zerithsys`.

## Keys

`q` quit · `t` switch theme · `r` refresh · `c` sort by CPU · `s` sort by RAM · `k` kill process · `↑↓` move

## Themes

`tokyo-night` (default), `dracula`, `nord`, `gruvbox`. Pass one with `--theme`.

## Panels

OS (distro logo, kernel, uptime, container/VM info) · CPU (per-core, freq, temp, fan, history) · Memory (RAM, swap, bus speed) · GPU (VRAM, load, temp, fan) · Storage (partitions, I/O, SMART temp) · Network (IPs, WAN, live up/down) · Processes (sortable, killable)

## Optional

Install any of these for more data: `nvidia-smi` (NVIDIA GPU), `rocm-smi` (AMD GPU), `smartmontools` (disk temp), `lm-sensors` (more CPU temps). All optional — ZerithSys works without them.

## Update / Uninstall

```bash
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.sh | bash -s -- --update
curl -sSL https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/install.ps1 | iex -Args @('--Update')
irm https://raw.githubusercontent.com/zerithsys/zerithsys/main/uninstall.ps1 | iex
```

## Requirements

Python 3.8+. ~30 MB. Works on Windows 10+, Debian 10+, Ubuntu 18.04+, Arch, Fedora 30+, macOS, Alpine.

## License

MIT
