"""Summarise results/runs.jsonl: median Power cost per (label, workload, browser), and ratio to Safari.

  python3 harness/analyze.py [--label stock] [--since 20261117-2330]
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "results" / "runs.jsonl"
PARITY = 1.2


def load(label: str | None, since: str | None):
    rows = []
    for line in RUNS.read_text().splitlines():
        r = json.loads(line)
        if not r.get("ok"):
            continue
        if label and r["label"] != label:
            continue
        if since and r["stamp"] < since:
            continue
        rows.append(r)
    return rows


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def table(rows, safari_label: str = "stock"):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["workload"], r["browser"], r["label"])].append(r["summary"])
    out = []
    for (wl, br, lb), ss in sorted(groups.items()):
        out.append({
            "workload": wl, "browser": br, "label": lb, "n": len(ss),
            "chip_w": med([s["combined_mw"] for s in ss]) / 1000,
            "cpu_w": med([s["cpu_mw"] for s in ss]) / 1000,
            "gpu_w": med([s["gpu_mw"] for s in ss]) / 1000,
            "system_w": (med([s.get("system_mw") for s in ss]) or 0) / 1000,
            "ws_cpu": med([s.get("windowserver_cpu_ms_per_s") for s in ss]),
            "browser_cpu": med([s.get("browser_cpu_ms_per_s") for s in ss]),
            "wakeups": med([s.get("browser_wakeups_per_s") for s in ss]),
        })
    ref = {(t["workload"]): t for t in out if t["browser"] == "safari" and t["label"] == safari_label}
    for t in out:
        s = ref.get(t["workload"])
        t["chip_x"] = t["chip_w"] / s["chip_w"] if s else None
        t["system_x"] = t["system_w"] / s["system_w"] if s and s["system_w"] else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label")
    ap.add_argument("--since")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    t = table(load(a.label, a.since))
    if a.json:
        print(json.dumps(t, indent=1))
        return
    hdr = f"{'workload':24} {'browser':8} {'label':14} {'n':>2} {'system W':>8} {'×Saf':>5} {'chip W':>7} {'×Saf':>5} {'cpu':>5} {'gpu':>5} {'WS ms/s':>7} {'br ms/s':>7} {'wake/s':>6}"
    print(hdr)
    last = None
    for r in t:
        if last and r["workload"] != last:
            print()
        last = r["workload"]
        sx = f"{r['system_x']:.2f}" if r["system_x"] else "  -  "
        cx = f"{r['chip_x']:.2f}" if r["chip_x"] else "  -  "
        flag = " !" if r["chip_x"] and r["chip_x"] > PARITY else ""
        print(f"{r['workload']:24} {r['browser']:8} {r['label']:14} {r['n']:>2} {r['system_w']:8.2f} {sx:>5} "
              f"{r['chip_w']:7.2f} {cx:>5} {r['cpu_w']:5.2f} {r['gpu_w']:5.2f} {r['ws_cpu'] or 0:7.1f} "
              f"{r['browser_cpu'] or 0:7.1f} {r['wakeups'] or 0:6.0f}{flag}")


if __name__ == "__main__":
    main()
