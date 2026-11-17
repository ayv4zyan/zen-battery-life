"""Run variants (browser + prefs overlay) against workloads, interleaved, and print a comparison.

  python3 harness/experiment.py experiments/001-vibrancy.json

Experiment file:
  {"name": "...", "repeat": 2, "measure": 125, "workloads": ["yt-1080p60-windowed"],
   "variants": [{"label": "stock", "browser": "zen", "prefs": {}},
                {"label": "vib-off", "browser": "zen", "prefs": {"zen.widget.macos.window-vibrancy": false}}]}
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import analyze
import preflight
import run


def main(path: str):
    exp = json.loads(Path(path).read_text())
    run.MEASURE_S = exp.get("measure", run.MEASURE_S)
    ok, problems, _ = preflight.check()
    if not ok:
        print("NOT READY:\n- " + "\n- ".join(problems))
        sys.exit(1)
    # Warm-up: one launch per Gecko browser so background first-launch work (plugin checks,
    # extension rule compilation) happens outside the measurements.
    for name in sorted({v["browser"] for v in exp["variants"]} - {"safari"}):
        b = run.browsers.make(name)
        b.ensure_profile(extensions=tuple(exp.get("extensions", ["uBOLiteRedux@raymondhill.net"])))
        b.launch()
        b.navigate("https://www.youtube.com/")
        time.sleep(45)
        b.quit()
    start = time.strftime("%Y%m%d-%H%M%S")
    exts = tuple(exp.get("extensions", ["uBOLiteRedux@raymondhill.net"]))
    for i in range(exp.get("repeat", 2)):
        for wl in exp["workloads"]:
            for v in exp["variants"]:
                r = run.run_one(v["browser"], wl, v["label"], v.get("prefs"), tuple(v.get("extensions", exts)))
                print(f"[{i + 1}] {v['label']:16} {run.fmt(r)}", flush=True)
                time.sleep(run.COOLDOWN_S)
    print()
    rows = [r for r in analyze.load(None, start)]
    for t in analyze.table(rows):
        print(f"{t['workload']:24} {t['browser']:8} {t['label']:16} n={t['n']} system {t['system_w']:.2f} W  "
              f"chip {t['chip_w']:.2f} W (cpu {t['cpu_w']:.2f} gpu {t['gpu_w']:.2f})  WS {t['ws_cpu'] or 0:.0f} ms/s")


if __name__ == "__main__":
    main(sys.argv[1])
