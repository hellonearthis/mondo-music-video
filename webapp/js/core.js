// Core state, DOM utilities, HTTP client, clipboard, and session logging.

export const $ = selector => document.querySelector(selector);
export const $$ = selector => [...document.querySelectorAll(selector)];

export const state = {
  catalog: null,
  currentQuote: null,
  currentOap: null,
  lastState: null,
  currentRun: null,
  upscaleSource: null,
  captionSource: null,
  currentCustomVocab: {},
  currentVocabRandomKey: "",
  thematicWorlds: null,
  formFiles: new WeakMap(),
  sessionLogs: []
};

export function updateThemeToggle() {
  const themeToggle = $("#theme-toggle");
  if (!themeToggle) return;
  const dark = document.documentElement.dataset.theme !== "light";
  themeToggle.setAttribute("aria-pressed", String(dark));
  themeToggle.textContent = dark ? "Dark mode" : "Light mode";
  themeToggle.title = dark ? "Switch to light mode" : "Switch to dark mode";
}

export function initThemeToggle() {
  const themeToggle = $("#theme-toggle");
  if (!themeToggle) return;
  themeToggle.onclick = () => {
    const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("mmv-theme", theme); } catch {}
    updateThemeToggle();
  };
  updateThemeToggle();
}

export function logSession(message, type = "INFO") {
  const ts = new Date().toLocaleTimeString();
  state.sessionLogs.push(`[${ts}] [${type}] ${message}`);
  if (state.sessionLogs.length > 50) state.sessionLogs.shift();
  if ($("#operation-log") && !$("#operation-log").hidden) updateLogDisplay();
}

export function notice(message, log = true) {
  const noticeElem = $("#notice");
  if (noticeElem) {
    noticeElem.textContent = message;
    noticeElem.hidden = !message;
  }
  $$(".dialog-error").forEach(node => {
    node.textContent = message;
    node.hidden = !message;
  });
  if (message && log) logSession(message, "NOTICE");
}

export async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    logSession(`${options.method || "GET"} ${path} -> ${message}`, "ERROR");
    throw new Error(message);
  }
  return response;
}

export async function updateLogDisplay() {
  const logElem = $("#operation-log");
  if (!logElem || logElem.hidden) return;
  let serverLog = "";
  try {
    const res = await (await api("/api/log/" + (state.currentRun || "latest"))).json();
    serverLog = res.log || "";
    if (serverLog === "No operation or server log recorded yet.") {
      serverLog = "";
    }
  } catch (err) {
    serverLog = `(Could not fetch server log: ${err.message})`;
  }
  const clientSection = state.sessionLogs.length
    ? `=== Recent Session Activity & Notices ===\n${state.sessionLogs.join("\n")}\n\n`
    : "";
  const full = (clientSection + serverLog).trim();
  logElem.textContent = full || "Log cleared. Waiting for new activity.";
}

export async function copyToClipboard(content) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(content);
      return true;
    }
  } catch {}
  try {
    const textarea = document.createElement("textarea");
    textarea.value = content;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const successful = document.execCommand("copy");
    document.body.removeChild(textarea);
    return successful;
  } catch {
    return false;
  }
}

export async function json(path, body, method = "POST") {
  return (await api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  })).json();
}

export function handle(fn) {
  return async event => {
    event?.preventDefault();
    try {
      notice("");
      await fn(event);
    } catch (error) {
      notice(error.message);
    }
  };
}

export function option(value, label, tooltip) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  if (tooltip) {
    node.dataset.tooltip = tooltip;
    node.title = tooltip;
  }
  return node;
}

export const keyNames = {
  WAVESPEED_API_KEY: "WaveSpeed (video rendering)",
  MMV_WRITER_API_KEY: "Writer service",
  MMV_VISION_API_KEY: "Vision service",
  MMV_COMFY_API_KEY: "ComfyUI API proxy",
  MMV_TOPAZ_API_KEY: "Topaz cloud (upscale)"
};

// One paste-and-save row for any provider key. `saved` is whether a key exists; `onSaved(configured)` follows a save.
export function keyRow(name, saved, onSaved) {
  const row = document.createElement("div");
  row.className = "key-row";
  const label = document.createElement("label");
  label.dataset.tooltip = label.title = `Paste your ${keyNames[name] || name} key; it is stored privately on this machine`;
  const status = text("span", saved ? "saved" : "not set", "muted");
  label.append(`${keyNames[name] || name} `, status);
  const input = document.createElement("input");
  input.type = "password";
  input.autocomplete = "new-password";
  input.placeholder = saved ? "Paste a new key to replace it" : "Paste key here";
  input.dataset.tooltip = input.title = "Paste the key from your provider account";
  label.append(input);
  const save = text("button", "Save key", "secondary", "Save this key locally; it is never shown again");
  save.type = "button";
  save.onclick = handle(async () => {
    const result = await json("/api/key", { name, value: input.value.trim() }, "PUT");
    input.value = "";
    status.textContent = result.configured ? "saved" : "not set";
    notice(result.configured ? `${keyNames[name] || name} key saved on this machine` : "No key saved");
    if (onSaved) await onSaved(result.configured);
  });
  row.append(label, save);
  return row;
}

export function text(tag, value, className, tooltip) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  if (tooltip) {
    node.dataset.tooltip = tooltip;
    node.title = tooltip;
  }
  return node;
}

export async function upload(file, kind) {
  const body = new FormData();
  body.append("file", file);
  return (await (await api("/api/upload/" + kind, { method: "POST", body })).json()).file;
}

export async function saveDownload(response, filename) {
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

