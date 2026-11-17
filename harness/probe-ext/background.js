// Long-polls the harness control server for commands. Between commands it holds one idle
// HTTP request open, so it costs essentially nothing while a Workload is being measured.
// The "sleep" command stops polling entirely for a given number of seconds.
const SERVER = "http://127.0.0.1:8765";

async function activeTab() {
  const [t] = await browser.tabs.query({ active: true, currentWindow: true });
  return t;
}

function waitLoaded(tabId, timeoutMs = 60000) {
  return new Promise((resolve) => {
    const done = () => {
      browser.tabs.onUpdated.removeListener(onUpd);
      clearTimeout(timer);
      resolve(true);
    };
    const onUpd = (id, info) => {
      if (id === tabId && info.status === "complete") done();
    };
    const timer = setTimeout(() => {
      browser.tabs.onUpdated.removeListener(onUpd);
      resolve(false);
    }, timeoutMs);
    browser.tabs.onUpdated.addListener(onUpd);
  });
}

const handlers = {
  async ping() {
    return { ok: true, ua: navigator.userAgent };
  },
  async navigate({ url }) {
    const t = await activeTab();
    const loaded = waitLoaded(t.id);
    await browser.tabs.update(t.id, { url });
    return { loaded: await loaded };
  },
  async exec({ code }) {
    const t = await activeTab();
    // Runs in the content-script world. Page-defined objects are reached via wrappedJSObject.
    const wrapped = `(function(){ const P = (o) => (o && o.wrappedJSObject) || o;
      try { return JSON.stringify((function(){ ${code} })()); }
      catch (e) { return JSON.stringify({__error: String(e)}); } })()`;
    const [res] = await browser.tabs.executeScript(t.id, { code: wrapped });
    return res === undefined ? null : JSON.parse(res);
  },
  async newTab({ url }) {
    const t = await browser.tabs.create({ url, active: true });
    return { loaded: await waitLoaded(t.id) };
  },
  async setWindow({ left, top, width, height }) {
    const w = await browser.windows.getCurrent();
    await browser.windows.update(w.id, { left, top, width, height, state: "normal" });
    return true;
  },
};

let sleepUntil = 0;

async function loop() {
  for (;;) {
    const now = Date.now();
    if (now < sleepUntil) {
      await new Promise((r) => setTimeout(r, sleepUntil - now));
    }
    let cmd;
    try {
      const r = await fetch(`${SERVER}/next`, { cache: "no-store" });
      if (r.status === 204) continue;
      cmd = await r.json();
    } catch (e) {
      await new Promise((r) => setTimeout(r, 1000));
      continue;
    }
    let result, error = null;
    try {
      if (cmd.name === "sleep") {
        sleepUntil = Date.now() + cmd.args.seconds * 1000;
        result = true;
      } else {
        result = await handlers[cmd.name](cmd.args || {});
      }
    } catch (e) {
      error = String(e);
    }
    try {
      await fetch(`${SERVER}/result`, {
        method: "POST",
        body: JSON.stringify({ id: cmd.id, result, error }),
      });
    } catch (e) {}
  }
}

loop();
