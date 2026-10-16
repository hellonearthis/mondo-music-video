"use strict";
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
let catalog, currentQuote, currentOap, lastState, currentRun, upscaleSource;
const formFiles = new WeakMap();
const sessionLogs = [];
let activeTooltipTrigger = null;
let tooltipTimeout = null;
let saveDebounceTimer = null;

function logSession(message, type = "INFO") {
  const ts = new Date().toLocaleTimeString();
  sessionLogs.push(`[${ts}] [${type}] ${message}`);
  if (sessionLogs.length > 50) sessionLogs.shift();
  if ($("#operation-log") && !$("#operation-log").hidden) updateLogDisplay();
}

function notice(message) {
  $("#notice").textContent = message; $("#notice").hidden = !message;
  $$(".dialog-error").forEach(node => { node.textContent = message; node.hidden = !message; });
  if (message) logSession(message, "NOTICE");
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail); } catch {}
    logSession(`${options.method || "GET"} ${path} -> ${message}`, "ERROR");
    throw new Error(message);
  }
  return response;
}
async function updateLogDisplay() {
  const logElem = $("#operation-log");
  if (!logElem || logElem.hidden) return;
  let serverLog = "";
  try {
    const res = await (await api("/api/log/" + (currentRun || "latest"))).json();
    serverLog = res.log || "";
  } catch (err) {
    serverLog = `(Could not fetch server log: ${err.message})`;
  }
  const clientSection = sessionLogs.length ? `=== Recent Session Activity & Notices ===\n${sessionLogs.join("\n")}\n\n` : "";
  logElem.textContent = clientSection + (serverLog || "No logs recorded yet.");
}
async function copyToClipboard(content) {
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
async function json(path, body, method = "POST") {
  return (await api(path, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})).json();
}
function handle(fn) { return async event => { event?.preventDefault(); try { notice(""); await fn(event); } catch (error) { notice(error.message); } }; }
function option(value, label, tooltip) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  if (tooltip) { node.dataset.tooltip = tooltip; node.title = tooltip; }
  return node;
}
function text(tag, value, className, tooltip) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  if (tooltip) { node.dataset.tooltip = tooltip; node.title = tooltip; }
  return node;
}

// ── WCAG 1.4.13 Compliant Studio Tooltip System ──────────────────────────────
function showTooltip(target) {
  if (!target) return;
  const tipText = target.dataset.tooltip || target.getAttribute("title");
  if (!tipText) return;

  if (target.hasAttribute("title")) {
    target.dataset.tooltip = target.getAttribute("title");
    target.removeAttribute("title");
  }

  activeTooltipTrigger = target;
  target.setAttribute("aria-describedby", "studio-tooltip");
  const tip = $("#studio-tooltip");
  if (!tip) return;
  tip.textContent = tipText;
  tip.hidden = false;

  const rect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  const gap = 8;
  const padding = 10;

  let left = rect.left + (rect.width / 2) - (tipRect.width / 2);
  left = Math.max(padding, Math.min(left, window.innerWidth - tipRect.width - padding));

  let top = rect.bottom + gap;
  if (top + tipRect.height > window.innerHeight - padding) {
    top = Math.max(padding, rect.top - tipRect.height - gap);
  }

  tip.style.left = `${Math.round(left)}px`;
  tip.style.top = `${Math.round(top)}px`;
}

function hideTooltip(immediate = false) {
  clearTimeout(tooltipTimeout);
  const doHide = () => {
    const tip = $("#studio-tooltip");
    if (tip) tip.hidden = true;
    if (activeTooltipTrigger) {
      activeTooltipTrigger.removeAttribute("aria-describedby");
      if (activeTooltipTrigger.dataset.tooltip) {
        activeTooltipTrigger.setAttribute("title", activeTooltipTrigger.dataset.tooltip);
      }
      activeTooltipTrigger = null;
    }
  };
  if (immediate) doHide();
  else tooltipTimeout = setTimeout(doHide, 120);
}

function initTooltips() {
  const tip = $("#studio-tooltip");
  if (tip) {
    tip.onpointerenter = () => clearTimeout(tooltipTimeout);
    tip.onpointerleave = () => hideTooltip(false);
  }

  document.addEventListener("pointerover", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target && !target.closest("#studio-tooltip")) {
      clearTimeout(tooltipTimeout);
      showTooltip(target);
    }
  }, true);

  document.addEventListener("pointerout", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) hideTooltip(false);
  }, true);

  document.addEventListener("focusin", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) {
      clearTimeout(tooltipTimeout);
      showTooltip(target);
    }
  }, true);

  document.addEventListener("focusout", event => {
    const target = event.target.closest("[data-tooltip], [title]");
    if (target) hideTooltip(true);
  }, true);

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") hideTooltip(true);
  });
}

// ── Project State Persistence ───────────────────────────────────────────────
function panel(name) {
  $$(".panel").forEach(node => node.hidden = node.id !== "panel-" + name);
  $$(".nav[data-panel]").forEach(node => {
    const active = node.dataset.panel === name;
    node.classList.toggle("active", active);
    node.setAttribute("aria-current", active ? "page" : "false");
  });
  scheduleSave();
}

function getProjectState() {
  const activeNav = $(".nav.active[data-panel]");
  const panelName = activeNav ? activeNav.dataset.panel : "video";
  const forms = {};
  const files = {};

  ["video-form", "harvest-form", "ident-form", "actor-form", "style-form"].forEach(id => {
    const form = $("#" + id);
    if (!form) return;
    const data = {};
    [...form.elements].forEach(el => {
      if (!el.name || el.type === "file" || el.type === "password" || el.type === "submit" || el.type === "button") return;
      if (el.tagName === "SELECT" && el.multiple) {
        data[el.name] = [...el.selectedOptions].map(o => o.value);
      } else if (el.type === "checkbox") {
        data[el.name] = el.checked;
      } else {
        data[el.name] = el.value;
      }
    });
    forms[id] = data;

    const fileState = formFiles.get(form);
    if (fileState) {
      files[id] = {
        song: fileState.song || "",
        songName: fileState.songName || "",
        references: fileState.references || [],
        referenceNames: fileState.referenceNames || []
      };
    }
  });

  return {
    panel: panelName,
    forms,
    files,
    details_open: Boolean($("#video-form details")?.open),
    log_open: Boolean($("#operation-log") && !$("#operation-log").hidden)
  };
}

async function saveProject() {
  const state = getProjectState();
  try { localStorage.setItem("mmv_project_draft", JSON.stringify(state)); } catch {}
  try { await json("/api/project", state, "PUT"); } catch {}
}

function scheduleSave() {
  clearTimeout(saveDebounceTimer);
  saveDebounceTimer = setTimeout(saveProject, 250);
}

async function restoreProject() {
  let saved = null;
  try {
    const res = await api("/api/project");
    if (res.ok) saved = await res.json();
  } catch {}

  if (!saved || !saved.panel) {
    try {
      const local = localStorage.getItem("mmv_project_draft");
      if (local) saved = JSON.parse(local);
    } catch {}
  }
  if (!saved) return;

  if (saved.panel) panel(saved.panel);
  if (saved.details_open !== undefined) {
    const det = $("#video-form details");
    if (det) det.open = Boolean(saved.details_open);
  }
  if (saved.log_open && $("#operation-log")) {
    $("#operation-log").hidden = false;
    $("#show-log").textContent = "Hide log";
    updateLogDisplay();
  }

  const formsData = saved.forms || {};
  Object.entries(formsData).forEach(([formId, data]) => {
    const form = $("#" + formId);
    if (!form) return;

    if (data.backend && form.querySelector(".backend-select")) {
      const bSelect = form.querySelector(".backend-select");
      bSelect.value = data.backend;
      resolutionSelect(form);
    }

    Object.entries(data).forEach(([name, val]) => {
      const el = form.elements[name];
      if (!el) return;
      if (el.tagName === "SELECT" && el.multiple && Array.isArray(val)) {
        [...el.options].forEach(opt => opt.selected = val.includes(opt.value));
      } else if (el.type === "checkbox") {
        el.checked = Boolean(val);
      } else {
        el.value = val;
      }
    });
  });

  const filesData = saved.files || {};
  Object.entries(filesData).forEach(([formId, fileState]) => {
    const form = $("#" + formId);
    if (!form) return;
    const state = formFiles.get(form) || { references: [], pending: 0 };
    if (fileState.song) {
      state.song = fileState.song;
      state.songName = fileState.songName || fileState.song;
      const receipt = form.querySelector(".song-receipt");
      if (receipt) receipt.textContent = "Uploaded: " + state.songName;
      const songInput = form.querySelector(".song-input");
      if (songInput) songInput.required = false;
    }
    if (Array.isArray(fileState.references) && fileState.references.length) {
      state.references = fileState.references;
      state.referenceNames = fileState.referenceNames || fileState.references;
      const receipt = form.querySelector(".refs-receipt");
      if (receipt) receipt.textContent = state.referenceNames.join(" · ");
      const refsInput = form.querySelector(".refs-input");
      if (refsInput && form.dataset.kind === "harvest") refsInput.required = false;
    }
    formFiles.set(form, state);
  });
}

async function upload(file, kind) {
  const body = new FormData(); body.append("file", file);
  return (await (await api("/api/upload/" + kind, {method: "POST", body})).json()).file;
}

function resolutionSelect(form) {
  const backend = form.querySelector(".backend-select").value;
  const select = form.querySelector(".resolution-select");
  const old = select.value;
  const resolutions = catalog.backends[backend]?.resolutions || [];
  select.replaceChildren(...resolutions.map(value => option(value, value, `Render resolution ${value} for ${catalog.backends[backend]?.name || backend}`)));
  if ([...select.options].some(item => item.value === old)) select.value = old;
}

async function loadStyles() {
  const styles = await (await api("/api/styles")).json();
  $$(".style-select").forEach(select => {
    const old = select.value;
    select.replaceChildren(...styles.map(style => option(style.id, style.name, `${style.name} (${style.id})`)));
    if (styles.some(x => x.id === old)) select.value = old;
  });
  $("#style-list").replaceChildren(...styles.map(style => {
    const card = text("article", "", "card", `Style card: ${style.name}`);
    card.append(text("h2", style.name), text("p", style.direction));
    return card;
  }));
}

async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  $$(".actor-select").forEach(select => {
    const old = [...select.selectedOptions].map(x => x.value);
    select.replaceChildren(...actors.map(actor => {
      const node = option(actor.id, actor.name, `Cast actor: ${actor.name} (${actor.id})`);
      node.selected = old.includes(actor.id);
      return node;
    }));
  });
  $("#actor-list").replaceChildren(...actors.map(actor => {
    const card = text("article", "", "card", `Cast member: ${actor.name}`);
    const image = document.createElement("img");
    image.src = `/api/actors/${encodeURIComponent(actor.id)}/reference`;
    image.alt = actor.name + " reference";
    image.loading = "lazy";
    image.dataset.tooltip = `Reference portrait for ${actor.name}`;
    image.title = image.dataset.tooltip;

    const button = text("button", "Export OAP package", "secondary", `Export signed OAP package for ${actor.name}`);
    button.onclick = handle(async () => {
      const response = await api(`/api/actors/${encodeURIComponent(actor.id)}/export`, {method: "POST"});
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = actor.id + ".oap";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    });
    card.append(image, text("h2", actor.name), text("p", actor.description), text("p", actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export"), button);
    return card;
  }));
  if (!actors.length) $("#actor-list").append(text("div", "Your cast starts here. Create an actor or import a full OAP package below.", "empty", "No actors currently in your studio library"));
}

async function loadOutputs() {
  const outputs = await (await api("/api/outputs")).json();
  $("#output-list").replaceChildren(...outputs.map(output => {
    const card = text("article", "", "card", `Rendered output: ${output.title}`);
    const video = document.createElement("video");
    video.src = "/api/media/" + output.file;
    video.controls = true;
    video.preload = "metadata";
    video.dataset.tooltip = `Video player for ${output.title}`;
    video.title = video.dataset.tooltip;

    const download = text("a", "Download", "download", `Download ${output.title} as MP4`);
    download.href = "/api/media/" + output.file + "?download=true";

    const upscale = text("button", "Topaz upscale ↗", "quiet", `Upscale ${output.title} using Topaz Video AI`);
    upscale.onclick = () => { upscaleSource = output.file; $("#upscale-dialog").showModal(); };

    card.append(video, text("h2", output.title), text("p", `${output.kind} · ${Number(output.duration).toFixed(1)} seconds`), download, upscale);
    return card;
  }));
  if (!outputs.length) $("#output-list").append(text("div", "Your finished videos and idents will appear here.", "empty", "No completed productions yet"));
  $$(".ident-select").forEach(select => {
    const old = select.value;
    select.replaceChildren(option("", "None", "No ident clip attached"), ...outputs.filter(output => output.kind === "ident").map(output => option(output.file, output.title, `Ident clip: ${output.title}`)));
    if ([...select.options].some(item => item.value === old)) select.value = old;
  });
}

const settingLabels = {
  comfy_sdk_url: "Local Comfy API proxy URL",
  backend: "Default renderer", comfy_url: "ComfyUI service URL", comfy_input: "ComfyUI input folder (shared local path)", comfy_output: "ComfyUI output folder (shared local path)",
  writer_launch: "Local writer launch command (JSON arguments)", writer_cwd: "Writer working folder", comfy_launch: "ComfyUI launch command (JSON arguments)", comfy_cwd: "ComfyUI working folder",
  laya_model_dir: "Laya model folder", laya_device: "Laya device (cpu, cuda, mps)",
  writer_url: "Writer service URL (OpenAI-compatible /v1)", writer_model: "Music-video writer model", writer_mode: "Writer service: local or API", writer_call_estimate: "API writer estimate per call, USD",
  workflow_map_path: "Workflow binding map JSON path",
  vision_url: "Vision service URL (OpenAI-compatible /v1)", vision_model: "Vision model name", vision_key_env: "Vision credential name",
  vision_call_estimate: "Vision estimate per call, USD (0 for local)", topaz_executable: "Installed Topaz FFmpeg executable path", topaz_models: "Installed Topaz models folder"
};

const settingTooltips = {
  comfy_sdk_url: "Official Comfy API v2 proxy on this machine, usually http://127.0.0.1:8189",
  backend: "Default video generation engine for music videos and idents",
  comfy_url: "HTTP URL for your running ComfyUI service instance",
  comfy_input: "Shared local filesystem path to ComfyUI's input directory",
  comfy_output: "Shared local filesystem path to ComfyUI's output directory",
  writer_launch: "Optional JSON argument list to automatically launch a local llama-server writer",
  writer_cwd: "Working directory for the local writer process",
  comfy_launch: "Optional JSON argument list to automatically launch ComfyUI for local rendering",
  comfy_cwd: "Working directory for launching ComfyUI",
  laya_model_dir: "Path to folder containing Laya model.safetensors and config files",
  laya_device: "Hardware execution device for local Laya prompt review (cuda, cpu, mps)",
  writer_url: "OpenAI-compatible /v1 endpoint URL for the music-video writer LLM",
  writer_model: "Model identifier name served by your writer LLM service",
  writer_mode: "Select 'local' for private local engines or 'api' for cloud providers",
  writer_call_estimate: "Estimated cost in USD per writer generation call",
  workflow_map_path: "Filesystem path to the ComfyUI node injection map JSON",
  vision_url: "OpenAI-compatible /v1 endpoint for multimodal vision style harvesting",
  vision_model: "Model identifier for your vision service",
  vision_key_env: "Environment variable name storing your vision API key",
  vision_call_estimate: "Estimated cost in USD per vision style-harvest call",
  topaz_executable: "Path to Topaz Video AI ffmpeg.exe binary for upscaling",
  topaz_models: "Folder path containing installed Topaz AI model weight files"
};

async function loadSettings() {
  const data = await (await api("/api/settings")).json();
  $("#settings-fields").replaceChildren(...Object.entries(data.settings).map(([name, value]) => {
    const tip = settingTooltips[name] || settingLabels[name] || name;
    const label = text("label", settingLabels[name] || name, "", tip);
    let input;
    if (name === "writer_mode") {
      input = document.createElement("select");
      input.append(option("local", "Local", "Local writer engine"), option("api", "API", "Hosted cloud API provider"));
    } else if (name === "backend") {
      input = document.createElement("select");
      input.append(...Object.entries(catalog.backends).map(([key, card]) => option(key, card.name, `${card.name}: ${card.description || key}`)));
    } else {
      input = document.createElement("input");
      input.type = name.endsWith("call_estimate") ? "number" : "text";
      if (input.type === "number") { input.min = "0"; input.max = "100"; input.step = "0.001"; }
    }
    input.name = name;
    input.value = value;
    input.dataset.tooltip = tip;
    input.title = tip;
    if (name === "vision_key_env") input.readOnly = true;
    label.append(input);
    return label;
  }));
  $("#key-status").textContent = Object.entries(data.keys).map(([name, set]) => `${name}: ${set ? "configured" : "not set"}`).join(" · ");
  return data.settings;
}

async function preview(form) {
  const data = Object.fromEntries(new FormData(form)), files = formFiles.get(form) || {references: []};
  if (files.pending) throw new Error("Wait for the selected files to finish uploading");
  const request = {kind: form.dataset.kind, ...data, references: files.references};
  if (request.kind === "video") {
    if (!files.song) throw new Error("Upload your song first");
    request.song = files.song;
    request.actors = [...form.querySelector(".actor-select").selectedOptions].map(item => item.value);
    for (const name of ["megapixels", "beats_per_bar", "bars_per_phrase", "seed", "on_screen"]) request[name] = Number(request[name]);
    request.silent_mouths = request.silent_mouths === "true";
    request.reuse_prompts = form.elements.reuse_prompts ? form.elements.reuse_prompts.checked : true;
    request.content = {};
    for (const category of Object.keys(catalog.ratings)) { request.content[category] = request["rating_" + category]; delete request["rating_" + category]; }
  }
  if (request.kind === "ident") request.ident_seconds = Number(request.ident_seconds);
  logSession(`Preview requested for kind='${request.kind}' backend='${request.backend}'`);
  currentQuote = await json("/api/quote", request);
  logSession(`Preview ready: quote_id='${currentQuote.id}' estimate=$${Number(currentQuote.estimate_usd).toFixed(2)}`);
  showQuote(request, currentQuote);
}

function showQuote(request, quote) {
  currentQuote = quote;
  const summary = $("#quote-summary"); summary.replaceChildren();
  summary.append(text("p", request.kind === "harvest" ? "One visual style harvest." : `${currentQuote.clips} clips · ${currentQuote.seconds.toFixed(1)} seconds of ${request.kind === "ident" ? "ident" : "music"}.`),
                 text("h2", `Estimated provider cost: $${Number(currentQuote.estimate_usd).toFixed(2)}`), text("p", currentQuote.note, "muted"));
  if (currentQuote.analysis && request.kind === "video") {
    const a = currentQuote.analysis;
    summary.append(text("p", `Detected tempo: ${a.tempo_bpm.toFixed(1)} BPM · ${a.beats} beats · ${a.downbeats} downbeats · ${a.sections} sections · ${a.shots} shots · ${a.width} × ${a.height}`));
    for (const passage of currentQuote.segments) {
      summary.append(text("p", `${(passage.song_start_frame / 24).toFixed(2)}s · ${passage.section_label} · ${passage.montage_type.replaceAll("_", " ")} · ${passage.shots.length} shots`));
    }
  }
  $("#consent").checked = false; $("#preview-dialog").showModal();
}

async function poll() {
  try {
    const status = await (await api("/api/status")).json();
    currentRun = status.id;
    const busy = ["running", "cancelling"].includes(status.state);
    $("#status-title").textContent = status.state === "idle" ? "READY WHEN YOU ARE" : status.state.toUpperCase();
    $("#status-message").textContent = status.message || "One idea. One production at a time.";
    $("#progress").value = status.progress || 0;
    $("#cancel").hidden = !busy;
    $("#resume-production").hidden = !status.can_resume;
    $("#show-log").hidden = false;
    $$(".operation-action").forEach(button => button.disabled = busy);
    if (lastState && lastState !== status.state && !busy) { await Promise.all([loadActors(), loadStyles(), loadOutputs()]); }
    lastState = status.state;
    if (!$("#operation-log").hidden) await updateLogDisplay();
  } catch (error) { $("#status-message").textContent = "Connection unavailable. The server may have stopped."; }
  setTimeout(poll, 2000);
}

async function initialize() {
  initTooltips();
  catalog = await (await api("/api/catalog")).json();
  const version = await (await api("/api/version")).json();
  $("#version").textContent = version.version; $("#oap-version").textContent = catalog.oap_version;
  $$(".backend-select").forEach(select => {
    select.append(...Object.entries(catalog.backends).map(([key, card]) => option(key, card.name, `${card.name}: ${card.description || key}`)));
    select.onchange = () => { resolutionSelect(select.closest("form")); scheduleSave(); };
  });
  for (const [name, levels] of Object.entries(catalog.ratings)) {
    const tip = `OAP rating ceiling for ${name.replaceAll("_", " ")}`;
    const label = text("label", name.replaceAll("_", " "), "", tip);
    const select = document.createElement("select");
    select.name = "rating_" + name;
    select.dataset.tooltip = tip;
    select.title = tip;
    select.append(...levels.map(level => option(level, level, `Content rating level: ${level}`)));
    select.onchange = scheduleSave;
    label.append(select);
    $(".ratings").append(label);
  }
  const [settings] = await Promise.all([loadSettings(), loadActors(), loadStyles(), loadOutputs()]);
  $$(".backend-select").forEach(select => { select.value = settings.backend; resolutionSelect(select.closest("form")); });
  $$(".nav[data-panel]").forEach(button => button.onclick = () => panel(button.dataset.panel));
  const teasers = {"Short films": "From screenplay to screen, with the full studio's film production tools.", "Micro Drama": "A home for episodic stories and serial drama in the full studio.", "Hodge TV": "Channel-surf broadcasts and programme variety in the full studio.", "The cutting room": "Editing and production refinement in the full studio.", "The Vault": "A library of archival footage in the full studio."};
  $$(".teaser").forEach(button => button.onclick = () => { $("#teaser-title").textContent = button.dataset.feature; $("#teaser-description").textContent = teasers[button.dataset.feature]; panel("teaser"); });
  $("#back-to-video").onclick = () => panel("video");
  $$(".production-form, #actor-form, #style-form").forEach(form => {
    form.addEventListener("input", scheduleSave);
    form.addEventListener("change", scheduleSave);
  });
  const videoDetails = $("#video-form details");
  if (videoDetails) videoDetails.addEventListener("toggle", scheduleSave);

  $$(".production-form").forEach(form => {
    formFiles.set(form, {references: [], pending: 0});
    form.onsubmit = handle(() => preview(form));
    const song = form.querySelector(".song-input");
    if (song) song.onchange = handle(async () => {
      const selected = song.files[0]; if (!selected) return;
      const state = formFiles.get(form); state.song = undefined; state.songName = undefined; state.pending++;
      song.disabled = true; form.querySelector(".song-receipt").textContent = "Uploading " + selected.name + "…";
      try {
        state.song = await upload(selected, "song");
        state.songName = selected.name;
        form.querySelector(".song-receipt").textContent = "Uploaded: " + selected.name;
        song.required = false;
        scheduleSave();
      }
      catch (error) { form.querySelector(".song-receipt").textContent = "Upload failed; select the song again."; throw error; }
      finally { state.pending--; song.disabled = false; }
    });
    form.querySelector(".refs-input").onchange = handle(async event => {
      const files = [...event.target.files];
      if (files.length > 9) throw new Error("Choose at most nine reference images");
      const state = formFiles.get(form); state.references = []; state.referenceNames = []; state.pending++;
      event.target.disabled = true; form.querySelector(".clear-refs").disabled = true;
      form.querySelector(".refs-receipt").textContent = "Uploading reference images…";
      try {
        for (const file of files) {
          state.references.push(await upload(file, "reference"));
          state.referenceNames.push(file.name);
        }
        form.querySelector(".refs-receipt").textContent = files.map(file => file.name).join(" · ") || "No reference images";
        if (form.dataset.kind === "harvest") event.target.required = false;
        scheduleSave();
      } catch (error) { state.references = []; state.referenceNames = []; form.querySelector(".refs-receipt").textContent = "Upload failed; select references again."; throw error; }
      finally { state.pending--; event.target.disabled = false; form.querySelector(".clear-refs").disabled = false; }
    });
    form.querySelector(".clear-refs").onclick = () => {
      const state = formFiles.get(form);
      state.references = [];
      state.referenceNames = [];
      form.querySelector(".refs-input").value = "";
      form.querySelector(".refs-receipt").textContent = "No reference images";
      if (form.dataset.kind === "harvest") form.querySelector(".refs-input").required = true;
      scheduleSave();
    };
  });
  $("#resume-production").onclick = handle(async () => {
    const quote = await json("/api/resume/quote", {run_id: currentRun});
    showQuote({kind: quote.kind}, quote);
  });
  $("#start-production").onclick = handle(async () => {
    if (!$("#consent").checked) throw new Error("Accept the preview before starting");
    logSession(`Starting production for quote '${currentQuote.id}'`);
    await json("/api/start", {quote_id: currentQuote.id, consent: true}); $("#preview-dialog").close();
  });
  $("#cancel").onclick = handle(() => {
    logSession("Cancellation requested by operator");
    return api("/api/cancel", {method: "POST"});
  });
  $("#show-log").onclick = handle(async () => {
    const logElem = $("#operation-log");
    logElem.hidden = !logElem.hidden;
    $("#show-log").textContent = logElem.hidden ? "View log" : "Hide log";
    scheduleSave();
    if (!logElem.hidden) await updateLogDisplay();
  });
  $("#copy-log").onclick = handle(async () => {
    let content = $("#operation-log").textContent;
    if (!content || $("#operation-log").hidden) {
      await updateLogDisplay();
      content = $("#operation-log").textContent;
    }
    if (!content) content = "No logs recorded yet.";
    const ok = await copyToClipboard(content);
    if (ok) {
      const orig = $("#copy-log").textContent;
      $("#copy-log").textContent = "Copied!";
      setTimeout(() => { $("#copy-log").textContent = orig; }, 2000);
      notice("Operation log copied to clipboard.");
      setTimeout(() => { if ($("#notice").textContent === "Operation log copied to clipboard.") notice(""); }, 3000);
    } else {
      throw new Error("Unable to copy to clipboard. Please copy manually from the log view.");
    }
  });
  $("#clear-log").onclick = handle(async () => {
    sessionLogs.length = 0;
    await api("/api/log/clear", {method: "POST"});
    $("#operation-log").textContent = "Log cleared. Waiting for new activity.";
    notice("Diagnostic log cleared.");
    setTimeout(() => { if ($("#notice").textContent === "Diagnostic log cleared.") notice(""); }, 2000);
  });
  const rerollSeedBtn = $("#reroll-seed");
  if (rerollSeedBtn) {
    rerollSeedBtn.onclick = handle(() => {
      const input = $('input[name="seed"]');
      if (input) {
        input.value = Math.floor(Math.random() * 2147483647);
        notice(`New variation seed generated: ${input.value}`);
        setTimeout(() => { if ($("#notice").textContent.startsWith("New variation seed")) notice(""); }, 3000);
        scheduleSave();
      }
    });
  }
  const clearCacheBtn = $("#clear-cache");
  if (clearCacheBtn) {
    clearCacheBtn.onclick = handle(async () => {
      const res = await (await api("/api/cache/clear", {method: "POST"})).json();
      notice(`Prompt cache cleared (${res.count || 0} files removed).`);
      setTimeout(() => { if ($("#notice").textContent.startsWith("Prompt cache cleared")) notice(""); }, 3000);
    });
  }
  $("#actor-form").onsubmit = handle(async event => { await api("/api/actors", {method: "POST", body: new FormData(event.target)}); event.target.reset(); await loadActors(); scheduleSave(); });
  $("#style-form").onsubmit = handle(async event => { await json("/api/styles", Object.fromEntries(new FormData(event.target))); event.target.reset(); await loadStyles(); scheduleSave(); });
  $("#inspect-oap").onclick = handle(async () => {
    const file = $("#oap-file").files[0]; if (!file) throw new Error("Choose an OAP package first");
    currentOap = await upload(file, "oap");
    const report = await (await api(`/api/oap/inspect/${currentOap}?allow_unsigned=${$("#allow-unsigned").checked}`)).json();
    $("#oap-report").textContent = JSON.stringify(report, null, 2); $("#oap-report").hidden = false; $("#oap-import-form").hidden = false;
  });
  $("#oap-import-form").onsubmit = handle(async event => {
    const body = new FormData(event.target); body.set("filename", currentOap); body.set("allow_unsigned", String($("#allow-unsigned").checked)); body.set("accept_unknown", String(event.target.elements.accept_unknown.checked));
    await api("/api/oap/import", {method: "POST", body}); event.target.hidden = true; $("#oap-report").hidden = true; await loadActors();
  });
  $("#settings-form").onsubmit = handle(async event => { const body = Object.fromEntries(new FormData(event.target)); body.vision_call_estimate = Number(body.vision_call_estimate); body.writer_call_estimate = Number(body.writer_call_estimate); await json("/api/settings", body, "PUT"); notice("Settings saved."); });
  $("#key-form").onsubmit = handle(async event => { await json("/api/key", Object.fromEntries(new FormData(event.target)), "PUT"); event.target.elements.value.value = ""; await loadSettings(); notice("Key saved locally. The settings API does not return it."); });
  $("#upscale-form").onsubmit = handle(async event => { const body = Object.fromEntries(new FormData(event.target)); body.scale = Number(body.scale); await json("/api/upscale", {...body, source: upscaleSource}); $("#upscale-dialog").close(); });

  await restoreProject();
  poll();
}
initialize().catch(error => notice(error.message));
