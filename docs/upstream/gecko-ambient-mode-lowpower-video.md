# [Draft — Bugzilla, Core :: Graphics: WebRender] Animated canvas opacity under fullscreen video re-rasterises picture-cache tiles every frame (YouTube Ambient mode); blocks macOS detached video

**Status:** draft, not filed. Related: Bug 1941693.

## Summary
YouTube's "Ambient mode" (dark theme; default on, also in fullscreen) places two large canvases (`#cinematics`,
~2× viewport) behind a transparent player and cross-fades their opacity continuously.
On macOS, WebRender re-rasterises the picture-cache tiles under and around the video every frame,
and the native layer tree is [12 content tiles, video], so `CheckVideoLowPower` fails with `FailBacking`.
Safari renders the same page at about half Gecko's chip power.

## Steps
1. macOS, dark theme on YouTube (Ambient mode on — the default), signed out.
2. Play a 1080p video fullscreen (e.g. https://www.youtube.com/watch?v=eRsGyueVLvQ).
3. Set `gfx.webrender.debug.dump-native-layer-tree-to-file` = true for one second.

## Observed
- Layer dump: 12 tiles (512×256 pt) covering the screen holding a blurred copy of the video, then the video layer.
- powermetrics, 1080p24 fullscreen: Gecko 0.32 W chip (GPU 0.18 W), WindowServer 174 ms/s; Safari 0.19 W, 92 ms/s.
- Hiding `#cinematics` (user stylesheet): layer tree becomes [full-screen black color layer, video]; chip 0.11 W, GPU ≈0 W.

| chip W (M4, macOS 15.7, Firefox/Zen on Gecko 158) | Safari | Gecko | Gecko, Ambient hidden |
|---|---|---|---|
| 1080p24 fullscreen | 0.19 | 0.32 | 0.11 |
| 1080p60 fullscreen | 0.29 | 0.36 | 0.14 |
| 1080p60 windowed | 0.59 | 0.53 | 0.26 |

## Expected
An opacity-only animation of a canvas should not require re-rasterising the tiles it overlaps every frame —
e.g. promote such canvases to their own compositor surface / native layer with opacity applied at
composite time (what Core Animation does for Safari).
