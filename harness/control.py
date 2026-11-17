"""Local control server for the MFGA probe extension, plus a minimal Firefox DevTools (RDP)
client used only to load that extension as a temporary add-on.

Why not Marionette: it makes navigator.webdriver true, and YouTube's bot checks then break playback
after ~40 s. The DevTools server does not flag the browser as automated.
"""
from __future__ import annotations

import itertools
import json
import queue
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765


class _State:
    commands: "queue.Queue[dict]" = queue.Queue()
    results: dict = {}
    cond = threading.Condition()
    ids = itertools.count(1)
    last_poll = 0.0
    # Bumped on every browser launch. A long-poll left open by a browser that has since quit must
    # not take commands meant for the next browser.
    gen = 0


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/next"):
            _State.last_poll = time.time()
            my_gen = _State.gen
            cmd = None
            deadline = time.time() + 20
            while cmd is None and time.time() < deadline and _State.gen == my_gen:
                try:
                    cmd = _State.commands.get(timeout=0.25)
                except queue.Empty:
                    pass
            if cmd is not None and _State.gen != my_gen:
                _State.commands.put(cmd)
                cmd = None
            if cmd is None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                return
            body = json.dumps(cmd).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
            except OSError:
                _State.commands.put(cmd)  # the browser went away; give it to the next poller
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        with _State.cond:
            _State.results[data["id"]] = data
            _State.cond.notify_all()
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


_server = None


def ensure_server():
    global _server
    if _server is None:
        _server = ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
        _server.daemon_threads = True
        threading.Thread(target=_server.serve_forever, daemon=True).start()


def reset():
    _State.gen += 1
    while not _State.commands.empty():
        _State.commands.get_nowait()
    _State.last_poll = 0.0


def call(name: str, timeout: float = 90, **args):
    ensure_server()
    cid = next(_State.ids)
    _State.commands.put({"id": cid, "name": name, "args": args})
    deadline = time.time() + timeout
    with _State.cond:
        while cid not in _State.results:
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError(f"probe command {name} timed out")
            _State.cond.wait(left)
        res = _State.results.pop(cid)
    if res.get("error"):
        raise RuntimeError(f"probe {name}: {res['error']}")
    r = res.get("result")
    if isinstance(r, dict) and "__error" in r:
        raise RuntimeError(f"page JS error: {r['__error']}")
    return r


# ---------------- DevTools remote protocol (just enough to install a temporary add-on) ----------------

class RDP:
    def __init__(self, port: int):
        self.port = port

    def _send(self, s, obj):
        data = json.dumps(obj).encode()
        s.sendall(str(len(data)).encode() + b":" + data)

    def _recv(self, s):
        buf = b""
        while b":" not in buf:
            ch = s.recv(1)
            if not ch:
                raise ConnectionError("RDP closed")
            buf += ch
        n_str, rest = buf.split(b":", 1)
        n = int(n_str)
        data = rest
        while len(data) < n:
            data += s.recv(n - len(data))
        return json.loads(data)

    def install_temporary_addon(self, path: str, timeout: float = 60):
        deadline = time.time() + timeout
        while True:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        s.settimeout(30)
        try:
            self._recv(s)  # greeting from root
            self._send(s, {"to": "root", "type": "getRoot"})
            root = self._recv(s)
            actor = root.get("addonsActor")
            if not actor:
                raise RuntimeError(f"no addonsActor in {root}")
            self._send(s, {"to": actor, "type": "installTemporaryAddon", "addonPath": path})
            while True:
                msg = self._recv(s)
                if msg.get("from") == actor:
                    if "error" in msg:
                        raise RuntimeError(f"installTemporaryAddon: {msg}")
                    return msg
        finally:
            s.close()
