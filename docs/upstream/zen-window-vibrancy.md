# [Draft — Zen issue] macOS window vibrancy costs ~1.4–2 W whenever page content repaints

**Where:** zen-browser/desktop issues. **Status:** draft, not filed.

## Summary
`ZenWindowMaterialView` (an `NSVisualEffectView`, behind-window blending) wraps the entire window
`contentView` (`src/widget/cocoa/nsCocoaWindow-mm.patch`, pref `zen.widget.macos.window-vibrancy`, default true).
Every frame the web content paints, WindowServer re-composites the window over a live blur of the desktop.

## Measurement (MacBook Pro M4 14", XDR, macOS 15.7; whole-system power from the battery, chip from powermetrics)
| Workload | Zen default | `window-vibrancy=false` | Safari |
|---|---|---|---|
| YouTube 1080p60 windowed, system | 6.91 W | 4.87 W | 5.61 W |
| ↳ chip | 1.32 W | 0.56 W | 0.57 W |
| Article scrolling, system | 6.24 W | 4.85 W | 4.93 W |
| ↳ chip | 1.08 W | 0.42 W | 0.19 W |

`zen.widget.macos.window-material` (any value) does not change the cost; only removing the view does.

## Suggested fix
- Restrict the effect view to the chrome regions (sidebar/toolbar) so the content area is an opaque layer that
  WindowServer can composite without re-blurring, or
- Default vibrancy off on battery / when Low Power Mode is on, and document the cost next to the setting.
