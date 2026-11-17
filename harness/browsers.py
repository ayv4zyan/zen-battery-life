"""Browser drivers. Each driver can: launch, navigate, run JS, focus, set window bounds, quit.

Firefox/Zen are driven over Marionette (with the remote agent's "recommended prefs" OFF, so the
browser behaves like stock). Safari is driven over AppleScript. Anything that needs a genuine user
gesture (fullscreen, play) is sent as a real OS key event by bin/mfga-input.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "bin" / "mfga-input"
PROFILES = ROOT / "profiles.noindex"
XPI_DIR = ROOT / "profiles.noindex" / "_xpi"

# Window used for all windowed workloads (points). Matches the visible area of the 14" panel
# below the menu bar, so every browser gets the same content size.
WINDOW = {"x": 0, "y": 38, "width": 1512, "height": 944}


def osa(script: str, timeout: float = 30) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip()}")
    return r.stdout.strip()


def real_key(key: str, *mods: str):
    subprocess.run([str(INPUT), "key", key, *mods], check=True)


def mouse_park():
    # Bottom-left corner area, inside the window but outside any video player.
    subprocess.run([str(INPUT), "move", "6", "975"], check=True)


# ---------------- Marionette (Firefox, Zen) ----------------

class Marionette:
    def __init__(self, port: int):
        self.port = port
        self.sock = None
        self.msg_id = 0

    def connect(self, timeout: float = 60):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(120)
        self._recv()  # handshake
        self.call("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {"pageLoadStrategy": "eager"}}})

    def _recv(self):
        buf = b""
        while b":" not in buf:
            buf += self.sock.recv(1)
        n_str, rest = buf.split(b":", 1)
        n = int(n_str)
        data = rest
        while len(data) < n:
            data += self.sock.recv(n - len(data))
        return json.loads(data)

    def call(self, name: str, params: dict | None = None):
        self.msg_id += 1
        payload = json.dumps([0, self.msg_id, name, params or {}]).encode()
        self.sock.sendall(str(len(payload)).encode() + b":" + payload)
        while True:
            msg = self._recv()
            if msg[0] == 1 and msg[1] == self.msg_id:
                if msg[2]:
                    raise RuntimeError(f"{name}: {msg[2]}")
                return msg[3]

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None


class GeckoBrowser:
    """Firefox or Zen with a Clean profile."""

    def __init__(self, name: str, app: str, binary: str, port: int, extra_prefs: dict | None = None):
        self.name = name
        self.app = app
        self.binary = binary
        self.port = port
        self.extra_prefs = extra_prefs or {}
        self.profile = PROFILES / f"{name}-clean"
        self.proc = None
        self.m: Marionette | None = None

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
        "datareporting.policy.dataSubmissionPolicyBypassNotification": True,
        "datareporting.healthreport.uploadEnabled": False,
        "toolkit.telemetry.enabled": False,
        "app.update.auto": False,
        "app.normandy.enabled": False,
        "media.autoplay.default": 0,
        "extensions.autoDisableScopes": 0,
        "remote.prefs.recommended": False,
        "zen.welcome-screen.seen": True,
    }

    def ensure_profile(self, prefs_overlay: dict | None = None, extensions: tuple[str, ...] = ()):
        self.profile.mkdir(parents=True, exist_ok=True)
        prefs = {**self.BASE_PREFS, "marionette.port": self.port, **self.extra_prefs, **(prefs_overlay or {})}
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
        self.proc = subprocess.Popen(
            [self.binary, "-profile", str(self.profile), "-no-remote", "--marionette",
             "-remote-allow-system-access", url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.m = Marionette(self.port)
        self.m.connect()
        self.set_window(**WINDOW)

    def navigate(self, url: str):
        self.m.call("WebDriver:Navigate", {"url": url})

    def js(self, script: str):
        """Run `script` as a function body in the page; use `return`."""
        return self.m.call("WebDriver:ExecuteScript", {"script": script, "args": []}).get("value")

    def chrome_js(self, script: str):
        self.m.call("Marionette:SetContext", {"value": "chrome"})
        try:
            return self.m.call("WebDriver:ExecuteScript", {"script": script, "args": []}).get("value")
        finally:
            self.m.call("Marionette:SetContext", {"value": "content"})

    def set_window(self, x, y, width, height):
        self.m.call("WebDriver:SetWindowRect", {"x": x, "y": y, "width": width, "height": height})

    def new_tab(self, url: str):
        h = self.m.call("WebDriver:NewWindow", {"type": "tab", "focus": True})["handle"]
        self.m.call("WebDriver:SwitchToWindow", {"handle": h, "focus": True})
        self.navigate(url)
        return h

    def focus(self):
        subprocess.run(["open", "-a", self.app], check=True)
        time.sleep(0.8)

    def quit(self):
        try:
            if self.m:
                self.m.call("Marionette:Quit", {"flags": ["eForceQuit"]})
        except Exception:  # noqa: BLE001
            pass
        if self.m:
            self.m.close()
        if self.proc:
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.m = None
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
        osa(f'''tell application "System Events" to tell process "Safari"
  set frontmost to true
  click menu item "New {self.PROFILE} Window" of menu 1 of menu item "New Window" of menu "File" of menu bar 1
end tell''')
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
        wrapped = f"JSON.stringify((function(){{ {script} }})())"
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
        return GeckoBrowser("firefox", "Firefox", "/Applications/Firefox.app/Contents/MacOS/firefox", 2828)
    if name == "zen":
        # Mirror the user's Zen layout (compact mode, tabs on the right) so the content area matches.
        return GeckoBrowser("zen", "Zen", "/Applications/Zen.app/Contents/MacOS/zen", 2829,
                            extra_prefs={"zen.view.compact.enable-at-startup": True,
                                         "zen.tabs.vertical.right-side": True})
    raise ValueError(name)
