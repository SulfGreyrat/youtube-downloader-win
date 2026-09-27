// Popup logic: read the active tab's URL, POST it to the local agent,
// poll /status/<id> until done/error.

const AGENT = "http://127.0.0.1:8756";

const titleEl = document.getElementById("title");
const btn = document.getElementById("downloadBtn");
const statusEl = document.getElementById("status");
const bar = document.getElementById("bar");

function isYouTubeVideoUrl(url) {
  try {
    const u = new URL(url);
    if (!/(^|\.)youtube\.com$/.test(u.hostname) && u.hostname !== "youtu.be") {
      return false;
    }
    if (u.hostname === "youtu.be") return u.pathname.length > 1;
    return u.pathname === "/watch" && u.searchParams.has("v");
  } catch {
    return false;
  }
}

function setStatus(text, cls) {
  statusEl.textContent = text;
  statusEl.className = cls || "";
}

async function pingAgent() {
  try {
    const res = await fetch(`${AGENT}/ping`, { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

async function pollStatus(id) {
  bar.style.display = "block";
  const start = Date.now();
  const timeoutMs = 30 * 60 * 1000; // 30 min ceiling for very large videos
  while (Date.now() - start < timeoutMs) {
    let data;
    try {
      const res = await fetch(`${AGENT}/status/${id}`);
      data = await res.json();
    } catch {
      setStatus("Lost connection to the local agent.", "error");
      return;
    }
    if (data.status === "downloading") {
      const pct = data.pct ?? 0;
      bar.value = pct;
      setStatus(`Downloading... ${pct}%`);
    } else if (data.status === "merging") {
      setStatus("Merging video + audio...");
    } else if (data.status === "done") {
      bar.value = 100;
      setStatus(`Saved:\n${data.path}`, "done");
      return;
    } else if (data.status === "error") {
      setStatus(`Error: ${data.error}`, "error");
      return;
    } else {
      setStatus("Queued...");
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  setStatus("Timed out waiting for the download to finish.", "error");
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";

  if (!isYouTubeVideoUrl(url)) {
    titleEl.textContent = "Open a YouTube video tab first.";
    return;
  }
  titleEl.textContent = url;

  const agentUp = await pingAgent();
  if (!agentUp) {
    setStatus(
      "Local helper app is not running. It should start automatically at " +
        "login — you can also launch it manually.",
      "error"
    );
    return;
  }

  btn.disabled = false;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    setStatus("Starting download...");
    try {
      const res = await fetch(`${AGENT}/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (data.error) {
        setStatus(`Error: ${data.error}`, "error");
        btn.disabled = false;
        return;
      }
      await pollStatus(data.id);
    } catch (err) {
      setStatus(`Request failed: ${err}`, "error");
    }
    btn.disabled = false;
  });
}

init();
