"""Dump Gecko's native (Core Animation) layer tree during fullscreen YouTube and say why
macOS low-power "detached" video mode is or isn't possible.

  python3 harness/layerdump.py zen [--prefs '{"k": v}'] [--windowed]

Mirrors NativeLayerRootCA::CheckVideoLowPower: exactly one video layer, video on top,
an opaque black full-screen layer directly below it, window fullscreen.
The dump folder (~/Desktop/nativelayerdumps-<pid>) is deleted afterwards.
"""
from __future__ import annotations

import argparse
import html.parser
import json
import re
import shutil
import time
from pathlib import Path

import browsers
import control
import run

DESKTOP = Path.home() / "Desktop"
PREF = "gfx.webrender.debug.dump-native-layer-tree-to-file"


class _Layers(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.layers = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        st = a.get("style", "")
        if tag == "div":
            box = {k: float(v) for k, v in re.findall(r"(left|top|width|height): ([-\d.e+]+)px", st)}
            color = re.search(r"background: rgb\(([^)]*)\); opacity: ([\d.]+)", st)
            self.layers.append({**box, "color": (color.group(1), float(color.group(2))) if color else None,
                                "surface": None, "img": None})
        elif tag == "img" and self.layers:
            self.layers[-1]["surface"] = a.get("alt")
            size = {k: float(v) for k, v in re.findall(r"(width|height): ([-\d.e+]+)px", st)}
            self.layers[-1]["img"] = size
            self.layers[-1]["has_png"] = a.get("src", "").startswith("data:")


def parse(path: Path):
    p = _Layers()
    p.feed(path.read_text(errors="replace"))
    return p.layers


def describe(layers):
    for i, l in enumerate(layers):
        what = (f"color rgb({l['color'][0]}) a={l['color'][1]}" if l["color"]
                else f"{l['surface']} img={l['img']} png={'yes' if l.get('has_png') else 'no (YUV/video?)'}")
        print(f"  [{i}] x={l.get('left', 0):.0f} y={l.get('top', 0):.0f} "
              f"{l.get('width', 0):.0f}x{l.get('height', 0):.0f}  {what}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("browser")
    ap.add_argument("--prefs", default="{}")
    ap.add_argument("--windowed", action="store_true")
    ap.add_argument("--frames", type=float, default=1.0, help="seconds of dumping")
    a = ap.parse_args()
    before = set(DESKTOP.glob("nativelayerdumps-*"))
    b = browsers.make(a.browser)
    b.ensure_profile(prefs_overlay=json.loads(a.prefs), extensions=("uBOLiteRedux@raymondhill.net",))
    b.launch()
    try:
        wl = run.WORKLOADS["yt-1080p24-windowed" if a.windowed else "yt-1080p24-fullscreen"]
        print("setup:", {k: v for k, v in wl["setup"](b).items() if k in ("state", "quality", "fullscreen", "codecs")})
        time.sleep(8)  # let the player controls fade out
        b.quiesce(int(a.frames) + 3)
        rdp = control.RDP(b.rdp_port)
        rdp.set_pref(PREF, True)
        time.sleep(a.frames)
        rdp.set_pref(PREF, False)
        time.sleep(1)
    finally:
        b.quit()
    dirs = sorted(set(DESKTOP.glob("nativelayerdumps-*")) - before)
    if not dirs:
        print("no dump written")
        return
    try:
        for d in dirs:
            frames = sorted(d.glob("frame-*.html"), key=lambda f: int(f.stem.split("-")[1]))
            print(f"{d.name}: {len(frames)} frames")
            if frames:
                describe(parse(frames[-1]))
                out = run.ROOT / "results" / "raw.noindex" / f"layerdump-{a.browser}-{time.strftime('%Y%m%d-%H%M%S')}.html"
                shutil.copy(frames[-1], out)
                print("kept last frame:", out)
    finally:
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
