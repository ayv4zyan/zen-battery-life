# One-time setup (done by you, not by scripts)

These steps change system or browser settings, so they are yours to do. `harness/preflight.py` checks what it can before every batch of runs.

## 1. Let `powermetrics` run without a password

Run this in a terminal. It asks for your password once, and it allows passwordless sudo only for `/usr/bin/powermetrics`, nothing else:

```bash
echo "$(whoami) ALL=(root) NOPASSWD: /usr/bin/powermetrics" | sudo tee /etc/sudoers.d/powermetrics >/dev/null && sudo chmod 440 /etc/sudoers.d/powermetrics && sudo visudo -cf /etc/sudoers.d/powermetrics
```

To undo it later: `sudo rm /etc/sudoers.d/powermetrics`

## 2. Display

System Settings → Displays:
- **Automatically adjust brightness**: off
- **True Tone**: off
- Brightness: pick a level you're comfortable with (about half is fine) and leave it there for the whole project

## 3. Accessibility permission (for keystrokes and scrolling)

System Settings → Privacy & Security → Accessibility → turn on **Claude**.
The scripts send real keyboard and trackpad events (like pressing `f` for YouTube fullscreen, or two-finger scrolling), so no browser needs an automation mode switched on.

## 4. Safari

1. Safari → Settings → Advanced → turn on **Show features for web developers**.
2. Develop menu → **Allow JavaScript from Apple Events** (lets the scripts check things like "is the video playing, at what quality").
3. Safari → Settings → Profiles → create a profile named exactly **MFGA**.
4. Settings → Extensions, with the MFGA profile selected → turn on **uBlock Origin Lite**, and give it access to all websites.
5. Settings → Websites → Auto-Play → set **youtube.com** to **Allow All Auto-Play**.
6. Open a MFGA window (File → New Window → New MFGA Window) and sign in to **x.com**.

## 5. Firefox and Zen

Nothing to do yet. Clean profiles are created by the scripts. When they are ready, I'll open each one so you can sign in to x.com.
