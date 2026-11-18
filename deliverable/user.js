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

// Render web content at 60 fps instead of the ProMotion panel's 120 Hz. Safari does this by default
// ("Prefer Page Rendering Updates near 60fps"): in experiment 009 Safari fired ~3,380 scroll events per
// X-scroll run, Zen ~5,840, and Zen with this cap ~3,400 over the same distance.
// X scrolling: 6.79 W -> 5.37 W system (Safari 5.99 W); article scrolling 4.95 -> 4.12 W;
// YouTube 1080p60 unchanged or slightly lower. Hardware vsync stays on; Gecko just uses every 2nd tick.
// Cost: scrolling and animations look like a 60 Hz display, as they do in Safari.
user_pref("gfx.display.max-frame-rate", 60);
