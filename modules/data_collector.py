"""
data_collector.py  –  Cross-platform system data collection for ZerithSys.
Supports Linux (Debian / Ubuntu) and Windows; graceful no-op on missing APIs.
"""
from __future__ import annotations

import datetime
import json
import os
import platform
import re
import socket
import subprocess
import threading
from collections import deque
from typing import Any, Dict, List, Optional

import psutil

try:
    import cpuinfo as _cpuinfo_lib
    _HAS_CPUINFO = True
except ImportError:
    _HAS_CPUINFO = False

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

PLATFORM = platform.system()


def _safe(fn, default=None, *args, **kwargs):
    """Call *fn* safely; return *default* on any exception."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _run(cmd: list[str], timeout: int = 3) -> Optional[str]:
    """Run a subprocess and return stdout, or None on error."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode in (0, 4) else None
    except Exception:
        return None


class DataCollector:
    """Collects and caches all system information with per-call deltas."""

    HISTORY = 60

    def __init__(self) -> None:
        self.cpu_history:     deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.ram_history:     deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.net_rx_history:  deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.net_tx_history:  deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.disk_r_history:  deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self.disk_w_history:  deque[float] = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)

        self.session_start   = datetime.datetime.now()
        self.session_rx: int = 0
        self.session_tx: int = 0

        self._prev_net  = _safe(psutil.net_io_counters)
        self._prev_disk = _safe(psutil.disk_io_counters)
        self._prev_ts   = datetime.datetime.now()

        self.public_ip:  str  = "..."
        self._container      = self._detect_container_vm()
        self._cpu_brand: str  = self._get_cpu_brand()

        psutil.cpu_percent(percpu=True)

        threading.Thread(target=self._fetch_public_ip, daemon=True).start()

        self._snapshot: Dict = {}
        self._lock      = threading.Lock()
        self._running   = True

        self._gpu_cache:  list[Dict] = []
        self._gpu_ts:     float      = 0.0
        self._smart_cache: Dict       = {}
        self._smart_ts:   float      = 0.0
        self._SLOW_TTL = 30.0

        self._collect_snapshot()

        self._bg = threading.Thread(target=self._bg_loop, daemon=True)
        self._bg.start()

    def _bg_loop(self) -> None:
        """Collect a full snapshot every 2 s on a background thread."""
        while self._running:
            try:
                import time
                time.sleep(2.0)
                self._collect_snapshot()
            except Exception:
                pass

    def _collect_snapshot(self) -> None:
        """Gather all metrics and atomically swap into the cache."""
        snap = {
            "os":       self.get_os_info(),
            "cpu":      self.get_cpu_info(),
            "memory":   self.get_memory_info(),
            "storage":  self.get_storage_info(),
            "network":  self.get_network_info(),
            "gpu":      self.get_gpu_info_cached(),
            "process":  self.get_process_info(),
        }
        with self._lock:
            self._snapshot = snap

    def get_snapshot(self) -> Dict:
        """Return the latest cached snapshot (never blocks)."""
        with self._lock:
            return dict(self._snapshot)

    def force_refresh(self) -> None:
        """Trigger an immediate re-collection (called from UI actions)."""
        threading.Thread(target=self._collect_snapshot, daemon=True).start()

    def _get_cpu_brand(self) -> str:
        if _HAS_CPUINFO:
            info = _safe(_cpuinfo_lib.get_cpu_info)
            if info:
                return info.get("brand_raw", platform.processor()) or platform.processor()
        return platform.processor() or "Unknown CPU"

    def _detect_container_vm(self) -> Dict:
        out = {"type": None, "in_container": False, "in_vm": False, "name": "Bare Metal"}

        if os.path.exists("/.dockerenv"):
            return {**out, "type": "docker", "in_container": True, "name": "Docker Container"}

        if PLATFORM == "Linux":
            cgroup = _safe(open, None, "/proc/1/cgroup")
            if cgroup:
                with cgroup as f:
                    body = f.read()
                if "docker" in body:
                    return {**out, "type": "docker", "in_container": True, "name": "Docker Container"}
                if "lxc" in body:
                    return {**out, "type": "lxc", "in_container": True, "name": "LXC Container"}

        vm_map = {
            "QEMU":                "QEMU/KVM VM",
            "VMware":              "VMware VM",
            "VirtualBox":          "VirtualBox VM",
            "Microsoft Corporation": "Hyper-V VM",
            "Xen":                 "Xen VM",
            "innotek":             "VirtualBox VM",
        }
        dmi_text = ""
        if PLATFORM == "Linux":
            for path in ["/sys/class/dmi/id/sys_vendor",
                         "/sys/class/dmi/id/product_name",
                         "/sys/class/dmi/id/board_vendor"]:
                try:
                    with open(path) as f:
                        dmi_text += f.read()
                except Exception:
                    pass
        elif PLATFORM == "Windows":
            dmi_text = _run(["wmic", "computersystem", "get", "manufacturer"]) or ""

        for key, name in vm_map.items():
            if key in dmi_text:
                return {**out, "type": "vm", "in_vm": True, "name": name}

        return out

    def _fetch_public_ip(self) -> None:
        if not _HAS_REQUESTS:
            self.public_ip = "N/A"
            return
        try:
            self.public_ip = _requests.get("https://api.ipify.org", timeout=6).text.strip()
        except Exception:
            self.public_ip = "Unavailable"

    def _elapsed(self) -> float:
        """Seconds since last call; resets the clock."""
        now = datetime.datetime.now()
        dt  = max(0.1, (now - self._prev_ts).total_seconds())
        self._prev_ts = now
        return dt

    def get_os_info(self) -> Dict:
        if not hasattr(self, '_os_static'):
            self._os_static = {
                "os":        PLATFORM,
                "distro":    self._get_distro(),
                "kernel":    platform.release(),
                "hostname":  socket.gethostname(),
                "user":      os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
                "arch":      platform.machine(),
                "container": self._container,
            }

        boot  = psutil.boot_time()
        secs  = datetime.datetime.now().timestamp() - boot
        days, rem = divmod(int(secs), 86400)
        hrs,  rem = divmod(rem, 3600)
        mins      = rem // 60

        if days:
            uptime = f"{days}d {hrs}h {mins}m"
        elif hrs:
            uptime = f"{hrs}h {mins}m"
        else:
            uptime = f"{mins}m"

        return {**self._os_static, "uptime": uptime}

    def _get_distro(self) -> str:
        if PLATFORM == "Linux":
            try:
                import distro as _distro
                return _distro.name(pretty=True)
            except ImportError:
                pass
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            return line.split("=", 1)[1].strip().strip('"')
            except Exception:
                pass
            return f"Linux {platform.release()}"
        if PLATFORM == "Windows":
            return f"Windows {platform.release()} {platform.version()}"
        if PLATFORM == "Darwin":
            return f"macOS {platform.mac_ver()[0]}"
        return PLATFORM

    def get_cpu_info(self) -> Dict:
        phys  = psutil.cpu_count(logical=False) or 1
        logic = psutil.cpu_count(logical=True)  or 1
        pcts  = psutil.cpu_percent(percpu=True) or [0.0] * logic
        total = sum(pcts) / len(pcts)
        self.cpu_history.append(total)

        freqs = _safe(psutil.cpu_freq, None, percpu=True)
        if not freqs:
            g = _safe(psutil.cpu_freq)
            freqs = [g] * logic if g else None

        times = _safe(psutil.cpu_times_percent)
        temps = self._get_cpu_temps()
        fans  = self._get_fans()

        try:
            load = os.getloadavg()
        except (AttributeError, OSError):
            load = None

        cores: list[Dict] = []
        for i in range(logic):
            freq_mhz = None
            if freqs and i < len(freqs) and freqs[i]:
                freq_mhz = freqs[i].current
            elif freqs and len(freqs) == 1 and freqs[0]:
                freq_mhz = freqs[0].current
            cores.append({
                "id":       i,
                "usage":    pcts[i] if i < len(pcts) else 0.0,
                "freq_mhz": freq_mhz,
                "temp":     temps.get(f"core{i}") or temps.get("package"),
            })

        return {
            "brand":         self._cpu_brand,
            "physical_cores": phys,
            "logical_cores":  logic,
            "total_usage":    total,
            "cores":          cores,
            "times": {
                "user":   getattr(times, "user",   0),
                "system": getattr(times, "system", 0),
                "idle":   getattr(times, "idle",   0),
                "iowait": getattr(times, "iowait", 0),
            },
            "load_avg":    load,
            "history":     list(self.cpu_history),
            "package_temp":temps.get("package"),
            "fan_speeds":  fans,
        }

    def _get_cpu_temps(self) -> Dict[str, float]:
        temps: Dict[str, float] = {}
        try:
            all_sensors = psutil.sensors_temperatures()
            if not all_sensors:
                return temps
            priority = ["coretemp", "k10temp", "zenpower", "cpu_thermal",
                        "acpitz", "cpu-thermal", "it8686", "nct6775"]
            ordered = sorted(
                all_sensors.keys(),
                key=lambda k: priority.index(k) if k in priority else 999,
            )
            for name in ordered:
                for entry in all_sensors[name]:
                    lbl = entry.label.lower()
                    if any(x in lbl for x in ("package", "tctl", "tdie", "cpu temp")):
                        temps["package"] = entry.current
                    m = re.search(r"core\s*(\d+)", lbl)
                    if m:
                        temps[f"core{m.group(1)}"] = entry.current
                if temps:
                    break
            if not temps and all_sensors:
                for entries in all_sensors.values():
                    for e in entries:
                        if 10 < e.current < 120:
                            temps["package"] = e.current
                            return temps
        except (AttributeError, Exception):
            pass
        return temps

    def _get_fans(self) -> list[Dict]:
        fans: list[Dict] = []
        try:
            sf = psutil.sensors_fans()
            if sf:
                for name, entries in sf.items():
                    for entry in entries:
                        label = entry.label or name
                        fans.append({"name": label, "rpm": entry.current})
        except (AttributeError, Exception):
            pass
        return fans

    def get_memory_info(self) -> Dict:
        mem  = psutil.virtual_memory()
        swap = psutil.swap_memory()
        self.ram_history.append(mem.percent)

        return {
            "total":       mem.total,
            "used":        mem.used,
            "free":        mem.available,
            "cached":      getattr(mem, "cached", 0) + getattr(mem, "buffers", 0),
            "percent":     mem.percent,
            "swap_total":  swap.total,
            "swap_used":   swap.used,
            "swap_percent":swap.percent,
            "speed_mhz":   self._get_ram_speed(),
            "history":     list(self.ram_history),
        }

    def _get_ram_speed(self) -> Optional[int]:
        if hasattr(self, '_ram_speed_cached'):
            return self._ram_speed_cached
        result = None
        if PLATFORM == "Linux":
            out = _run(["sudo", "dmidecode", "-t", "17"])
            if out:
                for line in out.split("\n"):
                    if "Speed:" in line and "Unknown" not in line and "Configured" not in line:
                        m = re.search(r"(\d+)\s*MT/s", line)
                        if m:
                            result = int(m.group(1))
                            break
        elif PLATFORM == "Windows":
            out = _run(["wmic", "memorychip", "get", "speed"])
            if out:
                nums = [l.strip() for l in out.strip().split("\n") if l.strip().isdigit()]
                if nums:
                    result = int(nums[0])
        self._ram_speed_cached = result
        return result

    def get_storage_info(self) -> Dict:
        partitions: list[Dict] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device":     part.device,
                    "mountpoint": part.mountpoint,
                    "fstype":     part.fstype,
                    "total":      usage.total,
                    "used":       usage.used,
                    "free":       usage.free,
                    "percent":    usage.percent,
                })
            except (PermissionError, OSError):
                pass

        dt = self._elapsed()
        read_bps = write_bps = 0.0
        cur = _safe(psutil.disk_io_counters)
        if cur and self._prev_disk:
            read_bps  = max(0, (cur.read_bytes  - self._prev_disk.read_bytes)  / dt)
            write_bps = max(0, (cur.write_bytes - self._prev_disk.write_bytes) / dt)
        self._prev_disk = cur
        self.disk_r_history.append(read_bps / 1024)
        self.disk_w_history.append(write_bps / 1024)

        return {
            "partitions":    partitions,
            "io_read_bps":   read_bps,
            "io_write_bps":  write_bps,
            "disk_r_history":list(self.disk_r_history),
            "disk_w_history":list(self.disk_w_history),
            "disk_temps":    self._get_disk_temps_cached(partitions),
        }

    def _get_disk_temps_cached(self, partitions: list[Dict]) -> Dict[str, int]:
        """Return cached SMART temps; only re-probe every _SLOW_TTL seconds."""
        import time as _time
        now = _time.monotonic()
        if now - self._smart_ts >= self._SLOW_TTL:
            try:
                self._smart_cache = self._get_disk_temps(partitions)
            except Exception:
                pass
            self._smart_ts = now
        return self._smart_cache

    def _get_disk_temps(self, partitions: list[Dict]) -> Dict[str, int]:
        temps: Dict[str, int] = {}
        if PLATFORM != "Linux":
            return temps
        disks: set[str] = set()
        for p in partitions:
            dev = p["device"]
            if dev.startswith("/dev/"):
                disks.add(re.sub(r"\d+$", "", dev))
        for disk in list(disks)[:3]:
            out = _run(["smartctl", "-A", disk])
            if out:
                for line in out.split("\n"):
                    if "194" in line or "Temperature_Celsius" in line:
                        parts = line.split()
                        if len(parts) >= 10:
                            try:
                                temps[disk] = int(parts[9])
                                break
                            except ValueError:
                                pass
        return temps

    def get_network_info(self) -> Dict:
        dt      = max(0.5, (datetime.datetime.now() - self._prev_ts).total_seconds())
        cur_net = _safe(psutil.net_io_counters)
        rx_bps  = tx_bps = 0.0

        if cur_net and self._prev_net:
            rx_bps = max(0, (cur_net.bytes_recv - self._prev_net.bytes_recv) / dt)
            tx_bps = max(0, (cur_net.bytes_sent - self._prev_net.bytes_sent) / dt)
            self.session_rx += max(0, cur_net.bytes_recv - self._prev_net.bytes_recv)
            self.session_tx += max(0, cur_net.bytes_sent - self._prev_net.bytes_sent)
        self._prev_net = cur_net

        self.net_rx_history.append(rx_bps / 1024)
        self.net_tx_history.append(tx_bps / 1024)

        addrs  = _safe(psutil.net_if_addrs, {})
        stats  = _safe(psutil.net_if_stats, {})
        ifaces: list[Dict] = []
        skip   = {"lo", "Loopback Pseudo-Interface 1"}

        for name, addr_list in (addrs or {}).items():
            if name in skip:
                continue
            ipv4 = ipv6 = mac = None
            for a in addr_list:
                fname = a.family.name
                if fname == "AF_INET":
                    ipv4 = a.address
                elif fname == "AF_INET6":
                    ipv6 = a.address.split("%")[0]
                elif fname in ("AF_LINK", "AF_PACKET"):
                    mac = a.address
            st = (stats or {}).get(name)
            ifaces.append({
                "name":      name,
                "ipv4":      ipv4,
                "ipv6":      ipv6,
                "mac":       mac,
                "is_up":     st.isup if st else False,
                "speed_mbps":st.speed if st else 0,
            })

        return {
            "interfaces":    ifaces,
            "public_ip":     self.public_ip,
            "rx_bps":        rx_bps,
            "tx_bps":        tx_bps,
            "session_rx":    self.session_rx,
            "session_tx":    self.session_tx,
            "rx_history":    list(self.net_rx_history),
            "tx_history":    list(self.net_tx_history),
        }

    def get_gpu_info(self) -> list[Dict]:
        gpus: list[Dict] = []

        out = _run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.used,utilization.gpu,"
             "temperature.gpu,fan.speed",
             "--format=csv,noheader,nounits"],
            timeout=4,
        )
        if out:
            for line in out.strip().split("\n"):
                p = [x.strip() for x in line.split(",")]
                if len(p) < 5:
                    continue
                mt = int(p[1]) if p[1].isdigit() else 0
                mu = int(p[2]) if p[2].isdigit() else 0
                gpus.append({
                    "name":         p[0],
                    "type":         "NVIDIA",
                    "vram_total_mb":mt,
                    "vram_used_mb": mu,
                    "vram_pct":     (mu / mt * 100) if mt else 0.0,
                    "usage_pct":    float(p[3]) if p[3].replace(".", "").isdigit() else 0.0,
                    "temp":         float(p[4]) if p[4].replace(".", "").isdigit() else None,
                    "fan_pct":      float(p[5]) if len(p) > 5 and p[5].replace(".", "").isdigit() else None,
                })

        if not gpus and PLATFORM == "Linux":
            out = _run(["rocm-smi", "--showtemp", "--showuse", "--json"])
            if out:
                try:
                    data = json.loads(out)
                    for cid, cdata in data.items():
                        if str(cid).startswith("card"):
                            gpus.append({
                                "name":         cdata.get("Card series", f"AMD GPU {cid}"),
                                "type":         "AMD",
                                "vram_total_mb":0,
                                "vram_used_mb": 0,
                                "vram_pct":     0.0,
                                "usage_pct":    float(cdata.get("GPU use (%)", 0)),
                                "temp":         float(cdata.get("Temperature (Sensor junction) (°C)", 0) or 0),
                                "fan_pct":      None,
                            })
                except Exception:
                    pass

        if not gpus and PLATFORM == "Linux":
            try:
                for card in os.listdir("/sys/class/drm"):
                    if card.startswith("card") and "-" not in card:
                        vendor_f = f"/sys/class/drm/{card}/device/vendor"
                        if os.path.exists(vendor_f):
                            vendor = open(vendor_f).read().strip()
                            if vendor == "0x8086":
                                gpus.append({
                                    "name":         "Intel Integrated GPU",
                                    "type":         "Intel",
                                    "vram_total_mb":0,
                                    "vram_used_mb": 0,
                                    "vram_pct":     0.0,
                                    "usage_pct":    0.0,
                                    "temp":         None,
                                    "fan_pct":      None,
                                })
                                break
            except Exception:
                pass

        return gpus

    def get_gpu_info_cached(self) -> list[Dict]:
        """Return cached GPU data; only re-probe every _SLOW_TTL seconds."""
        import time as _time
        now = _time.monotonic()
        if now - self._gpu_ts >= self._SLOW_TTL:
            try:
                self._gpu_cache = self.get_gpu_info()
            except Exception:
                pass
            self._gpu_ts = now
        return self._gpu_cache

    def get_process_info(self) -> Dict:
        procs: list[Dict] = []
        attrs = ["pid", "name", "cpu_percent", "memory_percent",
                 "status", "username", "num_threads"]
        try:
            for p in psutil.process_iter(attrs):
                try:
                    i = p.info
                    procs.append({
                        "pid":     i["pid"],
                        "name":    (i["name"] or "?")[:22],
                        "cpu":     round(i["cpu_percent"] or 0.0, 1),
                        "mem":     round(i["memory_percent"] or 0.0, 1),
                        "status":  (i["status"] or "?")[:8],
                        "user":    (i["username"] or "?")[:12],
                        "threads": i["num_threads"] or 0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass

        procs.sort(key=lambda x: x["cpu"], reverse=True)
        total    = len(procs)
        running  = sum(1 for p in procs if p["status"] == "running")
        sleeping = sum(1 for p in procs if p["status"] == "sleeping")

        return {
            "list":     procs[:20],
            "total":    total,
            "running":  running,
            "sleeping": sleeping,
        }
