"use strict";

const MULTIPLE_RECORDS_HINT = "Multiple proxy records detected; only the first one is used per run.";

let cfg = null;
let api = null;
let batchRunning = false;
let batchAborted = false;
let batchStopped = false;
let batchUnlimited = false;
let manualRowSeq = 0;

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const TOAST_MS = 2200;
const TOAST_LONG_MS = 7000;

function toastDuration(msg) {
  const text = String(msg || "");
  if (text.includes("\n")) return Math.min(12000, 5000 + text.length * 25);
  if (text.length > 60) return TOAST_LONG_MS;
  return TOAST_MS;
}

function toast(msg, duration) {
  const text = String(msg || "");
  const ms = duration ?? toastDuration(text);
  const t = $("#toast");
  t.textContent = text;
  t.classList.toggle("long", ms > TOAST_MS || text.includes("\n"));
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), ms);
}

function showError(msg) {
  toast(msg);
}

async function validateExtractApi(url) {
  const btn = $("#a-add");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Testing...";
  let r;
  try {
    r = await api.fetch_one(url, cfg.extract_regex, cfg.timeout);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = old;
    return { ok: false, error: "Extraction test failed: " + e };
  }
  btn.disabled = false;
  btn.textContent = old;
  return r;
}

function whenReady() {
  if (window.__USE_HTTP_API__) return Promise.resolve();
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve();
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
  });
}

async function initApiClient() {
  try {
    const r = await fetch("/api/ping", { cache: "no-store" });
    if (r.ok) {
      const data = await r.json();
      if (data.ok) {
        window.__USE_HTTP_API__ = true;
        if (data.version) window.__APP_VERSION__ = data.version;
        document.body.classList.add("platform-android");
        if (typeof connectBatchSSE === "function") connectBatchSSE();
        return createHttpApi();
      }
    }
  } catch (_) { /* desktop pywebview */ }
  await whenReady();
  return window.pywebview.api;
}

function toggleGeoCustomInput() {
  const mode = ($("#set-geo-channel") && $("#set-geo-channel").value) ? $("#set-geo-channel").value : "ipinfo";
  const row = $("#geo-custom-row");
  if (!row) return;
  row.style.display = mode === "custom" ? "block" : "none";
}

function showResponseContent() {
  return !!cfg.show_response_content;
}

function setPublicIpDisplay(text) {
  const val = String(text || "—");
  [$("#s-public-ip"), $("#b-public-ip")].forEach((el) => {
    if (el) el.textContent = val;
  });
}

async function loadPublicIp() {
  setPublicIpDisplay("Checking...");
  try {
    // Backend will use cfg.geo_channel / cfg.geo_custom_url.
    const r = await api.fetch_public_ip("", cfg.timeout || 10);
    const ip = r.ip || r.content || "—";
    const country = r.country ? (" - " + r.country) : "";
    const text = r.ok ? (ip + country) : ("Checking failed: " + (r.error || "Unknown error"));
    setPublicIpDisplay(text);
  } catch (e) {
    setPublicIpDisplay("Checking failed");
  }
}

/* ---------------- Tabs ---------------- */
function initTabs() {
  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".nav-item").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      $$(".tab").forEach((t) => t.classList.remove("active"));
      $("#tab-" + tab).classList.add("active");
      if (tab === "single" || tab === "batch") {
        loadPublicIp();
        syncClearProxyButtons();
      }
    });
  });
}

function initSegments() {
  $$(".seg").forEach((seg) => {
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest(".seg-btn");
      if (!btn) return;
      seg.querySelectorAll(".seg-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}
function segValue(id) {
  const a = $("#" + id + " .seg-btn.active");
  return a ? a.dataset.v : "http";
}
function setSeg(id, val) {
  $$("#" + id + " .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.v === val));
}

function canSyncBrowserProxy(proto) {
  return (proto || "http") === "http";
}

function updateSyncBrowserUi(segId, checkboxId, rowId, configKey) {
  const proto = segValue(segId);
  const cb = $(checkboxId);
  const row = $(rowId);
  const supported = canSyncBrowserProxy(proto);
  const batchLocked = checkboxId === "#b-sync-browser" && batchRunning;
  cb.disabled = batchLocked || !supported;
  row.classList.toggle("check-row-disabled", !supported);
  if (!supported && cb.checked) {
    cb.checked = false;
    if (configKey) {
      cfg[configKey] = false;
      persist();
    }
    toast("SOCKS5 cannot sync browser proxy. Unchecked.");
  }
}

function refreshAllSyncBrowserUi() {
  updateSyncBrowserUi("single-proto", "#s-sync-browser", "#s-sync-row", "single_sync_browser");
  updateSyncBrowserUi("batch-proto", "#b-sync-browser", "#b-sync-row", "batch_sync_browser");
}

/* ---------------- Config wiring ---------------- */
function fillApiSelect() {
  const el = $("#b-api");
  el.innerHTML = "";
  if (!cfg.apis || cfg.apis.length === 0) {
    const o = document.createElement("option");
    o.value = ""; o.textContent = "(Please add an API in Settings first)";
    el.appendChild(o);
    return;
  }
  cfg.apis.forEach((a, i) => {
    const o = document.createElement("option");
    o.value = String(i); o.textContent = a.name;
    el.appendChild(o);
  });
}

function renderApiList() {
  const ul = $("#a-list");
  ul.innerHTML = "";
  if (!cfg.apis.length) { ul.innerHTML = '<div class="empty">No extract APIs</div>'; return; }
  cfg.apis.forEach((a, i) => {
    const authHint = (a.username || "").trim()
      ? `Credentials: ${esc((a.username || "").trim())}`
      : "No credentials";
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="li-main">
        <div class="li-title">${esc(a.name)}</div>
        <div class="li-sub" title="${esc(a.url)}">${esc(a.url)}</div>
        <div class="li-sub">${authHint}</div>
      </div>
      <div class="li-actions">
        <button class="chip test" data-i="${i}">Test Extract</button>
        <button class="chip del" data-i="${i}">Delete</button>
      </div>`;
    li.querySelector(".test").addEventListener("click", async (e) => {
      const btn = e.target; const old = btn.textContent; btn.textContent = "Extracting...";
      const r = await api.fetch_one(a.url, cfg.extract_regex, cfg.timeout);
      btn.textContent = old;
      if (r.ok) {
        if (r.multiple) toast(MULTIPLE_RECORDS_HINT);
        toast(`Extracted successfully: ${r.host}:${r.port}`);
      } else {
        showError(r.error || "Extraction failed");
      }
    });
    li.querySelector(".del").addEventListener("click", () => { cfg.apis.splice(i, 1); persist(); renderApiList(); fillApiSelect(); });
    ul.appendChild(li);
  });
}

function refreshSelects() {
  fillApiSelect();
}

function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

async function persist() {
  await api.save_config(cfg);
}

/* ---------------- System proxy ---------------- */
async function syncClearProxyButtons() {
  let enabled = false;
  try {
    const r = await api.get_system_proxy_status();
    enabled = !!(r.ok && r.enabled);
  } catch (_) { /* ignore */ }
  ["s-clear-proxy", "b-clear-proxy"].forEach((id) => {
    const btn = $("#" + id);
    if (btn) btn.classList.toggle("hidden", !enabled);
  });
}

async function clearBrowserProxy() {
  const r = await api.clear_system_proxy();
  if (r.ok) {
    toast("Browser proxy settings cleared");
    syncClearProxyButtons();
    loadPublicIp();
  } else {
    toast(r.error || "Clear failed");
  }
  return r;
}

async function restoreSystemProxy() {
  return clearBrowserProxy();
}

/* ---------------- Version notice (banners disabled) ---------------- */
async function loadVersion() {
  const el = $("#notice-version");
  if (!el) return;
  try {
    let ver = window.__APP_VERSION__ || "";
    if (!ver && api.get_version) {
      const r = await api.get_version();
      ver = r.version || "";
    }
    el.textContent = ver ? `v${ver}` : "";
  } catch (_) {
    el.textContent = "";
  }
}

/* ---------------- Single test ---------------- */
function mapSchemeToProto(scheme) {
  const s = (scheme || "").toLowerCase();
  if (s === "http" || s === "https") return "http";
  if (s === "socks5" || s === "socks5h" || s === "socks4") return "s5_tcp";
  return null;
}

function decodeUriPart(text) {
  try {
    return decodeURIComponent(text || "");
  } catch (_) {
    return text || "";
  }
}

function normalizeProxyText(text) {
  return (text || "").trim().replace(/\uFF1A/g, ":");
}

function parseHostPortFromRaw(raw) {
  const text = normalizeProxyText(raw);
  if (!text) return null;

  const v6 = text.match(/^\[([^\]]+)\]:(\d{1,5})$/);
  if (v6) {
    const port = parseInt(v6[2], 10);
    if (port > 0 && port < 65536) return { host: v6[1], port: String(port) };
  }

  const idx = text.lastIndexOf(":");
  if (idx > 0) {
    const host = text.slice(0, idx);
    const portStr = text.slice(idx + 1);
    if (/^\d{1,5}$/.test(portStr)) {
      const port = parseInt(portStr, 10);
      if (port > 0 && port < 65536) return { host, port: String(port) };
    }
  }
  return null;
}

function parseProxyInput(text) {
  let raw = normalizeProxyText(text);
  if (!raw) return null;

  const out = { host: "", port: "", username: "", password: "", protocol: null };
  const schemeMatch = raw.match(/^(https?|socks5h?|socks4):\/\//i);
  if (schemeMatch) {
    out.protocol = mapSchemeToProto(schemeMatch[1]);
    raw = raw.slice(schemeMatch[0].length);
    const atIdx = raw.lastIndexOf("@");
    if (atIdx >= 0) {
      const userinfo = raw.slice(0, atIdx);
      raw = raw.slice(atIdx + 1);
      const colonIdx = userinfo.indexOf(":");
      if (colonIdx >= 0) {
        out.username = decodeUriPart(userinfo.slice(0, colonIdx));
        out.password = decodeUriPart(userinfo.slice(colonIdx + 1));
      } else {
        out.username = decodeUriPart(userinfo);
      }
    }
  } else {
    raw = raw.replace(/^https?:\/\//i, "").split("/")[0].split("?")[0];
    const atIdx = raw.lastIndexOf("@");
    if (atIdx >= 0) {
      const userinfo = raw.slice(0, atIdx);
      raw = raw.slice(atIdx + 1);
      const colonIdx = userinfo.indexOf(":");
      if (colonIdx >= 0) {
        out.username = decodeUriPart(userinfo.slice(0, colonIdx));
        out.password = decodeUriPart(userinfo.slice(colonIdx + 1));
      } else {
        out.username = decodeUriPart(userinfo);
      }
    }
  }

  const hp = parseHostPortFromRaw(raw.split("/")[0].split("?")[0]);
  if (!hp) return null;
  out.host = hp.host;
  out.port = hp.port;
  return out;
}

function parseHostPort(text) {
  return parseProxyInput(text);
}

function applyProxyInput(text) {
  const parsed = parseProxyInput(text);
  if (!parsed) return false;
  $("#s-host").value = parsed.host;
  $("#s-port").value = parsed.port;
  if (parsed.username) $("#s-user").value = parsed.username;
  if (parsed.password) $("#s-pass").value = parsed.password;
  if (parsed.protocol) {
    setSeg("single-proto", parsed.protocol);
    cfg.protocol = parsed.protocol;
    refreshAllSyncBrowserUi();
  }
  return true;
}

function applyHostPortSplit() {
  const text = normalizeProxyText($("#s-host").value);
  if (parseProxyInput(text)) {
    return applyProxyInput(text);
  }
  if (/^(https?|socks5h?|socks4):\/\//i.test(text)) {
    return applyProxyInput(text);
  }
  const hp = parseHostPortFromRaw(text.replace(/^https?:\/\//i, "").split("/")[0].split("?")[0]);
  if (!hp) return false;
  $("#s-host").value = hp.host;
  $("#s-port").value = hp.port;
  return true;
}

function initPasswordToggle(inputId, toggleId) {
  const input = $(inputId);
  const btn = $(toggleId);
  if (!input || !btn) return;
  btn.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.classList.toggle("on", show);
    btn.title = show ? "Hide password" : "Show password";
    btn.setAttribute("aria-label", btn.title);
  });
}

function initSingleHostInput() {
  const hostEl = $("#s-host");
  hostEl.addEventListener("paste", (e) => {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    if (!parseProxyInput(text)) return;
    e.preventDefault();
    applyProxyInput(text);
  toast("Parsed proxy address");
  });
  hostEl.addEventListener("input", () => { applyHostPortSplit(); });
  hostEl.addEventListener("blur", () => { applyHostPortSplit(); });
  initPasswordToggle("#s-pass", "#s-pass-toggle");
  initPasswordToggle("#a-pass", "#a-pass-toggle");
}

async function runSingle() {
  applyHostPortSplit();
  const host = $("#s-host").value.trim();
  const port = $("#s-port").value.trim();
  if (!host || !port) { toast("Please enter proxy address and port"); return; }
  const proto = segValue("single-proto");
  const timeout = cfg.timeout || 10;

  const btn = $("#s-run");
  btn.disabled = true; btn.textContent = "Testing...";
  $("#s-result").classList.add("hidden");

  let r;
  const username = $("#s-user").value.trim();
  const password = $("#s-pass").value;
  const showContent = showResponseContent();
  const syncBrowser = $("#s-sync-browser").checked === true;

  try {
    r = await api.test_single(host, port, proto, "", timeout,
      cfg.udp_dns || "8.8.8.8", username, password, showContent, syncBrowser);
  } catch (e) {
    toast("Test error: " + e); btn.disabled = false; btn.textContent = "Start Testing"; return;
  }
    btn.disabled = false; btn.textContent = "Start Testing";

  if (r.public_ip) setPublicIpDisplay(r.public_ip);
  if (syncBrowser) {
    syncClearProxyButtons();
    if (r.proxy_note && String(r.proxy_note).toLowerCase().includes("failed")) toast(r.proxy_note);
  }

  $("#s-result").classList.remove("hidden");
  const badge = $("#s-badge");
  badge.className = "badge " + (r.ok ? "ok" : "fail");
  badge.textContent = r.ok ? "Connected" : "Failed";
  $("#s-time").textContent = r.elapsed_ms + " ms";
  $("#s-status").textContent = r.status != null ? r.status : "—";

  const wrap = $("#s-content-wrap");
  wrap.classList.remove("hidden");
  if (r.ok) {
    $("#s-content-label").textContent = "Response Content";
    $("#s-content").textContent = r.content || r.note || "(no content)";
  } else {
    $("#s-content-label").textContent = "Error Message";
    $("#s-content").textContent = r.error || "Unknown error";
  }
}

function initSingleControls() {
  $("#s-sync-browser").addEventListener("change", () => {
    if ($("#s-sync-browser").checked && !canSyncBrowserProxy(segValue("single-proto"))) {
      $("#s-sync-browser").checked = false;
      toast("SOCKS5 cannot sync browser proxy");
      return;
    }
    cfg.single_sync_browser = $("#s-sync-browser").checked === true;
    persist();
  });
}

/* ---------------- Batch test ---------------- */
const INTERVAL_UNIT_MAX = { s: 31536000, m: 525600, h: 8760, d: 365 };
const INTERVAL_UNIT_MULT = { s: 1, m: 60, h: 3600, d: 86400 };
const MIN_INTERVAL_SECONDS = 10;
const MAX_INTERVAL_SECONDS = 365 * 86400;

function parseBatchInterval() {
  const unit = $("#b-interval-unit").value || "s";
  const raw = $("#b-interval").value;
  const value = raw === "" ? 0 : parseFloat(raw);
  if (!value || value <= 0) {
    return { ok: true, unlimited: false, seconds: 0, value: 0, unit };
  }
  const max = INTERVAL_UNIT_MAX[unit] || 365;
  if (value > max) {
    return { ok: false, error: `The maximum interval for this unit is ${max}` };
  }
  const seconds = value * (INTERVAL_UNIT_MULT[unit] || 1);
  if (seconds < MIN_INTERVAL_SECONDS) {
    return { ok: false, error: "Minimum interval cannot be less than 10 seconds" };
  }
  if (seconds > MAX_INTERVAL_SECONDS) {
    return { ok: false, error: "Maximum interval cannot exceed 365 days" };
  }
  return { ok: true, unlimited: true, seconds, value, unit };
}

function updateIntervalMax() {
  const unit = $("#b-interval-unit").value || "s";
  $("#b-interval").max = INTERVAL_UNIT_MAX[unit] || 365;
}

function normalizeBatchIntervalOnBlur() {
  const unitEl = $("#b-interval-unit");
  const inputEl = $("#b-interval");
  const value = getBatchIntervalValue();
  if (!value || value <= 0) return;

  const seconds = value * (INTERVAL_UNIT_MULT[unitEl.value] || 1);
  if (seconds < MIN_INTERVAL_SECONDS) {
    unitEl.value = "s";
    inputEl.value = "10";
    toast("Minimum interval is 10 seconds; auto-adjusted.");
    saveBatchOptions();
    syncBatchModeUi();
    return;
  }
  if (seconds > MAX_INTERVAL_SECONDS) {
    unitEl.value = "d";
    inputEl.value = "365";
    toast("Maximum interval is 365 days; auto-adjusted.");
    saveBatchOptions();
    syncBatchModeUi();
  }
}

function getBatchCountValue() {
  return parseInt($("#b-count").value, 10) || 0;
}

function getBatchIntervalValue() {
  const raw = $("#b-interval").value;
  return raw === "" ? 0 : parseFloat(raw) || 0;
}

function syncBatchModeUi() {
  const intervalVal = getBatchIntervalValue();
  const countVal = getBatchCountValue();
  const intervalMode = intervalVal > 0;
  const countMode = !intervalMode && countVal > 0;

  const countWrap = $("#b-count-wrap");
  const intervalWrap = $("#b-interval-wrap");
  countWrap.classList.remove("batch-opt-active", "batch-opt-dimmed");
  intervalWrap.classList.remove("batch-opt-active", "batch-opt-dimmed");

  if (intervalMode) {
    intervalWrap.classList.add("batch-opt-active");
    countWrap.classList.add("batch-opt-dimmed");
  } else if (countMode) {
    countWrap.classList.add("batch-opt-active");
    intervalWrap.classList.add("batch-opt-dimmed");
  }

  const locked = batchRunning;
  $("#b-count").readOnly = locked;
  $("#b-interval").readOnly = locked;
  $("#b-interval-unit").disabled = locked;
  $("#b-manual").disabled = locked;
  refreshAllSyncBrowserUi();
}

function saveBatchOptions() {
  cfg.batch_count = getBatchCountValue();
  cfg.batch_interval = getBatchIntervalValue();
  cfg.batch_interval_unit = $("#b-interval-unit").value || "s";
  cfg.batch_sync_browser = $("#b-sync-browser").checked === true;
  persist();
}

function initBatchControls() {
  updateIntervalMax();
  $("#b-interval-unit").addEventListener("change", () => {
    updateIntervalMax();
    syncBatchModeUi();
    saveBatchOptions();
  });
  $("#b-interval").addEventListener("input", () => {
    if (getBatchIntervalValue() > 0 && getBatchCountValue() > 0) {
      $("#b-count").value = "0";
    }
    syncBatchModeUi();
    saveBatchOptions();
  });
  $("#b-interval").addEventListener("blur", normalizeBatchIntervalOnBlur);
  $("#b-count").addEventListener("input", () => {
    if (getBatchCountValue() > 0 && getBatchIntervalValue() > 0) {
      $("#b-interval").value = "0";
    }
    syncBatchModeUi();
    saveBatchOptions();
  });
  $("#b-count").addEventListener("change", saveBatchOptions);
  $("#b-sync-browser").addEventListener("change", () => {
    if ($("#b-sync-browser").checked && !canSyncBrowserProxy(segValue("batch-proto"))) {
      $("#b-sync-browser").checked = false;
      toast("SOCKS5 cannot sync browser proxy");
      return;
    }
    saveBatchOptions();
  });
  syncBatchModeUi();
}

function setBatchRunning(on) {
  batchRunning = on;
  $("#b-run").disabled = on;
  $("#b-stop").disabled = !on;
  $("#b-manual").disabled = on;
  $("#engineStatus").textContent = on ? "Testing..." : "Ready";
  if (!on) hideBatchCountdown();
  syncBatchModeUi();
}

function formatCountdown(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 86400) {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${d} days ${h} hours ${m} minutes ${sec} seconds`;
  }
  if (s >= 3600) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h} hours ${m} minutes ${sec} seconds`;
  }
  if (s >= 60) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m} minutes ${sec} seconds`;
  }
  return `${s} seconds`;
}

function showBatchCountdown(remaining, total) {
  const box = $("#b-countdown");
  const val = $("#b-countdown-val");
  const fill = $("#b-countdown-fill");
  if (!box || !val || !fill) return;
  box.classList.remove("hidden");
  val.textContent = formatCountdown(remaining);
  const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0;
  fill.style.width = pct + "%";
  $("#engineStatus").textContent = `Waiting to switch · ${formatCountdown(remaining)}`;
}

function hideBatchCountdown() {
  const box = $("#b-countdown");
  if (box) box.classList.add("hidden");
  const fill = $("#b-countdown-fill");
  if (fill) fill.style.width = "0%";
}

function getSelectedApiItem() {
  if (!cfg.apis.length) return null;
  const apiIdx = parseInt($("#b-api").value, 10);
  if (isNaN(apiIdx) || !cfg.apis[apiIdx]) return null;
  return cfg.apis[apiIdx];
}

function buildBatchParams() {
  const apiItem = getSelectedApiItem();
  if (!apiItem) return { ok: false, error: "Please select an extract API" };
  return {
    ok: true,
    params: {
      api_url: apiItem.url,
      protocol: segValue("batch-proto"),
      target: "",
      count: getBatchCountValue(),
      interval: getBatchIntervalValue(),
      interval_unit: $("#b-interval-unit").value || "s",
      sync_browser: $("#b-sync-browser").checked,
      timeout: cfg.timeout || 10,
      regex: cfg.extract_regex,
      dns_server: cfg.udp_dns || "8.8.8.8",
      username: (apiItem.username || "").trim(),
      password: apiItem.password || "",
      show_response_content: showResponseContent(),
    },
  };
}

function applyCycleResult(idx, cycle) {
  if (cycle.stage === "fetch" || cycle.stage === "parse") {
    updateRow(idx, {
      ipport: cycle.host ? cycle.host + ":" + cycle.port : "—",
      pill: "fail", pillText: "Failed", time: "—",
      note: cycle.error || "",
    });
    return;
  }
  updateRow(idx, {
    ipport: cycle.host + ":" + cycle.port,
    pill: cycle.ok ? "ok" : "fail",
    pillText: cycle.ok ? "Connected" : "Failed",
    time: cycle.ok ? cycle.elapsed_ms + " ms" : "—",
    note: cycle.note || formatBatchNote(cycle),
  });
  if (cycle.public_ip) setPublicIpDisplay(cycle.public_ip);
  if ($("#b-sync-browser").checked) syncClearProxyButtons();
}

function formatBatchNote(ev) {
  if (ev.note) return ev.note;
  if (!ev.ok) return ev.error || "";
  if (ev.content) return ev.content;
  if (ev.status != null) return "HTTP " + ev.status;
  return "Connected";
}

function addRow(idx) {
  const tr = document.createElement("tr");
  tr.id = "row-" + idx;
  tr.innerHTML = `<td>${idx}</td><td class="mono">—</td><td><span class="pill run">Extracting</span></td><td>—</td><td class="li-sub"></td>`;
  $("#b-tbody").prepend(tr);
  return tr;
}

function updateRow(idx, { ipport, pill, pillText, time, note }) {
  const tr = $("#row-" + idx);
  if (!tr) return;
  const tds = tr.children;
  if (ipport !== undefined) tds[1].textContent = ipport;
  if (pill !== undefined) tds[2].innerHTML = `<span class="pill ${pill}">${pillText}</span>`;
  if (time !== undefined) tds[3].textContent = time;
  if (note !== undefined) { tds[4].textContent = note; tds[4].title = note; }
}

window.onBatchEvent = function (ev) {
  switch (ev.type) {
    case "start":
      batchUnlimited = !!ev.unlimited;
      batchStopped = false;
      batchAborted = false;
      hideBatchCountdown();
      $("#st-progress").textContent = batchUnlimited ? "0 / ∞" : ("0 / " + ev.count);
      $("#b-progress").classList.toggle("indeterminate", batchUnlimited);
      if (!batchUnlimited) $("#b-progress").style.width = "0%";
      break;
    case "fetching":
      hideBatchCountdown();
      $("#engineStatus").textContent = "Testing...";
      addRow(ev.index);
      break;
    case "testing":
      hideBatchCountdown();
      $("#engineStatus").textContent = "Testing...";
      updateRow(ev.index, { ipport: ev.host + ":" + ev.port, pill: "run", pillText: "Testing" });
      break;
    case "waiting":
      showBatchCountdown(ev.seconds || 0, ev.seconds || 0);
      break;
    case "countdown":
      showBatchCountdown(ev.remaining || 0, ev.total || ev.remaining || 0);
      break;
    case "countdown_done":
      hideBatchCountdown();
      if (batchRunning) $("#engineStatus").textContent = "Testing...";
      break;
    case "hint":
      if (ev.message) toast(MULTIPLE_RECORDS_HINT);
      break;
    case "result":
      if (ev.stage === "test") {
        updateRow(ev.index, {
          ipport: ev.host + ":" + ev.port,
          pill: ev.ok ? "ok" : "fail",
          pillText: ev.ok ? "Connected" : "Failed",
          time: ev.ok ? ev.elapsed_ms + " ms" : "—",
          note: formatBatchNote(ev),
        });
        if (ev.public_ip) setPublicIpDisplay(ev.public_ip);
        if ($("#b-sync-browser").checked) syncClearProxyButtons();
      } else {
        updateRow(ev.index, {
          ipport: ev.host ? ev.host + ":" + ev.port : "—",
          pill: "fail", pillText: "Failed", time: "—",
          note: ev.error || "",
        });
      }
      break;
    case "progress":
      $("#st-progress").textContent = ev.unlimited ? (ev.done + " / ∞") : (ev.done + " / " + ev.count);
      $("#st-rate").textContent = ev.rate + "%";
      $("#st-avg").textContent = ev.avg_ms + " ms";
      $("#st-success").textContent = ev.success;
      if (ev.unlimited) {
        $("#b-progress").classList.add("indeterminate");
      } else {
        $("#b-progress").classList.remove("indeterminate");
        $("#b-progress").style.width = (ev.count ? (ev.done / ev.count * 100) : 0) + "%";
      }
      break;
    case "stopped":
      batchStopped = true;
      hideBatchCountdown();
      toast("Stopped");
      setBatchRunning(false);
      break;
    case "aborted":
      batchAborted = true;
      hideBatchCountdown();
      showError(ev.error || "Invalid API response format; batch test stopped");
      setBatchRunning(false);
      break;
    case "finished":
      hideBatchCountdown();
      $("#b-progress").classList.remove("indeterminate");
      if (!batchUnlimited) $("#b-progress").style.width = "100%";
      if (!batchAborted && !batchStopped && !batchUnlimited) {
        toast(`Done: success rate ${ev.rate}% · success ${ev.success}/${ev.done} · avg ${ev.avg_ms} ms`);
      }
      if (ev.sync_browser) {
        syncClearProxyButtons();
        loadPublicIp();
      }
      batchAborted = false;
      batchStopped = false;
      batchUnlimited = false;
      setBatchRunning(false);
      $("#engineStatus").textContent = "Ready";
      break;
  }
};

async function runManualSwitch() {
  if (batchRunning) return;
  if (!cfg.apis.length) { toast("Please add extract APIs in Settings first"); return; }
  const built = buildBatchParams();
  if (!built.ok) { toast(built.error); return; }
  saveBatchOptions();

  manualRowSeq += 1;
  const idx = manualRowSeq;
  const btn = $("#b-manual");
  btn.disabled = true;
    btn.textContent = "Testing...";
  addRow(idx);

  let fetchR;
  try {
    fetchR = await api.fetch_one(
      built.params.api_url,
      built.params.regex,
      built.params.timeout,
    );
  } catch (e) {
    fetchR = { ok: false, error: "Extraction failed: " + e };
  }

  if (!fetchR.ok) {
    btn.textContent = "Manual Single Test";
    btn.disabled = false;
    applyCycleResult(idx, { ok: false, stage: "fetch", error: fetchR.error || "Extraction failed" });
    showError(fetchR.error || "Extraction failed");
    return;
  }

  if (fetchR.multiple) toast(MULTIPLE_RECORDS_HINT);

  updateRow(idx, {
    ipport: fetchR.host + ":" + fetchR.port,
    pill: "run",
    pillText: "Testing",
  });

  let cycle;
  try {
    const testR = await api.test_extracted_proxy({
      host: fetchR.host,
      port: fetchR.port,
      protocol: built.params.protocol,
      target: built.params.target,
      timeout: built.params.timeout,
      dns_server: built.params.dns_server,
      username: built.params.username,
      password: built.params.password,
      show_response_content: built.params.show_response_content,
      sync_browser: built.params.sync_browser,
    });
    cycle = { ...testR, host: fetchR.host, port: fetchR.port, stage: "test" };
  } catch (e) {
    cycle = {
      ok: false,
      stage: "test",
      host: fetchR.host,
      port: fetchR.port,
      error: "Test failed: " + e,
    };
  }

    btn.textContent = "Manual Single Test";
  btn.disabled = false;

  applyCycleResult(idx, cycle);
  if (cycle.ok) {
    toast(`Test success: ${cycle.host}:${cycle.port}`);
  } else {
    toast(cycle.error || "Test failed");
  }
}

async function runBatch() {
  if (!cfg.apis.length) { toast("Please add extract APIs in Settings first"); return; }
  const built = buildBatchParams();
  if (!built.ok) { toast(built.error); return; }
  const interval = parseBatchInterval();
  if (!interval.ok) { toast(interval.error); return; }
  if (!interval.unlimited && getBatchCountValue() < 1) {
    toast("Please set extract count (>=1), or configure test interval");
    return;
  }
  saveBatchOptions();
  const params = built.params;
  $("#b-tbody").innerHTML = "";
  $("#st-progress").textContent = interval.unlimited ? "0 / ∞" : ("0 / " + params.count);
  $("#st-rate").textContent = "0%";
  $("#st-avg").textContent = "0 ms";
  $("#st-success").textContent = "0";
  $("#b-progress").classList.toggle("indeterminate", interval.unlimited);
  if (!interval.unlimited) $("#b-progress").style.width = "0%";

  batchAborted = false;
  batchStopped = false;
  batchUnlimited = interval.unlimited;
  setBatchRunning(true);
  const r = await api.start_batch(params);
  if (!r.ok) { toast(r.error || "Unable to start"); setBatchRunning(false); }
}

/* ---------------- Settings actions ---------------- */
function initSettings() {
  const geoChannelEl = $("#set-geo-channel");
  if (geoChannelEl) {
    geoChannelEl.addEventListener("change", () => {
      toggleGeoCustomInput();
    });
  }

  $("#a-add").addEventListener("click", async () => {
    const name = $("#a-name").value.trim() || "Unnamed API";
    const url = $("#a-url").value.trim();
    if (!url) { toast("Please enter API URL"); return; }
    const test = await validateExtractApi(url);
    if (!test.ok) {
      showError(test.error || "API test failed; cannot add");
      return;
    }
    if (test.multiple) {
      toast(MULTIPLE_RECORDS_HINT);
    }
    cfg.apis.push({
      name,
      url,
      username: $("#a-user").value.trim(),
      password: $("#a-pass").value,
    });
    $("#a-name").value = "";
    $("#a-url").value = "";
    $("#a-user").value = "";
    $("#a-pass").value = "";
    persist(); renderApiList(); fillApiSelect();
    toast("API verified and added");
  });
  $("#set-save").addEventListener("click", () => {
    cfg.timeout = parseFloat($("#set-timeout").value) || 10;
    cfg.udp_dns = $("#set-udp-dns").value.trim() || "8.8.8.8";
    cfg.show_response_content = $("#set-show-content").checked;

    const mode = $("#set-geo-channel") ? $("#set-geo-channel").value : (cfg.geo_channel || "ipinfo");
    cfg.geo_channel = mode;
    if (mode === "custom") {
      cfg.geo_custom_url = ($("#set-geo-custom-url") ? $("#set-geo-custom-url").value.trim() : "") || "";
      if (!cfg.geo_custom_url) { toast("Please input Custom Target URL first"); return; }
      const low = cfg.geo_custom_url.toLowerCase();
      if (!low.startsWith("http://") && !low.startsWith("https://")) {
        toast("Custom Target URL must start with http:// or https://");
        return;
      }
    } else {
      cfg.geo_custom_url = "";
    }

    persist();
    loadPublicIp();
    toast("Parameters saved");
  });
}

function initBrandLink() {
  const open = () => api.open_url("https://www.joyproxy.com/");
  $("#brand-link").addEventListener("click", open);
}

/* ---------------- Boot ---------------- */
async function boot() {
  api = await initApiClient();
  cfg = await api.get_config();

  if (document.body.classList.contains("platform-android")) {
    if (cfg.protocol === "s5_udp") cfg.protocol = "http";
    cfg.single_sync_browser = false;
    cfg.batch_sync_browser = false;
  }

  refreshSelects();
  renderApiList();
  setSeg("single-proto", cfg.protocol || "http");
  setSeg("batch-proto", cfg.protocol || "http");
  $("#b-count").value = cfg.batch_count != null ? cfg.batch_count : 10;
  $("#b-interval").value = cfg.batch_interval || 0;
  $("#b-interval-unit").value = cfg.batch_interval_unit || "s";
  $("#b-sync-browser").checked = cfg.batch_sync_browser === true;
  $("#s-sync-browser").checked = cfg.single_sync_browser === true;
  $("#set-timeout").value = cfg.timeout;
  $("#set-udp-dns").value = cfg.udp_dns || "8.8.8.8";
  $("#set-show-content").checked = cfg.show_response_content !== false;
  if ($("#set-geo-channel")) $("#set-geo-channel").value = cfg.geo_channel || "ipinfo";
  if ($("#set-geo-custom-url")) $("#set-geo-custom-url").value = cfg.geo_custom_url || "";
  toggleGeoCustomInput();

  initBrandLink();
  initSingleHostInput();
  initSingleControls();
  initBatchControls();
  refreshAllSyncBrowserUi();
  syncClearProxyButtons();
  loadVersion();
  loadPublicIp();
  $("#s-run").addEventListener("click", runSingle);
  $("#s-clear-proxy").addEventListener("click", clearBrowserProxy);
  $("#b-clear-proxy").addEventListener("click", clearBrowserProxy);
  $("#b-run").addEventListener("click", runBatch);
  $("#b-manual").addEventListener("click", runManualSwitch);
  $("#b-stop").addEventListener("click", async () => { await api.stop_batch(); });
  $("#b-clear").addEventListener("click", () => { $("#b-tbody").innerHTML = ""; });

  $("#single-proto").addEventListener("click", () => {
    cfg.protocol = segValue("single-proto");
    persist();
    refreshAllSyncBrowserUi();
  });
  $("#batch-proto").addEventListener("click", () => {
    cfg.protocol = segValue("batch-proto");
    persist();
    refreshAllSyncBrowserUi();
  });

  initSettings();
}

initTabs();
initSegments();
boot();
