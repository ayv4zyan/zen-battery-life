"""Real OS input via the 'MFGA Input' app bundle (which holds the Accessibility permission).

Event-posting commands must run inside the bundle (launched by LaunchServices with `open`), so the
permission check is made against that app and not against whatever launched this script.
Read-only queries (brightness, screen) run the binary directly.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "bin" / "MFGA Input.app"
BIN = ROOT / "bin" / "mfga-input"


def _open_args(*args: str) -> list[str]:
    return ["open", "-W", "-g", "-n", str(APP), "--args", *args]


def ev(*args: str):
    # `open -W` can report "Unable to block on application" when the helper exits very quickly;
    # the event has been posted by then, so the exit status is not meaningful.
    subprocess.run(_open_args(*args), stderr=subprocess.DEVNULL)


def ev_background(*args: str) -> subprocess.Popen:
    return subprocess.Popen(_open_args(*args))


def query(*args: str) -> str:
    return subprocess.run([str(BIN), *args], capture_output=True, text=True).stdout.strip()


def trusted(prompt: bool = False) -> bool:
    with tempfile.NamedTemporaryFile("r", suffix=".txt") as f:
        ev("trusted", *(["--prompt"] if prompt else []), "--out", f.name)
        return Path(f.name).read_text().strip() == "yes"
