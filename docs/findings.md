# Findings

Machine: MacBook Pro 14" M4, 16 GB, Liquid Retina XDR (ProMotion 120 Hz), macOS 15.7.
Browsers: Safari (Reference browser), Firefox 158.0.1, Zen 1.23.4b (Gecko 158.0.1).
All numbers are medians of interleaved runs, on battery, brightness 0.46, output muted, Clean profiles with uBlock Origin Lite.
"System" = whole-machine power from the battery's own accumulator (display included). "Chip" = CPU+GPU+ANE from `powermetrics`.

## 1. Zen's translucent window costs ~2 W whenever a page repaints (FIXED by a pref)

Zen wraps the whole browser window in an `NSVisualEffectView` with behind-window blending
(`ZenWindowMaterialView`, `src/widget/cocoa/nsCocoaWindow-mm.patch`, pref `zen.widget.macos.window-vibrancy`, default `true`).
Every frame the page paints, WindowServer re-composites the translucent window over a live blur of the desktop.

| YouTube 1080p60, windowed (exp 002) | System | Chip | WindowServer energy impact |
|---|---|---|---|
| Safari | 5.61 W | 0.57 W | 118 |
| Firefox | 5.20 W | 0.49 W | 28 |
| Zen (stock) | **6.91 W** | **1.32 W** | **473** |
| Zen, `window-vibrancy=false` | 4.87 W | 0.56 W | ~40 |
| Zen, `window-material=0` (vibrancy on) | 6.54 W | 1.33 W | — |

Turning vibrancy off brings Zen from 1.23× Safari (system) to 0.87×. Changing the material does nothing; only removing the blur view helps.
Cost: the window background behind the sidebar/toolbar becomes opaque instead of translucent.

Possible better fix (source): mask the effect view to the non-content regions so the web-content area is composited opaque.

## 2. Fullscreen video: Gecko composites ~2× more than Safari, but the whole-machine gap is small

| 1080p24 fullscreen (exp 003, n=2 each) | System | Chip | WindowServer CPU |
|---|---|---|---|
| Safari | 4.20–4.32 W | 0.20 W | 92 ms/s |
| Firefox | 4.38–4.74 W | 0.33–0.35 W | 176 ms/s |
| Zen | 4.33–4.38 W | 0.32 W | 176 ms/s |

- Same stream in all three browsers (AV1 1080p, hardware decode via VideoToolbox).
- Chip ×1.65 vs Safari, but only ~+0.1 W on the system → ~1.03× system.
- Revealing the fullscreen menu bar once (the workaround from [Bug 1941693](https://bugzilla.mozilla.org/show_bug.cgi?id=1941693)) changes nothing on this machine.
- `layout.frame_rate=60` changes nothing (exp 001).
- Next: dump the native layer tree (`gfx.webrender.debug.dump-native-layer-tree-to-file`) to see which `CheckVideoLowPower` condition fails.

## 3. Breadth: background audio, idle tabs, article scroll (exp 004, n=2)

| Workload | Safari | Firefox | Zen stock | Zen vib-off |
|---|---|---|---|---|
| YouTube audio in background tab, chip | 0.06 W | 0.07 W | **0.27 W** | 0.18 W |
| ↳ WindowServer CPU | 5 ms/s | 5 ms/s | **315 ms/s** | 264 ms/s |
| Idle, 10 tabs, system | 2.11 W | 2.05 W | 1.99 W | 2.06 W |
| Article scroll, system | 4.93 W | 4.89 W | **6.24 W** | 4.85 W |
| ↳ chip | 0.19 W | 0.37 W | 1.08 W | 0.42 W |

- Idle with tabs is at parity in all three browsers. Gecko leaves WindowServer quieter than Safari here (5 vs 102 ms/s).
- Article scrolling: vibrancy again costs Zen ~1.4 W; with it off, Zen matches Safari on system power. Gecko uses ~2× Safari's chip power while scrolling but that does not show up on the system.
- Background audio: Zen keeps WindowServer busy even with the video tab hidden and vibrancy off. Firefox does not, so it is Zen UI.
  Cause (source read): the media card in the sidebar draws an animated music-note sprite (`.zen-media-notes`, `src/zen/media/zen-media-controls.css`,
  90 steps / 3 s, infinite) whenever a tab is playing audio, including while compact mode hides the sidebar.
  System power for this workload is noisy (Safari 4.21 / 2.79 W) because the battery's 60 s accumulator is coarse at ~3 W; trust chip here.

## Method notes (things that bit us)

- Marionette sets `navigator.webdriver`, and YouTube then kills playback ~40 s in ("Something went wrong"). Firefox/Zen are driven through a small probe extension loaded over the DevTools server instead.
- `user.js` only sets keys; prefs a variant set stay in `prefs.js` for later runs. The harness now strips tunable prefs from `prefs.js` before each launch.
- The XDR panel's local dimming makes system power depend on picture content; chip power is the steadier signal, system power is what the battery sees.
