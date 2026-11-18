"""Run Workloads and record Power cost.

  python3 harness/run.py --browsers safari,firefox,zen --workloads yt-1080p60-windowed --repeat 3 --label stock

Runs are interleaved (A B C, A B C, ...) so slow drift (battery level, temperature) spreads evenly.
Each run: fresh browser launch -> Workload setup -> warmup -> recording -> verification -> quit.
Every run appends one line to results/runs.jsonl; raw data goes to results/raw.noindex/.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import browsers
import inputctl
import power
import preflight
import yt

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw.noindex"
RUNS = ROOT / "results" / "runs.jsonl"

WARMUP_S = 20
MEASURE_S = 150
COOLDOWN_S = 15


# ---------------- Workloads ----------------
# Each workload: setup(b) puts the browser in the measured state; during(b) optionally drives input
# while recording (returns a Popen or None); verify(b) returns facts checked after recording.

def _youtube(video: str, quality: str, fullscreen: bool, reveal_menubar: bool = False):
    def setup(b):
        b.navigate(yt.watch_url(video))
        yt.wait_ready(b)
        yt.set_quality(b, quality)
        time.sleep(2)
        b.focus()
        yt.ensure_playing(b)
        if fullscreen:
            yt.enter_fullscreen(b)
            time.sleep(4)
            if reveal_menubar:
                # Bug 1941693: Gecko reportedly only reaches macOS "detached" low-power video
                # after the fullscreen titlebar/menu bar has been revealed once.
                inputctl.ev("move", "756", "1")
                time.sleep(4)
                inputctl.ev("move", "756", "500")
                time.sleep(3)
        browsers.mouse_park()
        s = yt.state(b)
        if s.get("paused") or s.get("state") != 1:
            raise RuntimeError(f"video not playing: {s}")
        if fullscreen and not s.get("fullscreen"):
            raise RuntimeError("fullscreen did not engage")
        return s

    def verify(b):
        return yt.state(b)

    return {"setup": setup, "verify": verify, "during": None}


def _background_audio():
    def setup(b):
        b.navigate(yt.watch_url("sintel"))
        yt.wait_ready(b)
        yt.set_quality(b, "hd1080")
        b.focus()
        yt.ensure_playing(b)
        time.sleep(2)
        b.new_tab("https://example.com/")
        browsers.mouse_park()
        return {"note": "video in background tab, example.com in front"}

    return {"setup": setup, "verify": lambda b: {"front": b.js("return location.href")}, "during": None}


def _scroll(url: str, flick_px: int = 1000, interval_s: float = 1.6, period: int = 20):
    def setup(b):
        b.navigate(url)
        time.sleep(5)
        b.focus()
        # Pointer over the content column so scroll events target the page.
        inputctl.ev("move", "756", "520")
        # Count scroll events (window and inner scrollers) in the DOM, visible to every browser's injector.
        href = b.js("""
            const el = document.documentElement; el.dataset.mfgaScroll = '0';
            addEventListener('scroll', () => { el.dataset.mfgaScroll = String(+el.dataset.mfgaScroll + 1); },
                             {passive: true, capture: true});
            return location.href;""")
        return {"url": url, "href": href}

    def during(b):
        return inputctl.ev_background("scroll", str(MEASURE_S), str(flick_px), str(interval_s), str(period))

    def verify(b):
        return b.js("""return {scrollY: Math.round(window.scrollY), href: location.href,
                               scrolls: +(document.documentElement.dataset.mfgaScroll || -1)};""")

    return {"setup": setup, "verify": verify, "during": during}


# Mirrors the user's Real session (11 tabs, read from sessionstore by host only). Signed out except
# where the test profile has a login. Video pages are left out of the background set so nothing plays.
IDLE_TABS = [
    "https://www.youtube.com/",
    "https://www.youtube.com/feed/trending",
    "https://chatgpt.com/",
    "https://x.com/home",
    "https://claude.dev/",
    "https://www.amazon.com/",
    "https://www.bbc.com/news",
    "https://github.com/",
    "https://en.wikipedia.org/wiki/Battery",
    "https://chatgpt.com/",  # front tab: the user's most common non-video tab
]


def _idle_tabs():
    def setup(b):
        b.navigate(IDLE_TABS[0])
        for u in IDLE_TABS[1:]:
            b.new_tab(u)
            time.sleep(1)
        b.focus()
        browsers.mouse_park()
        time.sleep(25)  # let pages settle before warmup
        return {"tabs": len(IDLE_TABS)}

    return {"setup": setup, "verify": lambda b: {"front": b.js("return location.host")}, "during": None}


def _idle_system():
    return {"setup": None, "verify": None, "during": None, "no_browser": True}


WORKLOADS = {
    "idle-system": _idle_system(),
    "yt-1080p60-windowed": _youtube("bbb60", "hd1080", False),
    "yt-1080p60-fullscreen": _youtube("bbb60", "hd1080", True),
    "yt-1080p24-windowed": _youtube("sintel", "hd1080", False),
    "yt-1080p24-fullscreen": _youtube("sintel", "hd1080", True),
    "yt-4k60-fullscreen": _youtube("bbb60", "hd2160", True),
    "yt-1080p24-fullscreen-reveal": _youtube("sintel", "hd1080", True, reveal_menubar=True),
    "yt-1080p60-fullscreen-reveal": _youtube("bbb60", "hd1080", True, reveal_menubar=True),
    "yt-background-audio": _background_audio(),
    "idle-tabs": _idle_tabs(),
    "article-scroll": _scroll("https://en.wikipedia.org/wiki/History_of_the_United_States"),
    "x-scroll": _scroll("https://x.com/home", flick_px=1200, interval_s=2.0, period=0),
}


# ---------------- Runner ----------------

def run_one(browser_name: str, workload: str, label: str, prefs: dict | None, extensions: tuple[str, ...],
            profile: str | None = None) -> dict:
    wl = WORKLOADS[workload]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RAW / f"{stamp}_{browser_name}_{workload}_{label}"
    b = None
    rec_info: dict = {"browser": browser_name, "workload": workload, "label": label, "stamp": stamp,
                      "prefs": prefs or {}, "extensions": list(extensions), "profile": profile}
    try:
        if not wl.get("no_browser"):
            b = browsers.make(browser_name, profile)
            if hasattr(b, "ensure_profile"):
                b.ensure_profile(prefs_overlay=prefs, extensions=extensions)
            b.launch()
            rec_info["setup"] = wl["setup"](b)
        time.sleep(WARMUP_S)
        if b:
            b.quiesce(MEASURE_S)
        rec = power.PowerRecorder(MEASURE_S, out_dir)
        rec.start()
        driver = wl["during"](b) if wl.get("during") else None
        r = rec.wait()
        if driver:
            driver.wait(timeout=30)
        if wl.get("verify"):
            rec_info["verify"] = wl["verify"](b)
        rec_info["summary"] = power.summarize(r, None if wl.get("no_browser") else browser_name)
        rec_info["ok"] = True
        st, vf = rec_info.get("setup") or {}, rec_info.get("verify") or {}
        if "scrolls" in vf:  # Scroll Workloads: the page must really have scrolled, on the page we asked for
            if vf["scrolls"] < 100 or vf.get("href") != st.get("href"):
                rec_info["ok"] = False
                rec_info["error"] = f"page did not scroll: scrolls={vf['scrolls']} href={vf.get('href')}"
        if "state" in vf:  # YouTube: must still be playing, and must have played through the window
            played = (vf.get("t") or 0) - (st.get("t") or 0)
            if vf.get("state") != 1 or played < MEASURE_S * 0.95:
                rec_info["ok"] = False
                rec_info["error"] = f"video not playing through window: state={vf.get('state')} played={played:.0f}s"
    except Exception as e:  # noqa: BLE001
        rec_info["ok"] = False
        rec_info["error"] = repr(e)
    finally:
        if b:
            b.quit()
    rec_info["conditions_after"] = preflight.conditions()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(json.dumps(rec_info, indent=1, default=str))
    RUNS.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in rec_info.items() if k != "conditions_after"}
    if "summary" in slim:
        slim["summary"] = {k: v for k, v in slim["summary"].items() if k != "top_processes"}
    with RUNS.open("a") as f:
        f.write(json.dumps(slim, default=str) + "\n")
    return rec_info


def fmt(r: dict) -> str:
    if not r.get("ok"):
        return f"{r['browser']:8} {r['workload']:24} FAILED {r.get('error')}"
    s = r["summary"]
    sysw = f"{s['system_mw'] / 1000:5.2f} W" if s.get("system_mw") else "  n/a  "
    return (f"{r['browser']:8} {r['workload']:24} system {sysw}  chip {s['combined_mw'] / 1000:5.2f} W "
            f"(cpu {s['cpu_mw'] / 1000:4.2f} gpu {s['gpu_mw'] / 1000:4.2f})  "
            f"browser EI {s.get('browser_energy_impact', 0):6.1f}  WS cpu {s.get('windowserver_cpu_ms_per_s') or 0:5.1f} ms/s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browsers", default="safari,firefox,zen")
    ap.add_argument("--workloads", required=True)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--label", default="stock")
    ap.add_argument("--prefs", default="{}", help="JSON prefs overlay for Firefox/Zen")
    ap.add_argument("--extensions", default="uBOLiteRedux@raymondhill.net")
    ap.add_argument("--allow-plugged", action="store_true")
    ap.add_argument("--measure", type=int, default=MEASURE_S)
    a = ap.parse_args()
    globals()["MEASURE_S"] = a.measure

    ok, problems, _ = preflight.check(require_battery=not a.allow_plugged)
    if not ok:
        print("NOT READY:\n- " + "\n- ".join(problems))
        sys.exit(1)
    prefs = json.loads(a.prefs)
    exts = tuple(x for x in a.extensions.split(",") if x)
    for i in range(a.repeat):
        for wl in a.workloads.split(","):
            for br in a.browsers.split(","):
                r = run_one(br, wl, a.label, prefs, exts)
                print(f"[{i + 1}/{a.repeat}] {fmt(r)}", flush=True)
                time.sleep(COOLDOWN_S)


if __name__ == "__main__":
    main()
