"""Power recording: powermetrics (chip-level, per-process) + battery telemetry (whole system).

Battery: AppleSmartBattery publishes AccumulatedSystemLoad (mW summed once per second) and
SystemLoadAccumulatorCount about once a minute. Delta(acc)/Delta(count) between two
publications is the exact average whole-system power (display included) over that span.
"""
from __future__ import annotations

import json
import plistlib
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

POWERMETRICS = "/usr/bin/powermetrics"


def _u64_to_i64(v: int) -> int:
    return v - (1 << 64) if v >= (1 << 63) else v


def battery_snapshot() -> dict:
    out = subprocess.run(["ioreg", "-rn", "AppleSmartBattery", "-w0"],
                         capture_output=True, text=True, check=True).stdout
    vals = {k: int(v) for k, v in re.findall(r'"(\w+)" ?= ?(\d+)', out)}
    ext = re.search(r'"ExternalConnected" = (Yes|No)', out)
    return {
        "t": time.time(),
        "system_load_mw": vals.get("SystemLoad"),
        "acc_load": vals.get("AccumulatedSystemLoad"),
        "acc_count": vals.get("SystemLoadAccumulatorCount"),
        "amperage_ma": _u64_to_i64(vals.get("InstantAmperage", 0)),
        "voltage_mv": vals.get("Voltage"),
        "charge_pct": vals.get("CurrentCapacity"),
        "on_battery": ext is not None and ext.group(1) == "No",
    }


def sudo_powermetrics_ok() -> bool:
    r = subprocess.run(["sudo", "-n", POWERMETRICS, "-n", "1", "-i", "100", "--samplers", "cpu_power"],
                       capture_output=True, text=True)
    return r.returncode == 0


@dataclass
class Recording:
    pm_samples: list = field(default_factory=list)
    battery: list = field(default_factory=list)
    t_start: float = 0.0
    t_end: float = 0.0


class PowerRecorder:
    """Records for a fixed duration. start() returns immediately; wait() blocks until done."""

    def __init__(self, seconds: int, out_dir: Path, interval_ms: int = 1000):
        self.seconds = seconds
        self.interval_ms = interval_ms
        self.out_dir = out_dir
        self.rec = Recording()
        self._stop = threading.Event()

    def start(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.pm_path = self.out_dir / "powermetrics.plists"
        n = max(1, (self.seconds * 1000) // self.interval_ms)
        self.rec.t_start = time.time()
        self.proc = subprocess.Popen(
            ["sudo", "-n", POWERMETRICS, "-i", str(self.interval_ms), "-n", str(n),
             "--samplers", "cpu_power,gpu_power,tasks", "--show-process-energy",
             "--show-process-gpu", "-f", "plist", "-o", str(self.pm_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self._bt = threading.Thread(target=self._poll_battery, daemon=True)
        self._bt.start()

    def _poll_battery(self):
        while not self._stop.is_set():
            try:
                self.rec.battery.append(battery_snapshot())
            except Exception as e:  # noqa: BLE001
                self.rec.battery.append({"t": time.time(), "error": str(e)})
            self._stop.wait(2.0)

    def wait(self) -> Recording:
        _, err = self.proc.communicate()
        self.rec.t_end = time.time()
        self._stop.set()
        self._bt.join()
        self.rec.battery.append(battery_snapshot())
        if self.proc.returncode != 0:
            raise RuntimeError(f"powermetrics failed: {err.decode(errors='replace')}")
        raw = self.pm_path.read_bytes()
        for chunk in raw.split(b"\x00"):
            chunk = chunk.strip()
            if chunk:
                self.rec.pm_samples.append(plistlib.loads(chunk))
        (self.out_dir / "battery.json").write_text(json.dumps(self.rec.battery, indent=1))
        return self.rec


# ---------- summarising ----------

def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def battery_average_mw(battery: list) -> tuple[float | None, float]:
    """Exact average from the accumulator, over the span between the first and last
    publication seen during the run. Returns (mW, seconds covered)."""
    pubs = []
    for s in battery:
        if "acc_count" not in s or s["acc_count"] is None:
            continue
        if not pubs or s["acc_count"] != pubs[-1]["acc_count"]:
            pubs.append(s)
    if len(pubs) < 2:
        return None, 0.0
    d_acc = pubs[-1]["acc_load"] - pubs[0]["acc_load"]
    d_cnt = pubs[-1]["acc_count"] - pubs[0]["acc_count"]
    return (d_acc / d_cnt if d_cnt else None), float(d_cnt)


METRICS = {
    "energy_impact": "energy_impact_per_s",
    "cpu_ms_per_s": "cputime_ms_per_s",
    "gpu_ms_per_s": "gputime_ms_per_s",
    "intr_wakeups_per_s": "intr_wakeups_per_s",
    "idle_wakeups_per_s": "idle_wakeups_per_s",
}

# Process-name prefixes per browser family, for attributing per-process energy.
FAMILIES = {
    "safari": ("Safari", "com.apple.WebKit", "com.apple.Safari"),
    "firefox": ("firefox", "plugin-container", "Firefox", "media-plugin-helper", "gpu-helper"),
    "zen": ("zen", "plugin-container", "Zen", "media-plugin-helper", "gpu-helper"),
}


def summarize(rec: Recording, family: str | None) -> dict:
    s = rec.pm_samples
    proc = [x.get("processor", {}) for x in s]
    gpu = [x.get("gpu", {}) for x in s]
    out = {
        "seconds": round(rec.t_end - rec.t_start, 1),
        "samples": len(s),
        "combined_mw": _mean([p.get("combined_power") for p in proc]),
        "cpu_mw": _mean([p.get("cpu_power") for p in proc]),
        "gpu_mw": _mean([p.get("gpu_power") or g.get("gpu_energy") for p, g in zip(proc, gpu)]),
        "ane_mw": _mean([p.get("ane_power") for p in proc]),
        "gpu_active_pct": _mean([(1 - g["idle_ratio"]) * 100 for g in gpu if "idle_ratio" in g]),
    }
    sys_mw, covered = battery_average_mw(rec.battery)
    out["system_mw"] = sys_mw
    out["system_seconds_covered"] = covered
    # Per-process aggregation (energy impact and CPU ms/s), averaged across samples.
    per = {}
    for x in s:
        for t in x.get("tasks", []):
            name = t.get("name", "?")
            a = per.setdefault(name, {m: 0.0 for m in METRICS})
            for m, src in METRICS.items():
                a[m] += t.get(src, 0.0) or 0.0
    n = max(1, len(s))
    procs = sorted(({"name": k, **{m: round(v[m] / n, 2) for m in METRICS}}
                    for k, v in per.items()), key=lambda d: -d["energy_impact"])
    out["top_processes"] = procs[:15]
    if family:
        pre = FAMILIES[family]
        mine = [p for p in procs if p["name"].startswith(pre)]
        out["browser_energy_impact"] = sum(p["energy_impact"] for p in mine)
        out["browser_cpu_ms_per_s"] = sum(p["cpu_ms_per_s"] for p in mine)
        out["browser_wakeups_per_s"] = sum(p["intr_wakeups_per_s"] + p["idle_wakeups_per_s"] for p in mine)
    ws = next((p for p in procs if p["name"] == "WindowServer"), None)
    out["windowserver_cpu_ms_per_s"] = ws["cpu_ms_per_s"] if ws else None
    out["windowserver_energy_impact"] = ws["energy_impact"] if ws else None
    out["gpu_freq_mhz"] = _mean([g.get("freq_hz") for g in gpu])
    return out
