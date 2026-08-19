"use strict";

function createHttpApi() {
  async function rpc(method, kwargs = {}) {
    const r = await fetch("/api/rpc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, kwargs }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || `Request failed (${r.status})`);
    }
    return r.json();
  }

  return {
    get_config: () => rpc("get_config"),
    get_version: () => rpc("get_version"),
    save_config: (cfg) => rpc("save_config", { cfg }),
    open_url: (url) => rpc("open_url", { url }),
    fetch_public_ip: (target, timeout) => rpc("fetch_public_ip", { target, timeout }),
    get_system_proxy_status: () => rpc("get_system_proxy_status"),
    clear_system_proxy: () => rpc("clear_system_proxy"),
    fetch_one: (api_url, regex, timeout) => rpc("fetch_one", { api_url, regex, timeout }),
    test_single: (host, port, protocol, target, timeout, dns_server, username, password, show_content, sync_browser) =>
      rpc("test_single", {
        host, port, protocol, target, timeout, dns_server, username, password, show_content, sync_browser,
      }),
    test_extracted_proxy: (params) => rpc("test_extracted_proxy", { params }),
    start_batch: (params) => rpc("start_batch", { params }),
    stop_batch: () => rpc("stop_batch"),
    browser_proxy_supported: (protocol) => rpc("browser_proxy_supported", { protocol }),
  };
}

let _batchEventSource = null;

function connectBatchSSE() {
  if (_batchEventSource) return;
  _batchEventSource = new EventSource("/api/batch/events");
  _batchEventSource.onmessage = (ev) => {
    if (!ev.data) return;
    try {
      const payload = JSON.parse(ev.data);
      if (typeof window.onBatchEvent === "function") {
        window.onBatchEvent(payload);
      }
    } catch (_) { /* ignore */ }
  };
  _batchEventSource.onerror = () => {
    /* EventSource auto-reconnects */
  };
}

window.createHttpApi = createHttpApi;
window.connectBatchSSE = connectBatchSSE;
