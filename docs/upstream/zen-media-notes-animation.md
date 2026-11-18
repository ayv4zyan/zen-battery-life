# [Draft — Zen issue] Media card note animation keeps WindowServer busy while audio plays (even with the sidebar hidden)

**Where:** zen-browser/desktop issues. **Status:** draft, not filed.

## Summary
While any tab plays audio, the sidebar media card runs `.zen-media-notes::before`
(`animation: zen-note-sprite 3s steps(90) infinite`, `src/zen/media/zen-media-controls.css`).
That is a 30 fps repaint for as long as audio plays, including in compact mode when the sidebar
is collapsed and the card is not visible.

## Measurement (MacBook Pro M4, macOS 15.7, Zen 1.23.4b, YouTube audio in a background tab, example.com in front)
| | Chip power | WindowServer CPU |
|---|---|---|
| Firefox 158 | 0.07 W | 5 ms/s |
| Zen (vibrancy off) | 0.21 W | 264 ms/s |
| Zen + `.zen-media-notes { display:none }` | 0.07 W | 12 ms/s |

With window vibrancy on (default) the cost is higher (0.27 W chip, 315 ms/s WindowServer), since each
repaint also re-composites the translucent window.

## Suggested fix
- Don't run the animation when the media card isn't visible (sidebar collapsed / compact mode hidden).
- Consider a pref or `prefers-reduced-motion`-like opt-out (only the latter exists today), or a slower/static indicator.
