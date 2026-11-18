# zen-battery-life

Making [Zen Browser](https://zen-browser.app/) (Firefox-based) on an Apple Silicon MacBook use as little power as Safari, or less.
Everything here was **measured**, on battery, against Safari. The result is one `user.js` and two small CSS files that you can drop into your Zen profile.

## The situation

I use Zen every day on a MacBook Pro 14" (M4, 120 Hz ProMotion display), and it drained the battery noticeably faster than Safari.
My day is mostly YouTube (fullscreen and windowed), scrolling X, ChatGPT and a handful of idle tabs.
Rather than switch browsers, I wanted to find out *why* Zen costs more and fix it.

The rules:
- **Measure, don't guess.** Each fix had to lower power in a scripted, repeatable test that ran interleaved against Safari on the same machine.
- **Target:** Zen at most 1.2× Safari's power on every Workload, and ideally below Safari.
- **Allowed tradeoffs:** anything Safari already does by default, as long as it never loses tabs or input.
- **Settings before source code.** I tried a source patch once (see below) and dropped it, because nobody wants to rebuild their browser on every update.

## Results

Whole-machine power while running each Workload, as a multiple of Safari's in the same experiment (below 1.00 means Zen uses less than Safari).
On battery, 2 interleaved runs per cell, 125 s each.

| Workload | Stock Zen | Zen + 3 fixes | Zen + 3 fixes + 60 fps cap |
|---|---|---|---|
| YouTube 1080p24, fullscreen | 1.02 | **0.68** | |
| YouTube 1080p60, fullscreen | 1.06 | **0.90** | **0.72** |
| YouTube 1080p60, windowed | 1.20 | **0.79** | **0.77** |
| YouTube 4K60, fullscreen | 1.19 | 1.04 | |
| YouTube audio in a background tab | 1.14 | **0.87** | |
| X feed scrolling | 1.49 | 1.18 | **0.90** |
| Wikipedia article scrolling | 1.15 | **0.95** | **0.82** |
| Idle, 10 tabs | 0.93 | **0.91** | |
| ChatGPT, a reply streaming in | 0.93 | | 0.94 |

The middle column comes from experiment 008 and the right column from experiment 009. A blank cell means that combination wasn't measured.
In absolute terms, scrolling X went from 9.3 W (stock Zen) to about 5.4 W (all fixes); Safari used 6.0–6.2 W.
Full tables, chip power, per-process breakdowns and caveats are in [docs/findings.md](docs/findings.md).

## The fixes

| # | Fix | What it fixes | Cost |
|---|---|---|---|
| 1 | `zen.widget.macos.window-vibrancy = false` (`user.js`) | Zen's translucent window makes macOS re-blur the desktop behind it on every frame a page draws: about +2 W during windowed video and +1.4 W while scrolling | The window background behind the sidebar and toolbar becomes opaque |
| 2 | Hide `.zen-media-notes` (`chrome/userChrome.css`) | The sidebar media card plays an animated music-note sprite for as long as any tab has audio, even when the sidebar is hidden. Background YouTube audio: chip 0.21 → 0.07 W | None: the media card and its buttons stay |
| 3 | Hide YouTube's Ambient mode (`chrome/userContent.css`) | YouTube's Ambient glow cross-fades two blurred copies of the video behind the player. Gecko repaints the whole screen for it, which keeps macOS out of its low-power video mode. 1080p24 fullscreen: chip 0.32 → 0.11 W | No coloured glow around the player |
| 4 | `gfx.display.max-frame-rate = 60` (`user.js`, optional) | Gecko renders at the panel's 120 Hz. Safari renders pages at about 60 fps. Scrolling: −17 to −21 % | **All of Zen runs at 60 Hz, scrolling included.** Safari limits only page rendering. Delete this line if you prefer 120 Hz |

Without fix 3's file, you can get the same effect by turning off Ambient mode in YouTube's player menu (gear icon → Ambient mode).

## Install

1. In Zen, open `about:support` and click **Profile Folder → Open Folder**. Then quit Zen with Cmd-Q.
2. Copy [`deliverable/user.js`](deliverable/user.js) into that folder. If a `user.js` already exists, append these lines to it instead.
3. Copy [`deliverable/chrome/userChrome.css`](deliverable/chrome/userChrome.css) and, optionally, [`userContent.css`](deliverable/chrome/userContent.css) into the profile's `chrome/` folder (create it if it's missing). Leave any existing `zen-themes*` files there alone; those are your Zen Mods. If you already have these CSS files, append to them.
4. Start Zen. In `about:config`, check that `zen.widget.macos.window-vibrancy` is `false`, `toolkit.legacyUserProfileCustomizations.stylesheets` is `true`, and (if you kept it) `gfx.display.max-frame-rate` is `60`.

The files live in your profile, so they survive Zen updates. The targets of fixes 1 and 2 still exist in Zen 1.24.2b.

**To undo:** delete the files, then reset the same prefs in `about:config`. Deleting `user.js` alone isn't enough, because Zen keeps the values it already applied.

## What did not help, or wasn't needed

- `layout.frame_rate = 60`: it swaps Gecko onto a software timer and changed nothing.
- Changing `zen.widget.macos.window-material`: only turning vibrancy off helps.
- Revealing the menu bar once in fullscreen, the known workaround from [Bug 1941693](https://bugzilla.mozilla.org/show_bug.cgi?id=1941693): no effect on this machine.
- Turning off Zen's media controls entirely: no better than hiding just the notes.
- uBlock Origin vs uBlock Origin Lite: the same in steady state. Dark Reader: no measurable cost.
- ChatGPT streaming: already at parity. The cost is the page's own JavaScript, about one CPU core in both browsers.
- **A page-only 60 fps cap** (pages at 60, scrolling and UI at 120, like Safari) can't be done with a pref; it needs a small Gecko change.
  A patched local build worked (X scrolling at 0.92× Safari, with scrolling still at 120 Hz), but it was dropped because it means maintaining a custom Zen build.
  It would make a good upstream feature.

Upstream write-ups (not filed yet) are in [docs/upstream/](docs/upstream/): Zen's vibrancy cost, the media-notes animation, and Gecko's handling of YouTube's Ambient mode.

## How it was measured

- **Machine:** MacBook Pro 14" M4, 16 GB, macOS 15.7, brightness fixed at about 46 %, sound muted, on battery.
- **Browsers:** Safari 27 (Reference browser), Firefox 158.0.1, Zen 1.23.4b (Gecko 158.0.1). Each used a Clean profile with uBlock Origin Lite.
- **Power:** whole-machine ("system") power from the battery's own energy counter, so it includes the display. Chip power (CPU + GPU) and per-process CPU come from `powermetrics`.
- **Workloads** are scripted: YouTube at fixed qualities, trackpad-style scrolling on X and Wikipedia, idle tabs, and ChatGPT replies streaming. Browsers are interleaved (A B C, A B C), and each run checks it really did the work: the video kept playing, the page scrolled, the text kept streaming. Runs that fail the check are rejected.
- **Automation:** real OS input comes from a small helper app (`harness/input/`). Firefox and Zen are driven by a tiny WebExtension over the DevTools protocol, not WebDriver, because YouTube stops playback when it detects `navigator.webdriver`.

**Caveats:** one machine; two runs per cell; whole-machine power is noisy (about ±0.3 W) at low loads; X and YouTube change over time.
Your numbers will differ, but the causes (vibrancy, the notes animation, Ambient mode, 120 Hz rendering) are general to Zen on macOS.

## Reproduce

Follow [SETUP.md](SETUP.md), then for example:

```sh
python3 harness/experiment.py experiments/008-confirm.json   # stock vs fixed Zen vs Safari, every Workload
```

Each experiment file lists its Workloads and variants (browser + prefs). Results are appended to `results/runs.jsonl`; the logs of all experiments used here are in `results/`.

## Layout

| Path | Contents |
|---|---|
| `deliverable/` | The fixes to install |
| `docs/findings.md` | Every experiment, with numbers and root causes |
| `docs/upstream/` | Draft bug reports for Zen and Mozilla |
| `experiments/` | Experiment definitions (001–010) |
| `harness/` | Measurement harness (Python standard library only, plus a Swift input helper and a probe WebExtension) |
| `results/` | Run logs and `runs.jsonl` (one line per measured run) |
| `GLOSSARY.md` | Terms used throughout (Workload, Power cost, Parity target, …) |

## License

[MIT](LICENSE). The research was done together with [Claude Code](https://claude.com/claude-code).
