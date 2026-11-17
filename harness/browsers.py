"""Browser drivers. Each driver can: launch, navigate, run JS, focus, set window bounds, quit.

Firefox/Zen are driven by the MFGA probe extension (see control.py; no WebDriver, so pages do not
see an automated browser). Safari is driven over AppleScript. Anything that needs a genuine user
gesture (fullscreen, play) is sent as a real OS key event by bin/mfga-input.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

import control
import inputctl

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles.noindex"
XPI_DIR = ROOT / "profiles.noindex" / "_xpi"
PROBE_EXT = ROOT / "harness" / "probe-ext"

# Window used for all windowed workloads (points). Matches the visible area of the 14" panel
# below the menu bar, so every browser gets the same content size.
WINDOW = {"x": 0, "y": 38, "width": 1512, "height": 944}


def osa(script: str, timeout: float = 30) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip()}")
    return r.stdout.strip()


def real_key(key: str, *mods: str):
    inputctl.ev("key", key, *mods)


def mouse_park():
    # Bottom-left corner area, inside the window but outside any video player.
    inputctl.ev("move", "6", "975")


# ---------------- Firefox, Zen (probe extension) ----------------

class GeckoBrowser:
    """Firefox or Zen with a Clean profile, controlled through the MFGA probe extension."""

    def __init__(self, name: str, app: str, bundle_id: str, binary: str, rdp_port: int,
                 extra_prefs: dict | None = None):
        self.name = name
        self.app = app
        self.bundle_id = bundle_id
        self.binary = binary
        self.rdp_port = rdp_port
        self.extra_prefs = extra_prefs or {}
        self.profile = PROFILES / f"{name}-clean"
        self.proc = None

    # Prefs that only make a scripted, repeatable run possible. Nothing here changes rendering,
    # media, or scheduling behaviour. (Telemetry off in both, to remove upload noise.)
    BASE_PREFS = {
        "browser.shell.checkDefaultBrowser": False,
        "browser.aboutwelcome.enabled": False,
        "browser.startup.homepage_override.mstone": "ignore",
        "startup.homepage_welcome_url": "",
        "startup.homepage_welcome_url.additional": "",
        "browser.startup.page": 0,
        "browser.sessionstore.resume_from_crash": False,
        "browser.tabs.warnOnClose": False,
        "browser.warnOnQuit": False,
        "browser.warnOnQuitShortcut": False,
        "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
        "datareporting.healthreport.uploadEnabled": False,
        "toolkit.telemetry.enabled": False,
        "app.update.auto": False,
        "app.normandy.enabled": False,
        "media.autoplay.default": 0,
        "extensions.autoDisableScopes": 0,
        "zen.welcome-screen.seen": True,
        # DevTools server, used once per launch to load the probe extension.
        "devtools.debugger.remote-enabled": True,
        "devtools.chrome.enabled": True,
        "devtools.debugger.prompt-connection": False,
    }

    def ensure_profile(self, prefs_overlay: dict | None = None, extensions: tuple[str, ...] = ()):
        self.profile.mkdir(parents=True, exist_ok=True)
        prefs = {**self.BASE_PREFS, **self.extra_prefs, **(prefs_overlay or {})}
        lines = [f'user_pref({json.dumps(k)}, {json.dumps(v)});' for k, v in prefs.items()]
        (self.profile / "user.js").write_text("\n".join(lines) + "\n")
        ext_dir = self.profile / "extensions"
        ext_dir.mkdir(exist_ok=True)
        wanted = set()
        for ext_id in extensions:
            src = XPI_DIR / f"{ext_id}.xpi"
            dst = ext_dir / f"{ext_id}.xpi"
            wanted.add(dst.name)
            if not dst.exists():
                shutil.copy(src, dst)
        for f in ext_dir.glob("*.xpi"):
            if f.name not in wanted:
                f.unlink()

    def launch(self, url: str = "about:blank"):
        control.ensure_server()
        control.reset()
        self.proc = subprocess.Popen(
            [self.binary, "-profile", str(self.profile), "-no-remote",
             "-start-debugger-server", str(self.rdp_port), url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        control.RDP(self.rdp_port).install_temporary_addon(str(PROBE_EXT))
        control.call("ping", timeout=30)
        self.set_window(**WINDOW)

    def navigate(self, url: str):
        control.call("navigate", url=url)

    def js(self, script: str):
        """Run `script` as a function body in the page (content-script world); use `return`.
        Wrap page-defined objects with P(...) to reach their page methods."""
        return control.call("exec", code=script)

    def set_window(self, x, y, width, height):
        control.call("setWindow", left=x, top=y, width=width, height=height)

    def new_tab(self, url: str):
        control.call("newTab", url=url)

    def quiesce(self, seconds: int):
        """Stop the probe from polling while a Workload is measured."""
        control.call("sleep", seconds=seconds)

    def focus(self):
        subprocess.run(["open", "-b", self.bundle_id], check=True)
        time.sleep(0.8)

    def quit(self):
        try:
            osa(f'tell application id "{self.bundle_id}" to quit', timeout=20)
        except Exception:  # noqa: BLE001
            pass
        if self.proc:
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.proc = None


# ---------------- Safari ----------------

class Safari:
    name = "safari"
    app = "Safari"
    PROFILE = "MFGA"

    def launch(self, url: str = "about:blank"):
        subprocess.run(["open", "-a", "Safari"], check=True)
        time.sleep(2)
        # Close whatever opened by default, then open a window in the MFGA profile.
        osa('tell application "Safari" to close every window')
        osa('tell application "Safari" to activate')
        inputctl.ev("menu", "com.apple.Safari", "File", "New Window", f"New {self.PROFILE} Window")
        time.sleep(1.5)
        self.set_window(**WINDOW)
        self.navigate(url)

    def navigate(self, url: str):
        osa(f'tell application "Safari" to set URL of current tab of front window to {json.dumps(url)}')
        # Wait for load.
        for _ in range(120):
            time.sleep(0.5)
            try:
                if self.js("return document.readyState") in ("interactive", "complete"):
                    return
            except RuntimeError:
                pass

    def js(self, script: str):
        wrapped = f"JSON.stringify((function(){{ const P = (o) => o; {script} }})())"
        out = osa(f'tell application "Safari" to do JavaScript {json.dumps(wrapped)} in current tab of front window')
        return json.loads(out) if out and out != "missing value" else None

    def set_window(self, x, y, width, height):
        osa(f'tell application "Safari" to set bounds of front window to {{{x}, {y}, {x + width}, {y + height}}}')

    def new_tab(self, url: str):
        osa(f'''tell application "Safari" to tell front window
  set t to make new tab with properties {{URL:{json.dumps(url)}}}
  set current tab to t
end tell''')
        time.sleep(2)

    def quiesce(self, seconds: int):
        pass

    def focus(self):
        osa('tell application "Safari" to activate')
        time.sleep(0.8)

    def quit(self):
        try:
            osa('tell application "Safari" to close every window')
            osa('tell application "Safari" to quit')
        except RuntimeError:
            pass
        for _ in range(40):
            if subprocess.run(["pgrep", "-x", "Safari"], capture_output=True).returncode != 0:
                return
            time.sleep(0.5)


def make(name: str):
    if name == "safari":
        return Safari()
    if name == "firefox":
        return GeckoBrowser("firefox", "Firefox", "org.mozilla.firefox",
                            "/Applications/Firefox.app/Contents/MacOS/firefox", 6080)
    if name == "zen":
        # Mirror the user's Zen layout (compact mode, tabs on the right) so the content area matches.
        return GeckoBrowser("zen", "Zen", "app.zen-browser.zen",
                            "/Applications/Zen.app/Contents/MacOS/zen", 6081,
                            extra_prefs={"zen.view.compact.enable-at-startup": True,
                                         "zen.tabs.vertical.right-side": True})
    raise ValueError(name)
