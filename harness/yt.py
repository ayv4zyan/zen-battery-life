"""YouTube page helpers (all JS runs in the page; works in every driver)."""
from __future__ import annotations

import time

VIDEOS = {
    # Blender open movies: stable, public, SDR.
    "bbb60": "aqz-KE-bpKQ",     # Big Buck Bunny, 4K 60fps, 10:34
    "sintel": "eRsGyueVLvQ",    # Sintel, 24fps, 14:48
}


def watch_url(key: str) -> str:
    return f"https://www.youtube.com/watch?v={VIDEOS[key]}&t=1s"


STATE_JS = r"""
const p = document.getElementById('movie_player');
const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
if (!p || !v || !p.getPlayerState) return {ready: false};
const q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : {};
let nerds = {};
try { nerds = p.getStatsForNerds ? p.getStatsForNerds() : {}; } catch (e) {}
return {
  ready: true,
  state: p.getPlayerState(),
  quality: p.getPlaybackQuality(),
  t: v.currentTime, paused: v.paused, muted: v.muted, volume: v.volume,
  w: v.videoWidth, h: v.videoHeight,
  rect: (() => { const r = v.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })(),
  total_frames: q.totalVideoFrames, dropped_frames: q.droppedVideoFrames,
  codecs: nerds.codecs, dims_and_frames: nerds.dims_and_frames, resolution: nerds.resolution,
  fullscreen: !!document.fullscreenElement,
  ad: !!document.querySelector('.ad-showing'),
};
"""


def state(b) -> dict:
    return b.js(STATE_JS) or {"ready": False}


def wait_ready(b, timeout=45) -> dict:
    deadline = time.time() + timeout
    s = {}
    while time.time() < deadline:
        s = state(b)
        if s.get("ready") and s.get("w"):
            return s
        time.sleep(1)
    raise RuntimeError(f"player not ready: {s}")


def set_quality(b, q: str):
    b.js(f"const p=document.getElementById('movie_player'); p.setPlaybackQualityRange('{q}','{q}'); return true;")
