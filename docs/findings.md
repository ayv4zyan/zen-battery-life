# Findings

Machine: MacBook Pro 14" M4, 16 GB, Liquid Retina XDR (ProMotion 120 Hz), macOS 15.7.
Browsers: Safari 27 (Reference browser), Firefox 158.0.1, Zen 1.23.4b (Gecko 158.0.1).
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
- Cause found: YouTube Ambient mode, see section 5.

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

## 4. Zen's media-card note animation (FIXED by userChrome.css)

| YouTube audio in background tab (exp 005, n=2) | Chip | WindowServer CPU | System |
|---|---|---|---|
| Firefox | 0.07 W | 5 ms/s | 3.29 W |
| Zen vib-off | 0.21 W | 264 ms/s | 4.12 W |
| Zen vib-off, notes hidden | **0.07 W** | 12 ms/s | 2.78 W |
| Zen vib-off, `zen.mediacontrols.enabled=false` | 0.07 W | 6 ms/s | 3.57 W |
| Zen vibrancy on, notes hidden | 0.08 W | 13 ms/s | 3.14 W |

- Hiding only `.zen-media-notes` removes the whole cost while keeping the media card. Disabling media controls entirely is no better.
- System power is noisy at ~3 W (battery accumulator); chip and WindowServer are unambiguous.
- Upstream idea for Zen: stop the sprite animation when the sidebar is collapsed/hidden (compact mode), or honour it only on hover.

## 5. YouTube Ambient mode blocks Gecko's low-power fullscreen video (FIXED by userContent.css)

Layer dump (`harness/layerdump.py`, pref `gfx.webrender.debug.dump-native-layer-tree-to-file`) in fullscreen 1080p24, Zen:
- Stock: 12 painted 512×256 tiles covering the screen, then the video on top. The tiles hold a blurred grey copy of the video plus the channel watermark.
  `CheckVideoLowPower` fails at `FailBacking` (the layer under the video is not opaque black), so WindowServer composites every frame.
- DOM (same in Safari and Zen): `#cinematics` holds two 3024×1288 canvases cross-fading (opacity ≈0.15 animating), and the player has `ytp-transparent`.
  This is YouTube's Ambient mode, active in fullscreen too. Safari composites it as CA layers; WebRender re-rasterises the tiles under the video.
- With `#cinematics { display:none }`: layer tree becomes exactly [full-screen black color layer, video].

| exp 006 (n=1, on battery) | Safari | Zen vib-off | Zen vib-off, Ambient hidden |
|---|---|---|---|
| 1080p24 fullscreen, chip / GPU | 0.19 / 0.10 W | 0.32 / 0.18 W | **0.11 / 0.00 W** |
| ↳ system | 4.08 W | 4.75 W | 2.90 W |
| 1080p60 fullscreen, chip | 0.29 W | 0.36 W | **0.14 W** |
| ↳ system | 4.81 W | 5.34 W | 3.97 W |
| 1080p60 windowed, chip | 0.59 W | 0.53 W | **0.26 W** |
| ↳ system | 6.30 W | 5.16 W | 4.74 W |

- Forcing a pure black fullscreen background and hiding the watermark on top of this gave the same chip numbers; hiding Ambient mode is enough.
- This beats Safari (Stretch target) because Safari itself pays for Ambient mode. Turning Ambient mode off in Safari's YouTube settings would likely help Safari too.
- Upstream (Gecko): an opacity cross-fade of a canvas under a fullscreen video forces full-screen tile re-rasterisation; WebKit avoids that.
- Needs confirmation at n≥2 on a charged battery.

## 6. Extension costs in Zen (exp 007, on AC, chip power, n=2)

| chip W | uBO Lite | uBlock Origin | uBO Lite + Dark Reader |
|---|---|---|---|
| YouTube 1080p60 windowed | 0.31 / 0.30 | 0.37 / 0.30 | 0.31 / 0.30 |
| Article scroll | 0.58 / 0.56 | 0.73 / 0.56 | 0.59 / 0.57 |
| Idle, 10 tabs | 0.08 / 0.12 | 0.11 / 0.08 | 0.08 / 0.07 |

- uBlock Origin (full) costs the same as uBO Lite in steady state. Its first session after install was ~20% higher (filter-list compile/update); that recurs only when lists update.
- Dark Reader: no measurable cost on these pages. Verified active in that profile afterwards (Wikipedia rendered with
  `data-darkreader-mode`, 30 Dark Reader style sheets, background rgb(24,26,27)).
- AC chip numbers run higher than on battery (article scroll 0.56 vs 0.42 W in exp 004); compare within an experiment only.
- X scrolling was invalid in this experiment: see Method notes.

## 7. Confirmation on battery: all fixes vs stock Zen vs Safari (exp 008, n=2, 100→89%)

"Final" = `zen.widget.macos.window-vibrancy=false` + userChrome (media notes hidden) + userContent (YouTube Ambient mode hidden), uBO Lite.

| Workload | Safari system | Zen stock | Zen final | final ×Safari | chip: Safari / stock / final |
|---|---|---|---|---|---|
| YouTube 1080p24 fullscreen | 5.20 W | 5.30 W | 3.55 W | **0.68** | 0.24 / 0.36 / 0.15 W |
| YouTube 1080p60 fullscreen | 5.20 W | 5.51 W | 4.69 W | **0.90** | 0.34 / 0.40 / 0.20 W |
| YouTube 1080p60 windowed | 5.92 W | 7.12 W | 4.65 W | **0.79** | 0.63 / 1.40 / 0.29 W |
| YouTube 4K60 fullscreen | 5.04 W | 5.98 W | 5.25 W | 1.04 | 0.37 / 0.46 / 0.33 W |
| YouTube audio, background tab | 4.06 W | 4.63 W | 3.55 W | **0.87** | 0.09 / 0.31 / 0.09 W |
| X scrolling | 6.23 W | 9.31 W | 7.34 W | 1.18 | 1.40 / 3.90 / 2.48 W |
| Article scrolling | 5.76 W | 6.65 W | 5.49 W | **0.95** | 0.24 / 1.18 / 0.63 W |
| Idle, 10 tabs | 2.68 W | 2.48 W | 2.45 W | **0.91** | 0.09 / 0.12 / 0.06 W |

- Parity target (≤1.2× Safari, system) met on every Workload; Stretch target (below Safari) on 6 of 8.
- Remaining gap: X scrolling, chip 1.77× Safari. Per process (CPU ms/s): content 375 vs Safari 359 (same), but Zen GPU process 215 vs WebKit GPU 39,
  and Zen parent 127 vs Safari 54. The compositor side, not page work. Hypothesis: Gecko composites/paints at 120 Hz on ProMotion while Safari
  renders page updates near 60 fps by default. Confirmed and fixed in section 8.

## 8. ProMotion: cap web content at 60 fps like Safari (FIXED by a pref)

`gfx.display.max-frame-rate=60` keeps hardware vsync but makes Gecko's VsyncDispatcher use every 2nd tick on the 120 Hz panel.
Safari already renders page content near 60 fps by default (WebKit "Prefer Page Rendering Updates near 60fps").

| exp 009 (n=2, on battery, 89→79%) | Safari | Zen final | Zen final + 60 fps | +60 fps ×Safari |
|---|---|---|---|---|
| X scrolling, system | 5.99 W | 6.79 W | **5.37 W** | **0.90** |
| ↳ chip | 1.69 W | 2.23 W | **1.47 W** | |
| ↳ scroll events per run | 3,380 | 5,840 | 3,400 | |
| Article scrolling, system | 5.02 W | 4.95 W | **4.12 W** | **0.82** |
| ↳ chip | 0.21 W | 0.50 W | 0.37 W | |
| YouTube 1080p60 windowed, system | 6.25 W | 4.92 W | 4.84 W | 0.77 |
| YouTube 1080p60 fullscreen, system | 5.76 W | 4.53 W | 4.16 W | 0.72 |

- Scroll events fire once per rendered frame. Over the same scroll distance Safari and capped Zen fire the same number;
  stock Zen fires ~1.7× more. That is the direct evidence that Safari renders at ~60 fps here, and that this pref matches it.
- X scrolling goes from the last Workload above Safari to 0.90×. With this, Zen final is below Safari on every Workload
  measured except 4K60 fullscreen (1.04× in exp 008).
- 60 fps video is unaffected (one stray 0.52 W windowed run in the "final" column, otherwise 0.29–0.30 W chip in both).
- Cost: the cap is global. Gecko's compositor runs off the same vsync, so scrolling and Zen's own UI animations also drop to 60 Hz.
  Safari caps only page rendering; its scrolling follows the display. No Gecko pref caps pages only (checked in the Firefox source:
  `gfx.display.max-frame-rate` and `layout.frame_rate` both act on the one global vsync dispatcher).
- A page-only cap (content processes at 60, compositor and UI at 120, as in Safari) needs a Gecko change: thin the vsync ticks
  only where they are forwarded to content processes (`dom/ipc/VsyncParent.cpp`). A local Zen 1.24.2b build with such a patch
  was tried: pages ran at 60 fps while scrolling still composited every 8.3 ms, and X scrolling measured 0.92× Safari (global cap 0.88×,
  no cap 1.02×, one run each). It is not part of this repo because it means maintaining a custom Zen build; it would make a good upstream feature.
- `layout.frame_rate=60` (exp 001) did nothing for video; it swaps in a software timer. `gfx.display.max-frame-rate` is the one that works.

## 9. ChatGPT, a reply streaming in: at parity, no fix needed (exp 010, n=2, on battery)

Workload `chatgpt-stream`: signed-out chatgpt.com, one tab. An in-page loop sends the next prompt from a fixed list
(prose + code block + table) whenever a reply finishes, so text streams through the whole window (3 replies per window).

| exp 010 | system | ×Safari | chip | cpu / gpu | WindowServer | streamed |
|---|---|---|---|---|---|---|
| Safari | 10.20 W | | 4.39 W | 4.32 / 0.07 W | 132 ms/s | 307–333 chars/s |
| Zen stock | 9.46 W | **0.93** | 4.20 W | 4.09 / 0.11 W | 99 ms/s | 260–318 chars/s |
| Zen final + 60 fps | 9.62 W | **0.94** | 4.53 W | 4.49 / 0.03 W | 55 ms/s | 243–322 chars/s |

- Parity target met with or without the fixes. Chip is 0.96–1.03× Safari, within run-to-run spread.
- This is the most expensive Workload measured (~4.4 W chip in both browsers), and it is almost all page CPU work
  (the page's content process uses 760–940 ms/s of CPU in both browsers, i.e. nearly one core). Browser compositing is a small share, so vibrancy and the 60 fps cap
  only show in WindowServer (99 → 55 ms/s), not in system power.
- A first 40 s smoke run showed Zen at 1.38× Safari chip. It did not hold up at 125 s, n=2.
- Stream speed varies between runs (243–333 chars/s, set by OpenAI's servers), and chip power follows it.
  The runner records characters streamed inside the window and rejects runs where the stream stalled.

## Method notes (things that bit us)

- Marionette sets `navigator.webdriver`, and YouTube then kills playback ~40 s in ("Something went wrong"). Firefox/Zen are driven through a small probe extension loaded over the DevTools server instead.
- `user.js` only sets keys; prefs a variant set stay in `prefs.js` for later runs. The harness now strips tunable prefs from `prefs.js` before each launch.
- The XDR panel's local dimming makes system power depend on picture content; chip power is the steadier signal, system power is what the battery sees.
- Synthetic trackpad scrolls must start like a real trackpad (MayBegin, then Began carrying movement). A zero-delta Began makes Gecko drop
  the whole gesture on pages whose root has `overscroll-behavior: none` (X), so every X-scroll run before f1fd8b8 measured an unscrolled page.
  Scroll Workloads now count page scroll events and reject runs that did not scroll.
