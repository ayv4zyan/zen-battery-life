"""Checks that a measurement batch can run under fixed conditions. Never changes any setting."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import power

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "bin" / "mfga-input"
REF = ROOT / "results" / "conditions.json"
BROWSER_PROCS = {"safari": "Safari", "firefox": "firefox", "zen": "zen"}


def _run(*cmd) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def conditions() -> dict:
    b = power.battery_snapshot()
    vol = _run("osascript", "-e", "output volume of (get volume settings)")
    muted = _run("osascript", "-e", "output muted of (get volume settings)")
    return {
        "brightness": float(_run(str(INPUT), "brightness") or -1),
        "volume": int(vol) if vol.isdigit() else None,
        "muted": muted == "true",
        "on_battery": b["on_battery"],
        "charge_pct": b["charge_pct"],
        "low_power_mode": "lowpowermode         1" in _run("pmset", "-g"),
        "thermal": _run("pmset", "-g", "therm"),
        "accessibility": _run(str(INPUT), "trusted") == "yes",
        "sudo_powermetrics": power.sudo_powermetrics_ok(),
        "running_browsers": [k for k, p in BROWSER_PROCS.items()
                             if subprocess.run(["pgrep", "-x", p], capture_output=True).returncode == 0],
    }


def check(require_battery: bool = True) -> tuple[bool, list[str], dict]:
    c = conditions()
    problems = []
    if not c["sudo_powermetrics"]:
        problems.append("powermetrics needs passwordless sudo (SETUP.md step 1)")
    if not c["accessibility"]:
        problems.append("Accessibility permission for Claude is off (SETUP.md step 3)")
    if require_battery and not c["on_battery"]:
        problems.append("plugged in: unplug the charger")
    if c["charge_pct"] is not None and c["charge_pct"] < 40:
        problems.append(f"battery at {c['charge_pct']}%, need at least 40%")
    if c["low_power_mode"]:
        problems.append("Low Power Mode is on")
    if c["running_browsers"]:
        problems.append(f"quit these first: {', '.join(c['running_browsers'])}")
    if REF.exists():
        ref = json.loads(REF.read_text())
        if abs(ref["brightness"] - c["brightness"]) > 0.01:
            problems.append(f"brightness is {c['brightness']:.3f}, reference is {ref['brightness']:.3f}")
        if ref.get("volume") != c["volume"] or ref.get("muted") != c["muted"]:
            problems.append(f"volume is {c['volume']} (muted={c['muted']}), reference is "
                            f"{ref.get('volume')} (muted={ref.get('muted')})")
    return not problems, problems, c


def pin_reference():
    """Record the current brightness and volume as the fixed conditions for all future runs."""
    c = conditions()
    REF.parent.mkdir(parents=True, exist_ok=True)
    REF.write_text(json.dumps({"brightness": c["brightness"], "volume": c["volume"], "muted": c["muted"]}, indent=1))
    return c


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["pin"]:
        print(json.dumps(pin_reference(), indent=1))
    else:
        ok, problems, c = check()
        print(json.dumps(c, indent=1))
        print("OK" if ok else "NOT READY:\n- " + "\n- ".join(problems))
