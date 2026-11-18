"""ChatGPT page helpers (signed out; all JS runs in the page and works in every driver).

The chat Workload keeps a reply streaming for the whole measurement window: a small in-page loop
sends the next prompt from a fixed list each time a reply finishes. The harness does not touch the
page while recording, so the loop records its own progress ([time, characters on page] samples),
and the runner works out how much text streamed inside the recording window.
"""
from __future__ import annotations

import json
import time

URL = "https://chatgpt.com/"

# Same shape every time (prose + a code block + a table) so every reply exercises the same rendering:
# markdown, syntax highlighting, tables, and auto-scroll to the bottom while text arrives.
PROMPTS = [
    "Explain how a hash map works, with a Python implementation and a comparison table of collision strategies.",
    "Explain how TCP congestion control works, with a Python simulation of AIMD and a table comparing Reno, CUBIC and BBR.",
    "Explain how garbage collectors work, with a small mark-and-sweep implementation in JavaScript and a table comparing GC strategies.",
    "Explain how B-trees work, with a Python implementation of search and insert and a table comparing B-trees, B+ trees and LSM trees.",
    "Explain how public-key cryptography works, with a toy RSA implementation in Python and a table comparing RSA, ECC and post-quantum schemes.",
    "Explain how a CPU cache works, with a C example of cache-friendly and cache-unfriendly loops and a table of typical cache latencies.",
    "Explain how a regular expression engine works, with a small backtracking matcher in Python and a table comparing NFA and DFA engines.",
    "Explain how database indexes work, with SQL examples and a Python sketch of an index lookup, plus a table comparing index types.",
]

# Selectors of the signed-out chatgpt.com app (checked 2026-11-18).
COMPOSER = "#mobile-composer-prompt"
SEND = 'button[aria-label="Send message"]'
STOP = 'button[aria-label="Stop generating"]'

# Tick once a second. No layout reads (no innerText / getBoundingClientRect), so the loop itself
# costs nothing measurable and the same in every browser.
LOOP_JS = r"""
if (window.__mfgaChat) return {already: true};
const PROMPTS = %(prompts)s, COMPOSER = %(composer)s, SEND = %(send)s, STOP = %(stop)s;
const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
const st = window.__mfgaChat = {sent: 0, finished: 0, ends: [], samples: [], errors: [], phase: 'idle', at: Date.now()};
const root = () => document.querySelector('main') || document.body;
let last = -1;
function send() {
  const ta = document.querySelector(COMPOSER);
  if (!ta) { st.errors.push([Date.now(), 'no composer']); return; }
  ta.focus();
  setValue.call(ta, PROMPTS[st.sent %% PROMPTS.length]);
  ta.dispatchEvent(new Event('input', {bubbles: true}));
  st.phase = 'sending'; st.at = Date.now();
  setTimeout(() => {
    const b = document.querySelector(SEND);
    if (!b) { st.errors.push([Date.now(), 'no send button']); st.phase = 'idle'; return; }
    b.click(); st.sent++; st.phase = 'waiting'; st.at = Date.now();
  }, 300);
}
setInterval(() => {
  const now = Date.now();
  const len = root().textContent.length;
  if (len !== last) { st.samples.push([now, len]); last = len; }
  const streaming = !!document.querySelector(STOP);
  if (st.phase === 'waiting' && streaming) { st.phase = 'streaming'; st.at = now; }
  else if (st.phase === 'waiting' && now - st.at > 45000) { st.errors.push([now, 'reply did not start']); st.phase = 'idle'; st.at = now; }
  else if (st.phase === 'streaming' && !streaming) { st.finished++; st.ends.push(now); st.phase = 'idle'; st.at = now; }
  else if (st.phase === 'idle' && now - st.at >= 2000) send();
}, 1000);
send();
return {started: true};
"""

STATE_JS = r"""
const st = window.__mfgaChat;
if (!st) return {running: false};
return {running: true, sent: st.sent, finished: st.finished, phase: st.phase, errors: st.errors,
        ends: st.ends, samples: st.samples, href: location.href};
"""


def start(b) -> dict:
    """Load a new chat and start the prompt loop. Returns once the first reply is streaming."""
    b.navigate(URL)
    deadline = time.time() + 30
    while time.time() < deadline:
        if b.js(f"return !!document.querySelector({json.dumps(COMPOSER)})"):
            break
        time.sleep(1)
    else:
        raise RuntimeError("ChatGPT composer not found")
    time.sleep(2)
    b.js(LOOP_JS % {"prompts": json.dumps(PROMPTS), "composer": json.dumps(COMPOSER),
                    "send": json.dumps(SEND), "stop": json.dumps(STOP)})
    deadline = time.time() + 45
    s = {}
    while time.time() < deadline:
        s = state(b)
        if s.get("phase") == "streaming" or s.get("finished"):
            return {k: v for k, v in s.items() if k != "samples"}
        if s.get("errors"):
            break
        time.sleep(1)
    raise RuntimeError(f"ChatGPT reply did not start: { {k: v for k, v in s.items() if k != 'samples'} }")


def state(b) -> dict:
    return b.js(STATE_JS) or {"running": False}


def streamed_in(samples: list, t0_ms: float, t1_ms: float) -> int:
    """Characters added to the page between t0 and t1 (from the loop's [time, length] samples)."""
    def at(t):
        n = 0
        for ts, length in samples:
            if ts > t:
                break
            n = length
        return n
    return at(t1_ms) - at(t0_ms)
