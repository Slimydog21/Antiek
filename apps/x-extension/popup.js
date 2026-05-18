// Popup logic — runs when the toolbar icon is clicked.
// Reads the API URL + investigation id from chrome.storage,
// asks the content script to extract the current thread,
// posts it to /sources/twitter, and shows the result.

const DEFAULTS = {
  apiUrl: "https://api.antiek.ai",
  investigationId: "__operator__",
};

const apiInput = document.getElementById("api-url");
const invInput = document.getElementById("inv-id");
const captureBtn = document.getElementById("capture");
const statusEl = document.getElementById("status");

function setStatus(kind, text) {
  statusEl.className = `row ${kind}`;
  statusEl.textContent = text;
}

async function loadSettings() {
  const stored = await chrome.storage.sync.get(["apiUrl", "investigationId"]);
  apiInput.value = stored.apiUrl || DEFAULTS.apiUrl;
  invInput.value = stored.investigationId || DEFAULTS.investigationId;
}

async function persistSettings() {
  await chrome.storage.sync.set({
    apiUrl: apiInput.value.trim() || DEFAULTS.apiUrl,
    investigationId: invInput.value.trim() || DEFAULTS.investigationId,
  });
}

async function captureCurrentTab() {
  const apiUrl = (apiInput.value || DEFAULTS.apiUrl).trim().replace(/\/$/, "");
  const investigationId =
    (invInput.value || DEFAULTS.investigationId).trim() ||
    DEFAULTS.investigationId;
  await persistSettings();

  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });
  if (!tab || !tab.id) {
    setStatus("err", "No active tab.");
    return;
  }

  captureBtn.disabled = true;
  setStatus("info", "Extracting thread from page…");
  let captureResp;
  try {
    captureResp = await chrome.tabs.sendMessage(tab.id, {
      type: "antiek-capture-thread",
    });
  } catch (e) {
    setStatus(
      "err",
      "Could not reach the page's content script. Reload the X tab and try again.",
    );
    captureBtn.disabled = false;
    return;
  }
  if (!captureResp || !captureResp.ok) {
    setStatus("err", captureResp?.error || "Unknown capture error.");
    captureBtn.disabled = false;
    return;
  }

  const payload = {
    ...captureResp.payload,
    investigation_id: investigationId,
  };
  setStatus(
    "info",
    `Captured ${payload.tweets.length} tweets. Posting to ${apiUrl}…`,
  );

  try {
    const resp = await fetch(`${apiUrl}/sources/twitter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      setStatus("err", `HTTP ${resp.status}: ${text.slice(0, 240)}`);
      return;
    }
    const body = await resp.json();
    if (body.status === "ingested") {
      setStatus(
        "ok",
        `Ingested: ${body.chunks_written} chunks. ${body.document_id}`,
      );
    } else {
      setStatus("err", `Skipped: ${body.skipped_reason || "(no reason)"}`);
    }
  } catch (e) {
    setStatus("err", `Network error: ${e instanceof Error ? e.message : e}`);
  } finally {
    captureBtn.disabled = false;
  }
}

captureBtn.addEventListener("click", () => {
  void captureCurrentTab();
});

void loadSettings();
