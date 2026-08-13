"use strict";

const elements = {
  apply: document.querySelector("#applyButton"),
  badge: document.querySelector("#connectionBadge"),
  cpu: document.querySelector("#cpuTemperature"),
  device: document.querySelector("#deviceModel"),
  fanIndex: document.querySelector("#fanIndexLabel"),
  lastUpdated: document.querySelector("#lastUpdated"),
  liveRefresh: document.querySelector("#liveRefresh"),
  message: document.querySelector("#message"),
  mode: document.querySelector("#fanMode"),
  modeDetail: document.querySelector("#modeDetail"),
  output: document.querySelector("#percentOutput"),
  restore: document.querySelector("#restoreButton"),
  rpm: document.querySelector("#fanRpm"),
  slider: document.querySelector("#speedSlider"),
  support: document.querySelector("#supportStatus"),
};

const appToken = document.querySelector('meta[name="app-token"]').content;
let selectedFan = 0;
let pollIntervalMs = 2000;
let pollingTimer = null;
let controlsAvailable = false;

function showMessage(text, kind = "") {
  elements.message.textContent = text;
  elements.message.className = `message${kind ? ` message-${kind}` : ""}`;
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") {
    headers["X-App-Token"] = appToken;
  }
  const response = await fetch(path, { ...options, headers });
  let body;
  try {
    body = await response.json();
  } catch (_) {
    throw new Error(`Local service returned HTTP ${response.status}`);
  }
  if (!response.ok || body.ok === false) {
    throw new Error(body.message || body.error || `Request failed (${response.status})`);
  }
  return body;
}

function setControlsEnabled(enabled) {
  controlsAvailable = enabled;
  elements.slider.disabled = !enabled;
  elements.apply.disabled = !enabled;
  elements.restore.disabled = !enabled;
}

function renderStatus(data) {
  const device = data.device;
  const fan = data.fans.find((item) => item.id === selectedFan) || data.fans[0];
  elements.device.textContent = device.model;
  elements.cpu.textContent = data.cpu_temperature ?? "—";
  elements.support.textContent = device.mock_mode
    ? "Safe simulation mode"
    : device.writes_allowed
      ? "Verified model · manual writes enabled"
      : "Unsupported model · manual writes blocked";
  if (fan) {
    selectedFan = fan.id;
    elements.fanIndex.textContent = fan.id;
    elements.rpm.textContent = fan.rpm.toLocaleString();
    elements.mode.textContent = fan.mode === "manual" ? "Manual" : "Firmware";
    elements.modeDetail.textContent = fan.mode === "manual"
      ? fan.percent == null ? "ASUS test mode active · duty unknown" : `Applied at ${fan.percent}%`
      : "ASUS firmware controls the fan";
  } else {
    elements.rpm.textContent = "—";
    elements.mode.textContent = "Unavailable";
    elements.modeDetail.textContent = data.hardware_error?.message || "No fan data";
  }

  setControlsEnabled(device.writes_allowed && Boolean(fan) && !data.hardware_error);

  elements.badge.textContent = data.hardware_error ? "Hardware unavailable" : "Live";
  elements.badge.className = `badge ${data.hardware_error ? "badge-error" : "badge-online"}`;
  elements.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  if (data.hardware_error) showMessage(data.hardware_error.message, "error");
}

async function refresh() {
  try {
    renderStatus(await api("/api/status"));
  } catch (error) {
    elements.badge.textContent = "Offline";
    elements.badge.className = "badge badge-error";
    setControlsEnabled(false);
    showMessage(error.message, "error");
  }
}

function schedulePolling() {
  clearInterval(pollingTimer);
  if (elements.liveRefresh.checked) pollingTimer = setInterval(refresh, pollIntervalMs);
}

elements.slider.addEventListener("input", () => {
  elements.output.textContent = `${elements.slider.value}%`;
});

elements.apply.addEventListener("click", async () => {
  elements.apply.disabled = true;
  try {
    const percent = Number.parseInt(elements.slider.value, 10);
    await api(`/api/fans/${selectedFan}/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ percent }),
    });
    showMessage(`Fan ${selectedFan} set to ${percent}%.`, "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    elements.apply.disabled = !controlsAvailable;
  }
});

elements.restore.addEventListener("click", async () => {
  elements.restore.disabled = true;
  try {
    await api(`/api/fans/${selectedFan}/restore`, { method: "POST" });
    showMessage(`Fan ${selectedFan} returned to firmware control.`, "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    elements.restore.disabled = !controlsAvailable;
  }
});

elements.liveRefresh.addEventListener("change", schedulePolling);

async function initialize() {
  try {
    const data = await api("/api/settings");
    pollIntervalMs = data.settings.poll_interval_ms;
    selectedFan = data.settings.last_selected_fan;
  } catch (error) {
    showMessage(`Settings unavailable: ${error.message}`, "error");
  }
  await refresh();
  schedulePolling();
}

initialize();
