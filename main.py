"""
ZerithSys  –  A real-time system monitor.
Usage:  python main.py  [--theme tokyo-night|dracula|nord|gruvbox]
Keys:   q quit  ·  t next theme  ·  r force refresh  ·  k kill selected
        s sort by RAM  ·  c sort by CPU (default)  ·  / search processes
"""
from __future__ import annotations

import argparse
import os
import sys
import platform
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Label, Static
from rich.text import Text

from modules.ascii_art import get_ascii_art
from modules.data_collector import DataCollector

import pathlib as _pl
_CSS_CANDIDATES = [
    _pl.Path(__file__).parent / "app.tcss",
    _pl.Path(__file__).parent / ".." / "share" / "app.tcss",
    _pl.Path.home() / ".zerithsys" / "app.tcss",
]
_CSS_PATH = next((str(p) for p in _CSS_CANDIDATES if p.exists()), "app.tcss")

PALETTE = {
    "tokyo-night": dict(
        cpu="#7aa2f7", mem="#9ece6a", gpu="#bb9af7",
        stor="#ff9e64", net="#2ac3de", proc="#f7768e",
        dim="#565f89", text="#c0caf5",
    ),
    "dracula": dict(
        cpu="#6272a4", mem="#50fa7b", gpu="#bd93f9",
        stor="#ffb86c", net="#8be9fd", proc="#ff5555",
        dim="#6272a4", text="#f8f8f2",
    ),
    "nord": dict(
        cpu="#88c0d0", mem="#a3be8c", gpu="#b48ead",
        stor="#d08770", net="#8fbcbb", proc="#bf616a",
        dim="#4c566a", text="#eceff4",
    ),
    "gruvbox": dict(
        cpu="#458588", mem="#98971a", gpu="#b16286",
        stor="#d79921", net="#689d6a", proc="#cc241d",
        dim="#7c6f64", text="#ebdbb2",
    ),
}

THEME_ORDER = list(PALETTE.keys())


def _fmt(n: float, suffix: str = "B") -> str:
    """Human-readable byte size."""
    for u in ("", "K", "M", "G", "T"):
        if abs(n) < 1024.0:
            return f"{n:6.1f} {u}{suffix}"
        n /= 1024.0
    return f"{n:.1f} P{suffix}"


def _spd(bps: float) -> str:
    """Speed string from bytes-per-second."""
    if bps < 1024:
        return f"{bps:5.0f} B/s "
    if bps < 1024 ** 2:
        return f"{bps/1024:5.1f} KB/s"
    return f"{bps/1024**2:5.1f} MB/s"


def _spark(vals: list, width: int = 30, hi: float = 100.0) -> str:
    """Unicode block sparkline."""
    blk = " ▁▂▃▄▅▆▇█"
    if not vals or hi <= 0:
        return "▁" * width
    vs = list(vals)[-width:]
    vs = [0.0] * (width - len(vs)) + vs
    return "".join(blk[min(8, int(v / hi * 8))] for v in vs)


def _bar(pct: float, w: int = 16) -> str:
    """Rich-markup coloured progress bar."""
    filled = max(0, min(w, int(pct / 100 * w)))
    empty  = w - filled
    if pct >= 90:
        col = "bold red"
    elif pct >= 70:
        col = "yellow"
    elif pct >= 45:
        col = "green"
    else:
        col = "cyan"
    return f"[{col}]{'█' * filled}[/{col}][dim]{'░' * empty}[/dim]"


def _temp(t: Optional[float]) -> str:
    """Temperature with colour and label."""
    if t is None:
        return "[dim]  N/A[/dim]"
    if t >= 85:
        return f"[bold red]HOT {t:3.0f}°[/bold red]"
    if t >= 65:
        return f"[yellow]WARM {t:3.0f}°[/yellow]"
    return f"[green]COOL {t:3.0f}°[/green]"


class OSPanel(Static):
    """Distro ASCII art + system overview."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(10.0, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("os", {})
        art, art_color = get_ascii_art(d["os"], d["distro"])

        art_lines  = art.splitlines()
        pal        = app.pal

        info_lines = [
            f"[bold {pal['cpu']}]ZerithSys[/bold {pal['cpu']}]  "
            f"[dim]─ real-time system monitor[/dim]",
            f"[dim]{'─' * 40}[/dim]",
            f"[dim]OS      [/dim][{pal['text']}]{d['distro']}[/{pal['text']}]",
            f"[dim]Kernel  [/dim][{pal['text']}]{d['kernel']}[/{pal['text']}]",
            f"[dim]Uptime  [/dim][{pal['mem']}]{d['uptime']}[/{pal['mem']}]",
            f"[dim]Host    [/dim][{pal['text']}]{d['hostname']}[/{pal['text']}]",
            f"[dim]User    [/dim][{pal['cpu']}]{d['user']}[/{pal['cpu']}]",
            f"[dim]Arch    [/dim][{pal['text']}]{d['arch']}[/{pal['text']}]",
        ]

        c = d.get("container", {})
        if c.get("in_container"):
            info_lines.append(f"[dim]Virt    [/dim][yellow][DOCKER] {c['name']}[/yellow]")
        elif c.get("in_vm"):
            info_lines.append(f"[dim]Virt    [/dim][yellow][VM] {c['name']}[/yellow]")

        art_w = max((len(l) for l in art_lines), default=0)
        rows  = max(len(art_lines), len(info_lines))
        lines = []
        for i in range(rows):
            a  = art_lines[i]  if i < len(art_lines)  else ""
            ii = info_lines[i] if i < len(info_lines) else ""
            pad = art_w - len(a) + 3
            lines.append(f"[bold {art_color}]{a}[/bold {art_color}]{' ' * pad}{ii}")

        self.update("\n".join(lines))


class CPUPanel(Static):
    """Per-core usage, frequency, temperature, sparkline."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(2.5, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("cpu", {})
        pal = app.pal
        c   = pal["cpu"]

        lines: list[str] = [
            f"[bold {c}]  CPU  [/bold {c}]",
            f"[dim]{d['brand'][:46]}[/dim]",
            f"[dim]{d['physical_cores']}P / {d['logical_cores']}T[/dim]"
            f"   Pkg: {_temp(d.get('package_temp'))}",
            f"[dim]{'─' * 44}[/dim]",
        ]

        cores = d["cores"]
        show  = cores[:10]
        for core in show:
            pct  = core["usage"]
            freq = f"{core['freq_mhz']/1000:.2f}G" if core.get("freq_mhz") else " ?GHz"
            lines.append(
                f"[dim]C{core['id']:02d}[/dim] {_bar(pct,14)} "
                f"[{c}]{pct:4.0f}%[/{c}] [dim]{freq}[/dim] {_temp(core.get('temp'))}"
            )

        if len(cores) > 10:
            lines.append(f"[dim]    … {len(cores)-10} more cores hidden[/dim]")

        lines.append(f"[dim]{'─' * 44}[/dim]")

        tot = d["total_usage"]
        lines.append(
            f"[bold]TOT[/bold] {_bar(tot, 14)} [bold {c}]{tot:4.0f}%[/bold {c}]"
        )

        t = d.get("times", {})
        lines.append(
            f"[dim] usr {t.get('user',0):4.1f}%  sys {t.get('system',0):4.1f}%"
            f"  idl {t.get('idle',0):4.1f}%  iow {t.get('iowait',0):4.1f}%[/dim]"
        )

        load = d.get("load_avg")
        if load:
            lines.append(f"[dim] Load avg: {load[0]:.2f}  {load[1]:.2f}  {load[2]:.2f}[/dim]")

        sl = _spark(d.get("history", []), width=42, hi=100)
        lines.append(f"[dim] hist │[/dim][{c}]{sl}[/{c}][dim]│[/dim]")

        fans = d.get("fan_speeds", [])
        if fans:
            fan_parts = [f"{f['name'][:10]}: {f['rpm']}rpm" for f in fans[:4]]
            lines.append(f"[dim] fans: {', '.join(fan_parts)}[/dim]")

        self.update("\n".join(lines))


class MemoryPanel(Static):
    """RAM and Swap with history sparkline."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(2.0, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("memory", {})
        pal = app.pal
        c   = pal["mem"]

        lines: list[str] = [
            f"[bold {c}]  MEMORY  [/bold {c}]",
            f"[dim]{'─' * 44}[/dim]",
        ]

        rp = d["percent"]
        lines.append(
            f"[bold]RAM [/bold]{_bar(rp,18)} [{c}]{rp:5.1f}%[/{c}]"
        )
        lines.append(
            f"[dim]  Used   [/dim][{c}]{_fmt(d['used'])}[/{c}]"
            f"[dim]  /  Total [/dim][{pal['text']}]{_fmt(d['total'])}[/{pal['text']}]"
        )
        lines.append(
            f"[dim]  Free   [/dim]{_fmt(d['free'])}"
            f"[dim]    Cached [/dim]{_fmt(d['cached'])}"
        )

        if d["swap_total"] > 0:
            sp = d["swap_percent"]
            lines.append(f"[dim]{'─' * 44}[/dim]")
            lines.append(
                f"[bold]SWAP[/bold]{_bar(sp,18)} [yellow]{sp:5.1f}%[/yellow]"
            )
            lines.append(
                f"[dim]  Used   [/dim][yellow]{_fmt(d['swap_used'])}[/yellow]"
                f"[dim]  /  Total [/dim]{_fmt(d['swap_total'])}"
            )
        else:
            lines.append(f"[dim]SWAP  (none)[/dim]")

        spd = d.get("speed_mhz")
        if spd:
            lines.append(f"[dim]{'─' * 44}[/dim]")
            lines.append(f"[dim]Bus speed: [/dim][{c}]{spd} MT/s[/{c}]")

        lines.append(f"[dim]{'─' * 44}[/dim]")
        sl = _spark(d.get("history", []), width=42, hi=100)
        lines.append(f"[dim] hist │[/dim][{c}]{sl}[/{c}][dim]│[/dim]")

        self.update("\n".join(lines))


class GPUPanel(Static):
    """GPU(s) info: VRAM, usage, temperature, fan."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(4.0, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        gpus = app.collector.get_snapshot().get("gpu", [])
        pal  = app.pal
        c    = pal["gpu"]

        lines: list[str] = [f"[bold {c}]  GPU  [/bold {c}]"]

        if not gpus:
            lines.append(f"[dim]  No GPU detected[/dim]")
            lines.append(f"[dim]  (nvidia-smi / rocm-smi not found)[/dim]")
            self.update("\n".join(lines))
            return

        for g in gpus:
            lines.append(f"[dim]{'─' * 44}[/dim]")
            lines.append(f"[{c}]{g['name'][:44]}[/{c}]")
            lines.append(f"[dim]  Type: [/dim]{g['type']}")

            vt = g["vram_total_mb"]
            vu = g["vram_used_mb"]
            vp = g["vram_pct"]
            if vt:
                lines.append(
                    f"[dim]  VRAM [/dim]{_bar(vp,14)} [{c}]{vp:5.1f}%[/{c}]"
                    f"  [dim]{vu}/{vt} MB[/dim]"
                )

            up = g["usage_pct"]
            lines.append(
                f"[dim]  Load [/dim]{_bar(up,14)} [{c}]{up:5.1f}%[/{c}]"
            )

            lines.append(f"[dim]  Temp: [/dim]{_temp(g.get('temp'))}")

            fan = g.get("fan_pct")
            if fan is not None:
                lines.append(f"[dim]  Fan:  [/dim][{c}]{fan:.0f}%[/{c}]")

        self.update("\n".join(lines))


class StoragePanel(Static):
    """Disk partitions, I/O speeds, SMART temperatures."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(3.0, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("storage", {})
        pal = app.pal
        c   = pal["stor"]

        lines: list[str] = [f"[bold {c}]  STORAGE  [/bold {c}]"]

        for p in d["partitions"]:
            pct = p["percent"]
            dev = p["device"].replace("/dev/", "")[:10]
            mnt = p["mountpoint"][:14]
            lines.append(f"[dim]{'─' * 44}[/dim]")
            lines.append(
                f"[{c}]{dev}[/{c}][dim]  →  {mnt}  ({p['fstype']})[/dim]"
            )
            lines.append(
                f"  {_bar(pct, 16)} [{c}]{pct:4.1f}%[/{c}]"
                f"  [dim]{_fmt(p['free'])} free / {_fmt(p['total'])}[/dim]"
            )

            disk_dev = p["device"]
            import re as _re
            base = _re.sub(r"\d+$", "", disk_dev)
            temp_v = d["disk_temps"].get(base) or d["disk_temps"].get(disk_dev)
            if temp_v:
                lines.append(f"[dim]  SMART temp: [/dim]{_temp(float(temp_v))}")

        lines.append(f"[dim]{'─' * 44}[/dim]")
        r_spd = d["io_read_bps"]
        w_spd = d["io_write_bps"]
        lines.append(
            f"[dim]  Read  [/dim][{c}]{_spd(r_spd):>12}[/{c}]"
            f"  [dim]Write [/dim][{pal['proc']}]{_spd(w_spd):>12}[/{pal['proc']}]"
        )
        hi = max(max(d["disk_r_history"] or [1]), max(d["disk_w_history"] or [1]), 1)
        sl_r = _spark(d["disk_r_history"], width=20, hi=hi)
        sl_w = _spark(d["disk_w_history"], width=20, hi=hi)
        lines.append(f"[dim] R │[/dim][{c}]{sl_r}[/{c}]")
        lines.append(f"[dim] W │[/dim][{pal['proc']}]{sl_w}[/{pal['proc']}]")

        self.update("\n".join(lines))


class NetworkPanel(Static):
    """Network interfaces, IPs, live traffic, session totals."""

    def on_mount(self) -> None:
        self._draw()
        self.set_interval(2.5, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("network", {})
        pal = app.pal
        c   = pal["net"]

        lines: list[str] = [f"[bold {c}]  NETWORK  [/bold {c}]"]

        for iface in d["interfaces"][:6]:
            if not iface.get("ipv4") and not iface.get("is_up"):
                continue
            up_mark = f"[{c}]●[/{c}]" if iface.get("is_up") else "[red]○[/red]"
            lines.append(f"[dim]{'─' * 44}[/dim]")
            lines.append(
                f"{up_mark} [{c}]{iface['name'][:14]}[/{c}]"
                f"  [dim]speed:[/dim] {iface.get('speed_mbps', 0)} Mbps"
            )
            if iface.get("ipv4"):
                lines.append(f"[dim]   IPv4  [/dim]{iface['ipv4']}")
            if iface.get("ipv6"):
                lines.append(f"[dim]   IPv6  [/dim][dim]{iface['ipv6'][:38]}[/dim]")
            if iface.get("mac"):
                lines.append(f"[dim]   MAC   [/dim][dim]{iface['mac']}[/dim]")

        lines.append(f"[dim]{'─' * 44}[/dim]")
        lines.append(f"[dim]  WAN IP  [/dim][{c}]{d['public_ip']}[/{c}]")

        lines.append(f"[dim]{'─' * 44}[/dim]")
        lines.append(
            f"[dim]  ↓ Down  [/dim][{c}]{_spd(d['rx_bps']):>12}[/{c}]  "
            f"[dim]↑ Up    [/dim][{pal['stor']}]{_spd(d['tx_bps']):>12}[/{pal['stor']}]"
        )

        lines.append(
            f"[dim]  Session ↓ [/dim]{_fmt(d['session_rx'])}"
            f"[dim]  ↑ [/dim]{_fmt(d['session_tx'])}"
        )

        hi = max(
            max(d["rx_history"] or [1]),
            max(d["tx_history"] or [1]),
            1,
        )
        sl_r = _spark(d["rx_history"], width=20, hi=hi)
        sl_t = _spark(d["tx_history"], width=20, hi=hi)
        lines.append(f"[dim] ↓ │[/dim][{c}]{sl_r}[/{c}]")
        lines.append(f"[dim] ↑ │[/dim][{pal['stor']}]{sl_t}[/{pal['stor']}]")

        self.update("\n".join(lines))


class ProcessPanel(Vertical):
    """Interactive process list with DataTable."""

    _sort_by: str = "cpu"

    def compose(self) -> ComposeResult:
        yield Static("", id="proc-header")
        yield DataTable(id="proc-table")

    def on_mount(self) -> None:
        tbl = self.query_one("#proc-table", DataTable)
        tbl.cursor_type   = "row"
        tbl.zebra_stripes = True
        tbl.add_columns("PID", "Name", "CPU%", "MEM%", "Status", "User", "Thd")
        self._draw()
        self.set_interval(5.0, self._draw)

    def _draw(self) -> None:
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        d   = app.collector.get_snapshot().get("process", {})
        pal = app.pal
        c   = pal["proc"]

        hdr = self.query_one("#proc-header", Static)
        hdr.update(
            f"[bold {c}]  PROCESSES  [/bold {c}]"
            f"  [dim]total:[/dim] [{c}]{d['total']}[/{c}]"
            f"  [dim]run:[/dim] [green]{d['running']}[/green]"
            f"  [dim]slp:[/dim] [dim]{d['sleeping']}[/dim]"
            f"  [dim]sort:[/dim] [yellow]{self._sort_by.upper()}[/yellow]"
            f"  [dim]  c=CPU  s=MEM  k=kill  q=quit[/dim]"
        )

        procs = list(d["list"])
        if self._sort_by == "mem":
            procs.sort(key=lambda x: x["mem"], reverse=True)

        tbl = self.query_one("#proc-table", DataTable)
        tbl.clear()
        for p in procs:
            cpu_s = f"{p['cpu']:5.1f}"
            mem_s = f"{p['mem']:5.1f}"
            if p["cpu"] >= 50:
                cpu_rich = f"[bold red]{cpu_s}[/bold red]"
            elif p["cpu"] >= 20:
                cpu_rich = f"[yellow]{cpu_s}[/yellow]"
            else:
                cpu_rich = f"[green]{cpu_s}[/green]"

            if p["mem"] >= 10:
                mem_rich = f"[bold red]{mem_s}[/bold red]"
            elif p["mem"] >= 4:
                mem_rich = f"[yellow]{mem_s}[/yellow]"
            else:
                mem_rich = f"[green]{mem_s}[/green]"

            tbl.add_row(
                Text(str(p["pid"]),  no_wrap=True),
                Text(p["name"],      no_wrap=True),
                Text.from_markup(cpu_rich),
                Text.from_markup(mem_rich),
                Text(p["status"],    no_wrap=True),
                Text(p["user"],      no_wrap=True),
                Text(str(p["threads"]), no_wrap=True),
            )


class ZerithSysApp(App):
    """ZerithSys  –  cross-platform real-time system monitor."""

    CSS_PATH = _CSS_PATH
    TITLE    = "ZerithSys"

    BINDINGS = [
        Binding("q",      "quit",         "Quit"),
        Binding("t",      "next_theme",    "Theme"),
        Binding("r",      "refresh_all",   "Refresh"),
        Binding("c",      "sort_cpu",      "Sort CPU"),
        Binding("s",      "sort_mem",      "Sort MEM"),
        Binding("k",      "kill_proc",     "Kill"),
        Binding("ctrl+c", "quit",          "Quit", show=False),
    ]

    def __init__(self, theme: str = "tokyo-night") -> None:
        super().__init__()
        self.collector     = DataCollector()
        self._theme_idx    = THEME_ORDER.index(theme) if theme in THEME_ORDER else 0
        self.pal           = PALETTE[THEME_ORDER[self._theme_idx]]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with ScrollableContainer(id="main-scroll"):
            yield OSPanel()
            with Horizontal(id="row-sensors"):
                yield CPUPanel()
                yield MemoryPanel()
                yield GPUPanel()
            with Horizontal(id="row-io"):
                yield StoragePanel()
                yield NetworkPanel()
            yield ProcessPanel()
        yield Footer()

    def action_next_theme(self) -> None:
        """Cycle through colour themes."""
        self._theme_idx = (self._theme_idx + 1) % len(THEME_ORDER)
        name            = THEME_ORDER[self._theme_idx]
        self.pal        = PALETTE[name]

        for t in THEME_ORDER:
            self.screen.remove_class(f"theme-{t}")
        if name != "tokyo-night":
            self.screen.add_class(f"theme-{name}")

        self.sub_title = f"Theme: {name}"
        self.action_refresh_all()

    def action_refresh_all(self) -> None:
        """Force an immediate re-collection on a background thread."""
        app: ZerithSysApp = self.app  # type: ignore[assignment]
        app.collector.force_refresh()

    def action_sort_cpu(self) -> None:
        proc = self.query_one(ProcessPanel)
        proc._sort_by = "cpu"
        proc._draw()

    def action_sort_mem(self) -> None:
        proc = self.query_one(ProcessPanel)
        proc._sort_by = "mem"
        proc._draw()

    def action_kill_proc(self) -> None:
        """Kill the currently highlighted process."""
        try:
            import psutil
            from textual.coordinate import Coordinate
            tbl     = self.query_one("#proc-table", DataTable)
            row_idx = tbl.cursor_row
            cell    = tbl.get_cell_at(Coordinate(row_idx, 0))
            pid     = int(str(cell).strip())
            psutil.Process(pid).terminate()
            self.notify(f"Sent SIGTERM to PID {pid}", severity="warning")
        except Exception as exc:
            self.notify(f"Kill failed: {exc}", severity="error")


def main() -> None:
    parser = argparse.ArgumentParser(description="ZerithSys – system monitor")
    parser.add_argument(
        "--theme",
        choices=THEME_ORDER,
        default="tokyo-night",
        help="Colour theme (default: tokyo-night)",
    )
    args = parser.parse_args()
    ZerithSysApp(theme=args.theme).run()


if __name__ == "__main__":
    main()
