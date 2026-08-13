"use strict";

const elements = {
  addCurvePoint: document.querySelector("#addCurvePoint"),
  apply: document.querySelector("#applyButton"),
  badge: document.querySelector("#connectionBadge"),
  backendMode: document.querySelector("#backendMode"),
  chart: document.querySelector("#historyChart"),
  chartEmpty: document.querySelector("#chartEmpty"),
  controlDevice: document.querySelector("#controlDevice"),
  controlMode: document.querySelector("#controlMode"),
  controlModeDot: document.querySelector("#controlModeDot"),
  controlRpm: document.querySelector("#controlRpm"),
  curveError: document.querySelector("#curveError"),
  curveChart: document.querySelector("#curveChart"),
  curveLastApplied: document.querySelector("#curveLastApplied"),
  curveName: document.querySelector("#curveName"),
  curveOwnership: document.querySelector("#curveOwnership"),
  curvePointValue: document.querySelector("#curvePointValue"),
  curveState: document.querySelector("#curveState"),
  curveStateDot: document.querySelector("#curveStateDot"),
  curveTarget: document.querySelector("#curveTarget"),
  curveTemperature: document.querySelector("#curveTemperature"),
  cpu: document.querySelector("#cpuTemperature"),
  device: document.querySelector("#deviceModel"),
  fanIndex: document.querySelector("#fanIndexLabel"),
  globalRestore: document.querySelector("#globalRestoreButton"),
  lastUpdated: document.querySelector("#lastUpdated"),
  liveRefresh: document.querySelector("#liveRefresh"),
  menu: document.querySelector("#menuButton"),
  message: document.querySelector("#message"),
  mode: document.querySelector("#fanMode"),
  modeDetail: document.querySelector("#modeDetail"),
  modeDot: document.querySelector("#modeDot"),
  output: document.querySelector("#percentOutput"),
  pollInterval: document.querySelector("#pollInterval"),
  profileForm: document.querySelector("#profileForm"),
  profileGrid: document.querySelector("#profileGrid"),
  profileMode: document.querySelector("#profileMode"),
  profileName: document.querySelector("#profileName"),
  profilePercent: document.querySelector("#profilePercent"),
  profilePercentField: document.querySelector("#profilePercentField"),
  restore: document.querySelector("#restoreButton"),
  retentionDays: document.querySelector("#retentionDays"),
  rpm: document.querySelector("#fanRpm"),
  sensorCpu: document.querySelector("#sensorCpu"),
  sensorController: document.querySelector("#sensorController"),
  sensorEcStatus: document.querySelector("#sensorEcStatus"),
  sensorMode: document.querySelector("#sensorMode"),
  sensorRpm: document.querySelector("#sensorRpm"),
  sessionOwnership: document.querySelector("#sessionOwnership"),
  settingsForm: document.querySelector("#settingsForm"),
  sidebarBackdrop: document.querySelector("#sidebarBackdrop"),
  sidebarConnection: document.querySelector("#sidebarConnection"),
  sidebarDevice: document.querySelector("#sidebarDevice"),
  sidebarMini: document.querySelector(".device-mini"),
  slider: document.querySelector("#speedSlider"),
  startCurve: document.querySelector("#startCurveButton"),
  stopCurve: document.querySelector("#stopCurveButton"),
  support: document.querySelector("#supportStatus"),
  telemetryEnabled: document.querySelector("#telemetryEnabled"),
  saveCurveProfile: document.querySelector("#saveCurveProfileButton"),
};

const appToken = document.querySelector('meta[name="app-token"]').content;
const chartSamples = [];
const maxChartSamples = 60;
let selectedFan = 0;
let pollIntervalMs = 2000;
let pollingTimer = null;
let pollGeneration = 0;
let controlsAvailable = false;
let refreshInFlight = null;
let toastTimer = null;
let lastStatus = null;
let draggedCurvePoint = null;
let selectedCurvePoint = null;
let curvePoints = [
  { temperature: 45, percent: 30 },
  { temperature: 60, percent: 50 },
  { temperature: 75, percent: 75 },
  { temperature: 90, percent: 100 },
];

function showMessage(text, kind = "") {
  clearTimeout(toastTimer);
  elements.message.textContent = text;
  elements.message.className = `toast is-visible${kind ? ` is-${kind}` : ""}`;
  toastTimer = setTimeout(() => {
    elements.message.classList.remove("is-visible");
  }, kind === "error" ? 7000 : 3500);
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-App-Token"] = appToken;
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
  elements.globalRestore.disabled = !enabled;
  elements.startCurve.disabled = !enabled;
}

function readCurvePoints() {
  return curvePoints.map((point) => ({ ...point }));
}

function updateCurvePointValue() {
  const point = selectedCurvePoint === null ? null : curvePoints[selectedCurvePoint];
  elements.curvePointValue.innerHTML = point
    ? `<i></i>${point.temperature} °C · ${point.percent}%`
    : "<i></i>Select a point";
}

function curveChartGeometry() {
  const bounds = elements.curveChart.getBoundingClientRect();
  const left = 44;
  const right = 16;
  const top = 16;
  const bottom = 30;
  return {
    bounds,
    left,
    top,
    width: Math.max(1, bounds.width - left - right),
    height: Math.max(1, bounds.height - top - bottom),
  };
}

function curvePointPosition(point, geometry) {
  return {
    x: geometry.left + ((point.temperature - 20) / 80) * geometry.width,
    y: geometry.top + geometry.height - (point.percent / 100) * geometry.height,
  };
}

function drawCurveChart() {
  const canvas = elements.curveChart;
  const geometry = curveChartGeometry();
  if (!geometry.bounds.width || !geometry.bounds.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(geometry.bounds.width * ratio);
  canvas.height = Math.round(geometry.bounds.height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, geometry.bounds.width, geometry.bounds.height);
  context.font = "9px Inter, system-ui, sans-serif";
  context.lineWidth = 1;

  for (let percent = 0; percent <= 100; percent += 25) {
    const y = geometry.top + geometry.height - (percent / 100) * geometry.height;
    context.strokeStyle = percent === 0 ? "#dfe3e8" : "#edf0f3";
    context.beginPath();
    context.moveTo(geometry.left, y);
    context.lineTo(geometry.left + geometry.width, y);
    context.stroke();
    context.fillStyle = "#9aa0aa";
    context.textAlign = "right";
    context.textBaseline = "middle";
    context.fillText(`${percent}%`, geometry.left - 8, y);
  }

  for (let temperature = 20; temperature <= 100; temperature += 10) {
    const x = geometry.left + ((temperature - 20) / 80) * geometry.width;
    context.fillStyle = "#9aa0aa";
    context.textAlign = "center";
    context.textBaseline = "top";
    context.fillText(`${temperature}°`, x, geometry.top + geometry.height + 9);
  }

  const validPoints = curvePoints.filter(
    (point) => Number.isFinite(point.temperature) && Number.isFinite(point.percent),
  );
  if (validPoints.length < 1) return;
  const positions = validPoints.map((point) => curvePointPosition(point, geometry));
  const gradient = context.createLinearGradient(0, geometry.top, 0, geometry.top + geometry.height);
  gradient.addColorStop(0, "rgba(46, 156, 105, .18)");
  gradient.addColorStop(1, "rgba(46, 156, 105, 0)");
  context.beginPath();
  context.moveTo(positions[0].x, geometry.top + geometry.height);
  positions.forEach((position) => context.lineTo(position.x, position.y));
  context.lineTo(positions.at(-1).x, geometry.top + geometry.height);
  context.closePath();
  context.fillStyle = gradient;
  context.fill();

  context.beginPath();
  positions.forEach((position, index) => {
    if (index === 0) context.moveTo(position.x, position.y);
    else context.lineTo(position.x, position.y);
  });
  context.strokeStyle = "#2e9c69";
  context.lineWidth = 2.5;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();

  positions.forEach((position, index) => {
    context.beginPath();
    const selected = selectedCurvePoint === index;
    context.arc(position.x, position.y, selected ? 6 : 4.5, 0, Math.PI * 2);
    context.fillStyle = "#ffffff";
    context.fill();
    context.strokeStyle = "#2e9c69";
    context.lineWidth = selected ? 3 : 2;
    context.stroke();
  });
}

function findCurvePointAt(event) {
  const geometry = curveChartGeometry();
  const x = event.clientX - geometry.bounds.left;
  const y = event.clientY - geometry.bounds.top;
  let closest = null;
  let distance = 15;
  curvePoints.forEach((point, index) => {
    const position = curvePointPosition(point, geometry);
    const candidate = Math.hypot(position.x - x, position.y - y);
    if (candidate < distance) {
      closest = index;
      distance = candidate;
    }
  });
  return closest;
}

function moveCurvePoint(event) {
  if (draggedCurvePoint === null) return;
  const geometry = curveChartGeometry();
  const x = Math.max(geometry.left, Math.min(geometry.left + geometry.width, event.clientX - geometry.bounds.left));
  const y = Math.max(geometry.top, Math.min(geometry.top + geometry.height, event.clientY - geometry.bounds.top));
  const previous = curvePoints[draggedCurvePoint - 1];
  const next = curvePoints[draggedCurvePoint + 1];
  const minimumTemperature = previous ? previous.temperature + 1 : 20;
  const maximumTemperature = next ? next.temperature - 1 : 100;
  const minimumPercent = previous ? previous.percent : 1;
  const maximumPercent = next ? next.percent : 100;
  curvePoints[draggedCurvePoint] = {
    temperature: Math.max(minimumTemperature, Math.min(maximumTemperature, Math.round(20 + ((x - geometry.left) / geometry.width) * 80))),
    percent: Math.max(minimumPercent, Math.min(maximumPercent, Math.round(((geometry.top + geometry.height - y) / geometry.height) * 100))),
  };
  updateCurvePointValue();
  drawCurveChart();
}

function renderCurveEditor() {
  elements.addCurvePoint.disabled = curvePoints.length >= 8;
  updateCurvePointValue();
  drawCurveChart();
}

function formatProfileDescription(profile) {
  if (profile.mode === "firmware") return "ASUS firmware controls fan behavior dynamically.";
  if (profile.mode === "manual") return `Fixed ${profile.percent}% through verified ASUS test mode.`;
  return `${profile.curve_points.length} temperature points · userspace controller.`;
}

function renderProfiles(bundle) {
  if (!bundle?.profiles) return;
  elements.profileGrid.replaceChildren();
  bundle.profiles.forEach((profile) => {
    const card = document.createElement("article");
    card.className = `panel profile-card${bundle.active_profile_id === profile.id ? " is-selected" : ""}`;
    const kind = document.createElement("span");
    kind.textContent = bundle.active_profile_id === profile.id ? "Active" : profile.mode;
    const title = document.createElement("h2");
    title.textContent = profile.name;
    const description = document.createElement("p");
    description.textContent = formatProfileDescription(profile);
    const actions = document.createElement("div");
    actions.className = "profile-actions";
    const apply = document.createElement("button");
    apply.className = "button button-secondary";
    apply.type = "button";
    apply.textContent = bundle.active_profile_id === profile.id ? "Reapply" : "Apply";
    apply.disabled = !controlsAvailable;
    apply.addEventListener("click", () => applyProfile(profile.id));
    actions.append(apply);
    if (!profile.built_in) {
      const remove = document.createElement("button");
      remove.className = "button button-danger";
      remove.type = "button";
      remove.textContent = "Delete";
      remove.disabled = bundle.active_profile_id === profile.id;
      remove.addEventListener("click", () => deleteProfile(profile.id));
      actions.append(remove);
    }
    card.append(kind, title, description, actions);
    elements.profileGrid.append(card);
  });
  const active = bundle.profiles.find((profile) => profile.id === bundle.active_profile_id);
  document.querySelector("#activeProfile").textContent = active?.name || (lastStatus?.curve_controller?.active ? lastStatus.curve_controller.name : "No profile");
}

function renderCurveStatus(controller) {
  if (!controller) return;
  elements.curveState.textContent = controller.active ? "Running" : "Stopped";
  elements.curveStateDot.classList.toggle("is-manual", controller.active);
  elements.curveTemperature.textContent = `${controller.temperature ?? "—"} °C`;
  elements.curveTarget.textContent = `${controller.target_percent ?? "—"} %`;
  elements.curveLastApplied.textContent = controller.last_applied
    ? new Date(controller.last_applied).toLocaleTimeString()
    : "Never";
  elements.curveOwnership.textContent = controller.session_owned ? "This session" : "No";
  elements.curveError.hidden = !controller.last_error;
  elements.curveError.textContent = controller.last_error?.message || "";
  elements.stopCurve.disabled = !controller.active;
  elements.sensorController.textContent = controller.active ? `Running · ${controller.target_percent}%` : "Stopped";
}

function formatRpm(rpm) {
  return Number.isFinite(rpm) ? rpm.toLocaleString() : "—";
}

function addChartSample(temperature, rpm) {
  if (!Number.isFinite(temperature) && !Number.isFinite(rpm)) return;
  chartSamples.push({ temperature, rpm, time: new Date() });
  if (chartSamples.length > maxChartSamples) chartSamples.shift();
  drawChart();
}

function chartPoint(value, min, max, top, height) {
  if (!Number.isFinite(value)) return null;
  const range = Math.max(max - min, 1);
  return top + height - ((value - min) / range) * height;
}

function drawSeries(context, samples, valueKey, min, max, color, left, top, width, height) {
  context.beginPath();
  context.strokeStyle = color;
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  let started = false;
  samples.forEach((sample, index) => {
    const y = chartPoint(sample[valueKey], min, max, top, height);
    if (y === null) return;
    const x = left + (samples.length === 1 ? width : (index / (samples.length - 1)) * width);
    if (!started) { context.moveTo(x, y); started = true; } else { context.lineTo(x, y); }
  });
  context.stroke();
}

function drawChart() {
  const canvas = elements.chart;
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(bounds.width * ratio);
  canvas.height = Math.round(bounds.height * ratio);
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  const width = bounds.width;
  const height = bounds.height;
  const left = 42;
  const right = 48;
  const top = 10;
  const bottom = 24;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#eceef1";
  context.lineWidth = 1;
  context.fillStyle = "#9aa0aa";
  context.font = "10px Inter, system-ui, sans-serif";
  context.textBaseline = "middle";
  for (let row = 0; row <= 4; row += 1) {
    const y = top + (row / 4) * plotHeight;
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(left + plotWidth, y);
    context.stroke();
    context.textAlign = "right";
    context.fillText(`${Math.round(100 - row * 20)}°`, left - 8, y);
    context.textAlign = "left";
    context.fillText(`${Math.round(5000 - row * 1250)}`, left + plotWidth + 8, y);
  }

  if (!chartSamples.length) return;
  drawSeries(context, chartSamples, "temperature", 20, 100, "#e99645", left, top, plotWidth, plotHeight);
  drawSeries(context, chartSamples, "rpm", 0, 5000, "#5b7cfa", left, top, plotWidth, plotHeight);
  context.fillStyle = "#9aa0aa";
  context.textAlign = "left";
  context.textBaseline = "bottom";
  context.fillText(chartSamples[0].time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), left, height);
  context.textAlign = "right";
  context.fillText(chartSamples.at(-1).time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), left + plotWidth, height);
  elements.chartEmpty.classList.add("is-hidden");
}

function updateModeElements(fan) {
  const manual = fan?.mode === "manual";
  const modeText = fan ? (manual ? "Manual" : "Firmware") : "Unavailable";
  elements.mode.textContent = modeText;
  elements.controlMode.textContent = modeText;
  elements.sensorMode.textContent = fan ? (manual ? "Enabled" : "Disabled") : "—";
  elements.modeDot.classList.toggle("is-manual", manual);
  elements.controlModeDot.classList.toggle("is-manual", manual);
  elements.sessionOwnership.textContent = fan?.session_owned ? "This session" : "No";
  elements.modeDetail.textContent = fan
    ? manual
      ? fan.percent == null ? "ASUS test mode active · duty unknown" : `Manual duty applied at ${fan.percent}%`
      : "ASUS firmware dynamically controls the fan"
    : lastStatus?.hardware_error?.message || "No fan data";
}

function renderStatus(data) {
  lastStatus = data;
  const device = data.device;
  const fan = data.fans.find((item) => item.id === selectedFan) || data.fans[0];
  const temperature = Number.isFinite(data.cpu_temperature) ? data.cpu_temperature : null;
  const rpm = fan && Number.isFinite(fan.rpm) ? fan.rpm : null;
  const online = !data.hardware_error && Boolean(fan);

  elements.device.textContent = device.model;
  elements.sidebarDevice.textContent = device.model;
  elements.controlDevice.textContent = device.model;
  elements.backendMode.textContent = device.mock_mode ? "Mock hardware" : "Native EC helper";
  elements.cpu.textContent = temperature ?? "—";
  elements.sensorCpu.textContent = `${temperature ?? "—"} °C`;
  elements.support.textContent = device.mock_mode
    ? "Safe simulation mode"
    : device.writes_allowed ? "Verified hardware" : "Unsupported · read only";

  if (fan) {
    selectedFan = fan.id;
    elements.fanIndex.textContent = fan.id;
    elements.rpm.textContent = formatRpm(rpm);
    elements.controlRpm.textContent = `${formatRpm(rpm)} RPM`;
    elements.sensorRpm.textContent = `${formatRpm(rpm)} RPM`;
  } else {
    elements.rpm.textContent = "—";
    elements.controlRpm.textContent = "— RPM";
    elements.sensorRpm.textContent = "— RPM";
  }
  updateModeElements(fan);
  setControlsEnabled(device.writes_allowed && Boolean(fan) && !data.hardware_error);
  renderCurveStatus(data.curve_controller);
  renderProfiles(data.profiles);
  elements.sensorEcStatus.textContent = data.ec
    ? `0x${data.ec.status.toString(16).padStart(2, "0")} · OBF ${data.ec.obf ? "1" : "0"} · IBF ${data.ec.ibf ? "1" : "0"}`
    : "—";

  elements.badge.innerHTML = `<span class="status-dot"></span>${online ? "Live" : "Hardware unavailable"}`;
  elements.badge.className = `status-pill ${online ? "is-online" : "is-error"}`;
  elements.sidebarMini.className = `device-mini ${online ? "is-online" : "is-error"}`;
  elements.sidebarConnection.textContent = online ? "Live connection" : "Hardware unavailable";
  elements.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  if (online) addChartSample(temperature, rpm);
  if (data.hardware_error) showMessage(data.hardware_error.message, "error");
}

async function startCurve() {
  stopPolling();
  elements.startCurve.disabled = true;
  try {
    curvePoints = readCurvePoints();
    await api("/api/curve/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fan: selectedFan, name: elements.curveName.value.trim(), points: curvePoints }),
    });
    showMessage("Temperature curve started.", "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    elements.startCurve.disabled = !controlsAvailable;
    schedulePolling();
  }
}

async function stopCurve() {
  stopPolling();
  elements.stopCurve.disabled = true;
  try {
    await api("/api/curve/stop", { method: "POST" });
    showMessage("Curve stopped; owned manual control was restored.", "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    schedulePolling();
  }
}

async function saveProfile(event) {
  event?.preventDefault();
  const mode = event ? elements.profileMode.value : "curve";
  const name = event ? elements.profileName.value.trim() : elements.curveName.value.trim();
  const payload = { name, mode };
  if (mode === "manual") payload.percent = Number.parseInt(elements.profilePercent.value, 10);
  if (mode === "curve") {
    curvePoints = readCurvePoints();
    payload.curve_points = curvePoints;
  }
  try {
    await api("/api/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    elements.profileName.value = "";
    showMessage(`Profile “${name}” saved.`, "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

async function applyProfile(id) {
  stopPolling();
  try {
    await api(`/api/profiles/${id}/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fan: selectedFan }),
    });
    showMessage("Profile applied.", "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    schedulePolling();
  }
}

async function deleteProfile(id) {
  try {
    await api(`/api/profiles/${id}`, { method: "DELETE" });
    showMessage("Profile deleted.", "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function refresh() {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      renderStatus(await api("/api/status"));
    } catch (error) {
      elements.badge.innerHTML = '<span class="status-dot"></span>Offline';
      elements.badge.className = "status-pill is-error";
      elements.sidebarMini.className = "device-mini is-error";
      elements.sidebarConnection.textContent = "Service offline";
      setControlsEnabled(false);
      showMessage(error.message, "error");
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

function stopPolling() {
  pollGeneration += 1;
  clearTimeout(pollingTimer);
}

function schedulePolling() {
  stopPolling();
  if (!elements.liveRefresh.checked) return;
  const generation = pollGeneration;
  pollingTimer = setTimeout(async function poll() {
    await refresh();
    if (elements.liveRefresh.checked && generation === pollGeneration) {
      pollingTimer = setTimeout(poll, pollIntervalMs);
    }
  }, pollIntervalMs);
}

function openView(name) {
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("is-visible", panel.dataset.viewPanel === name);
  });
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === name);
  });
  document.body.classList.remove("sidebar-open");
  if (name === "dashboard") requestAnimationFrame(drawChart);
  if (name === "curves") requestAnimationFrame(drawCurveChart);
  document.querySelector(`[data-view-panel="${name}"] h1`)?.focus({ preventScroll: true });
}

async function applyManual() {
  stopPolling();
  elements.apply.disabled = true;
  try {
    const percent = Number.parseInt(elements.slider.value, 10);
    await api(`/api/fans/${selectedFan}/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ percent }),
    });
    showMessage(`Fan ${selectedFan} set to ${percent}% and verified.`, "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    elements.apply.disabled = !controlsAvailable;
    schedulePolling();
  }
}

async function restoreFirmware() {
  stopPolling();
  elements.restore.disabled = true;
  elements.globalRestore.disabled = true;
  try {
    await api(`/api/fans/${selectedFan}/restore`, { method: "POST" });
    showMessage(`Fan ${selectedFan} returned to firmware control.`, "success");
    await refresh();
  } catch (error) {
    showMessage(error.message, "error");
  } finally {
    elements.restore.disabled = !controlsAvailable;
    elements.globalRestore.disabled = !controlsAvailable;
    schedulePolling();
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const values = {
    poll_interval_ms: Number.parseInt(elements.pollInterval.value, 10),
    telemetry_enabled: elements.telemetryEnabled.checked,
    telemetry_retention_days: Number.parseInt(elements.retentionDays.value, 10),
  };
  try {
    const data = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    pollIntervalMs = data.settings.poll_interval_ms;
    showMessage("Settings saved.", "success");
    schedulePolling();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => openView(button.dataset.view));
});
document.querySelectorAll("[data-open-view]").forEach((button) => {
  button.addEventListener("click", () => openView(button.dataset.openView));
});
elements.menu.addEventListener("click", () => document.body.classList.toggle("sidebar-open"));
elements.sidebarBackdrop.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
elements.slider.addEventListener("input", () => { elements.output.textContent = `${elements.slider.value}%`; });
elements.apply.addEventListener("click", applyManual);
elements.restore.addEventListener("click", restoreFirmware);
elements.globalRestore.addEventListener("click", restoreFirmware);
elements.addCurvePoint.addEventListener("click", () => {
  curvePoints = readCurvePoints();
  let insertAfter = 0;
  let largestGap = -1;
  for (let index = 0; index < curvePoints.length - 1; index += 1) {
    const gap = curvePoints[index + 1].temperature - curvePoints[index].temperature;
    if (gap > largestGap) {
      largestGap = gap;
      insertAfter = index;
    }
  }
  const lower = curvePoints[insertAfter];
  const upper = curvePoints[insertAfter + 1];
  curvePoints.splice(insertAfter + 1, 0, {
    temperature: Math.round((lower.temperature + upper.temperature) / 2),
    percent: Math.round((lower.percent + upper.percent) / 2),
  });
  selectedCurvePoint = insertAfter + 1;
  renderCurveEditor();
});
elements.curveChart.addEventListener("pointerdown", (event) => {
  draggedCurvePoint = findCurvePointAt(event);
  selectedCurvePoint = draggedCurvePoint;
  updateCurvePointValue();
  if (draggedCurvePoint !== null) {
    elements.curveChart.setPointerCapture(event.pointerId);
    elements.curveChart.classList.add("is-dragging");
    drawCurveChart();
  }
});
elements.curveChart.addEventListener("pointermove", moveCurvePoint);
elements.curveChart.addEventListener("pointerup", (event) => {
  if (draggedCurvePoint !== null && elements.curveChart.hasPointerCapture(event.pointerId)) {
    elements.curveChart.releasePointerCapture(event.pointerId);
  }
  draggedCurvePoint = null;
  elements.curveChart.classList.remove("is-dragging");
  drawCurveChart();
});
elements.curveChart.addEventListener("dblclick", (event) => {
  const index = findCurvePointAt(event);
  if (index === null || curvePoints.length <= 2) return;
  curvePoints.splice(index, 1);
  selectedCurvePoint = null;
  renderCurveEditor();
});
elements.curveChart.addEventListener("keydown", (event) => {
  if (selectedCurvePoint === null) return;
  const point = curvePoints[selectedCurvePoint];
  const previous = curvePoints[selectedCurvePoint - 1];
  const next = curvePoints[selectedCurvePoint + 1];
  if ((event.key === "Delete" || event.key === "Backspace") && curvePoints.length > 2) {
    event.preventDefault();
    curvePoints.splice(selectedCurvePoint, 1);
    selectedCurvePoint = null;
    renderCurveEditor();
    return;
  }
  let temperature = point.temperature;
  let percent = point.percent;
  if (event.key === "ArrowLeft") temperature -= 1;
  else if (event.key === "ArrowRight") temperature += 1;
  else if (event.key === "ArrowDown") percent -= 1;
  else if (event.key === "ArrowUp") percent += 1;
  else return;
  event.preventDefault();
  curvePoints[selectedCurvePoint] = {
    temperature: Math.max(previous ? previous.temperature + 1 : 20, Math.min(next ? next.temperature - 1 : 100, temperature)),
    percent: Math.max(previous ? previous.percent : 1, Math.min(next ? next.percent : 100, percent)),
  };
  updateCurvePointValue();
  drawCurveChart();
});
elements.curveChart.addEventListener("pointercancel", () => {
  draggedCurvePoint = null;
  elements.curveChart.classList.remove("is-dragging");
  drawCurveChart();
});
elements.startCurve.addEventListener("click", startCurve);
elements.stopCurve.addEventListener("click", stopCurve);
elements.saveCurveProfile.addEventListener("click", () => saveProfile());
elements.profileForm.addEventListener("submit", saveProfile);
elements.profileMode.addEventListener("change", () => {
  elements.profilePercentField.hidden = elements.profileMode.value !== "manual";
});
elements.liveRefresh.addEventListener("change", schedulePolling);
elements.settingsForm.addEventListener("submit", saveSettings);
window.addEventListener("resize", () => {
  drawChart();
  drawCurveChart();
});

async function initialize() {
  renderCurveEditor();
  try {
    const data = await api("/api/settings");
    pollIntervalMs = data.settings.poll_interval_ms;
    selectedFan = data.settings.last_selected_fan;
    elements.pollInterval.value = String(data.settings.poll_interval_ms);
    elements.telemetryEnabled.checked = data.settings.telemetry_enabled;
    elements.retentionDays.value = String(data.settings.telemetry_retention_days);
  } catch (error) {
    showMessage(`Settings unavailable: ${error.message}`, "error");
  }
  await refresh();
  schedulePolling();
}

initialize();
