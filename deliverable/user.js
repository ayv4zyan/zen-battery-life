// Make Firefox Great Again: Zen power settings.
// Each line below was measured on an M4 MacBook Pro (see docs/findings.md) and is kept only if it
// lowered Power cost without breaking Safari parity.

// Zen's translucent (vibrancy) window background makes WindowServer re-blur the desktop behind the
// window on every frame the page paints. YouTube 1080p60 windowed: 6.9 W -> 4.9 W system,
// 1.32 W -> 0.56 W chip (experiment 002). The window background becomes opaque.
user_pref("zen.widget.macos.window-vibrancy", false);

// Lets Zen load chrome/userChrome.css, which hides the media card's endless music-note animation
// (background audio: chip 0.21 W -> 0.07 W, experiment 005). Copy deliverable/chrome/ into the profile.
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
