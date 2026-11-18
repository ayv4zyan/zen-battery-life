# Setting up the measurement harness

You only need this to **reproduce the measurements**. To just use the fixes, see the README.

The harness takes over the Mac while it runs: it moves the pointer, sends keystrokes and scrolls, and opens and quits browsers.
Run it on a machine you can leave alone, on battery. `harness/preflight.py` checks what it can before every batch of runs.

## 0. Requirements

- An Apple Silicon Mac. The window geometry in `harness/browsers.py` (`WINDOW`) assumes a 14" MacBook Pro at its default resolution; adjust it for other screens.
- Python 3.11 or newer (standard library only), and the Xcode command line tools (`swiftc`).
- Safari, plus Firefox and Zen installed in `/Applications`.

## 1. Let `powermetrics` run without a password

This asks for your password once and allows passwordless sudo only for `/usr/bin/powermetrics`, nothing else:

```bash
echo "$(whoami) ALL=(root) NOPASSWD: /usr/bin/powermetrics" | sudo tee /etc/sudoers.d/powermetrics >/dev/null && sudo chmod 440 /etc/sudoers.d/powermetrics && sudo visudo -cf /etc/sudoers.d/powermetrics
```

To undo it later: `sudo rm /etc/sudoers.d/powermetrics`

## 2. Display

System Settings → Displays:
- **Automatically adjust brightness**: off
- **True Tone**: off
- Brightness: pick a level and keep it for every run

Then record your brightness and volume as the reference, which preflight compares before every batch
(the `results/conditions.json` in this repo holds the original machine's):

```bash
python3 harness/preflight.py pin
```

## 3. Input helper and Accessibility permission

```bash
harness/input/build.sh    # builds bin/MFGA Input.app (MFGA was the project's working name)
```

Then go to System Settings → Privacy & Security → Accessibility and turn on **MFGA Input**.
The scripts send real keyboard and trackpad events (such as `f` for YouTube fullscreen, or two-finger scrolling), so no browser has to run in an automation mode.

## 4. Extensions for the Firefox and Zen profiles

Download the `.xpi` files from addons.mozilla.org into `profiles.noindex/_xpi/`, named by add-on ID:

| File | Add-on | Used by |
|---|---|---|
| `uBOLiteRedux@raymondhill.net.xpi` | [uBlock Origin Lite](https://addons.mozilla.org/firefox/addon/ublock-origin-lite/) | every run |
| `uBlock0@raymondhill.net.xpi` | [uBlock Origin](https://addons.mozilla.org/firefox/addon/ublock-origin/) | experiment 007 only |
| `addon@darkreader.org.xpi` | [Dark Reader](https://addons.mozilla.org/firefox/addon/darkreader/) | experiment 007 only |

## 5. Safari

1. Safari → Settings → Advanced → turn on **Show features for web developers**.
2. Develop menu → **Allow JavaScript from Apple Events**. This lets the scripts check things like whether the video is playing and at what quality.
3. Safari → Settings → Profiles → create a profile named exactly **MFGA**.
4. Settings → Extensions, with the MFGA profile selected → turn on **uBlock Origin Lite** and give it access to all websites.
5. Settings → Websites → Auto-Play → set **youtube.com** to **Allow All Auto-Play**.
6. Open an MFGA window (File → New Window → New MFGA Window) and sign in to **x.com** (only needed for the X Workloads).

Quit Safari before running anything: the harness closes every Safari window when it starts.

## 6. Firefox and Zen

The Clean profiles are created in `profiles.noindex/` on first use. For the X Workloads, sign in to x.com once in each:

```bash
/Applications/Firefox.app/Contents/MacOS/firefox -profile profiles.noindex/firefox-clean -no-remote https://x.com/login
/Applications/Zen.app/Contents/MacOS/zen -profile profiles.noindex/zen-clean -no-remote https://x.com/login
```

Quit both browsers afterwards. Variants that use a named profile (e.g. `zen-ubo`) are copied from `zen-clean`, so they keep the login.

## 7. Run

```bash
python3 harness/experiment.py experiments/008-confirm.json
```

Preflight refuses to start if a browser is running, the Mac is on the charger or below 40 % (unless the experiment sets
`"allow_plugged": true`), Low Power Mode is on, or brightness or volume differ from the pinned reference.
