"use strict";
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const themeToggle = $("#theme-toggle");
function updateThemeToggle() {
  const dark = document.documentElement.dataset.theme !== "light";
  themeToggle.setAttribute("aria-pressed", String(dark));
  themeToggle.textContent = dark ? "Dark mode" : "Light mode";
  themeToggle.title = dark ? "Switch to light mode" : "Switch to dark mode";
}
themeToggle.onclick = () => {
  const theme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("mmv-theme", theme); } catch {}
  updateThemeToggle();
};
updateThemeToggle();

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
      updateSongPreview(form, "/api/uploads/song/" + encodeURIComponent(state.song));
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

function updateSongPreview(form, src) {
  const wrap = form.querySelector(".song-preview-wrap");
  const audio = form.querySelector(".song-preview");
  if (!wrap || !audio) return;
  if (src) {
    audio.src = src;
    wrap.hidden = false;
  } else {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    wrap.hidden = true;
  }
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

function actorOverview(actor) {
  const description = actor.description || "";
  const identity = description.match(/(?:^|\n)Identity:\s*([\s\S]*?)(?=\n(?:Hair|Makeup|Wardrobe|Footwear|Accessories|Expression Range|Detail Notes|Canonical Summary|Height):|$)/i);
  return identity ? identity[1].trim() : description;
}

async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  $$(".actor-select").forEach(select => {
    const old = [...select.selectedOptions].map(x => x.value);
    if (!actors.length) {
      const emptyOpt = option("", "No cast members yet — add in 02. Actors & OAP", "No cast members currently in your studio library");
      emptyOpt.disabled = true;
      select.replaceChildren(emptyOpt);
    } else {
      select.replaceChildren(...actors.map(actor => {
        const node = option(actor.id, actor.name, `Cast actor: ${actor.name} (${actor.id})`);
        node.selected = old.includes(actor.id);
        return node;
      }));
    }
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
    card.append(image, text("h2", actor.name), text("p", actorOverview(actor)), text("p", actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export"), button);
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
  vision_call_estimate: "Vision estimate per call, USD (0 for local)", topaz_executable: "Installed Topaz FFmpeg executable path", topaz_models: "Installed Topaz models folder",
  h3_video_vae: "H3 video VAE model",
  h3_audio_vae: "H3 audio VAE model",
  h3_diffusion_model: "H3 reference-to-video diffusion model",
  h3_text_encoder: "H3 text encoder (CLIP) model"
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
  topaz_models: "Folder path containing installed Topaz AI model weight files",
  h3_video_vae: "Video VAE safetensors filename for MiniMax H3 (node 119)",
  h3_audio_vae: "Audio VAE safetensors filename for MiniMax H3 (node 120)",
  h3_diffusion_model: "Reference-to-video UNET diffusion model for MiniMax H3 (node 127)",
  h3_text_encoder: "Text encoder CLIP model for MiniMax H3 (node 128)"
};

const folderSettings = new Set([
  "comfy_input",
  "comfy_output",
  "writer_cwd",
  "comfy_cwd",
  "laya_model_dir",
  "topaz_models"
]);

const fileSettings = {
  topaz_executable: ".exe",
  workflow_map_path: ".json"
};

let pickerNavigation = 0;
let currentPickerState = {
  mode: "folder",
  ext: "",
  current: "",
  onSelect: null,
  allEntries: []
};

async function navigatePicker(targetPath) {
  const navigation = ++pickerNavigation;
  $("#picker-confirm").disabled = true;
  const params = new URLSearchParams();
  if (targetPath) params.set("path", targetPath);
  params.set("mode", currentPickerState.mode);
  if (currentPickerState.ext) params.set("ext", currentPickerState.ext);

  const res = await api("/api/fs/browse?" + params.toString());
  if (!res.ok) return;
  const data = await res.json();
  if (navigation !== pickerNavigation || !$("#folder-picker-dialog").open) return;
  currentPickerState.current = data.current;

  $("#picker-selected-path").value = currentPickerState.mode === "folder" ? data.current : "";
  $("#picker-confirm").disabled = currentPickerState.mode === "file";

  const roots = $("#picker-roots");
  roots.replaceChildren();
  if (data.home) {
    const homeBtn = document.createElement("button");
    homeBtn.type = "button";
    homeBtn.className = "picker-root-btn";
    homeBtn.textContent = "🏠 Home";
    homeBtn.onclick = handle(() => navigatePicker(data.home));
    roots.append(homeBtn);
  }
  for (const drive of (data.drives || [])) {
    const driveBtn = document.createElement("button");
    driveBtn.type = "button";
    driveBtn.className = "picker-root-btn";
    driveBtn.textContent = drive;
    driveBtn.onclick = handle(() => navigatePicker(drive));
    roots.append(driveBtn);
  }

  const breadcrumbs = $("#picker-breadcrumbs");
  breadcrumbs.replaceChildren();
  const parts = data.current.split(/[\\/]+/).filter(Boolean);
  const isWin = /^[a-zA-Z]:/.test(data.current);
  let accumulated = "";

  if (data.parent) {
    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.className = "picker-crumb";
    upBtn.textContent = "⬆ Up";
    upBtn.onclick = handle(() => navigatePicker(data.parent));
    breadcrumbs.append(upBtn, document.createTextNode(" · "));
  }

  parts.forEach((part, index) => {
    if (index === 0 && isWin) {
      accumulated = part + "\\";
    } else if (index === 0 && !isWin) {
      accumulated = "/" + part;
    } else {
      accumulated += (accumulated.endsWith("\\") || accumulated.endsWith("/") ? "" : (isWin ? "\\" : "/")) + part;
    }
    const currentPath = accumulated;
    const crumb = document.createElement("button");
    crumb.type = "button";
    crumb.className = "picker-crumb";
    crumb.textContent = part;
    if (index < parts.length - 1) {
      crumb.onclick = handle(() => navigatePicker(currentPath));
      breadcrumbs.append(crumb, document.createTextNode(" > "));
    } else {
      breadcrumbs.append(crumb);
    }
  });

  currentPickerState.allEntries = [
    ...(data.folders || []).map(f => ({ ...f, isDir: true })),
    ...(data.files || []).map(f => ({ ...f, isDir: false }))
  ];
  renderPickerEntries();
}

function renderPickerEntries() {
  const container = $("#picker-entries");
  container.replaceChildren();
  const filter = ($("#picker-filter").value || "").toLowerCase().trim();

  const filtered = currentPickerState.allEntries.filter(entry =>
    !filter || entry.name.toLowerCase().includes(filter)
  );

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "picker-entry";
    empty.style.color = "var(--muted)";
    empty.textContent = "(No matching folders or files)";
    container.append(empty);
    return;
  }

  for (const entry of filtered) {
    const row = document.createElement("div");
    row.className = "picker-entry";
    row.tabIndex = 0;
    row.setAttribute("role", "button");
    if ($("#picker-selected-path").value === entry.path) {
      row.classList.add("selected");
    }

    const icon = document.createElement("span");
    icon.className = "picker-entry-icon";
    icon.textContent = entry.isDir ? "📁" : "📄";

    const name = document.createElement("span");
    name.className = "picker-entry-name";
    name.textContent = entry.name;

    row.append(icon, name);

    row.onclick = () => {
      $("#picker-selected-path").value = entry.path;
      $("#picker-confirm").disabled = currentPickerState.mode === "file" && entry.isDir;
      container.querySelectorAll(".picker-entry").forEach(el => el.classList.remove("selected"));
      row.classList.add("selected");
    };

    row.ondblclick = () => {
      if (entry.isDir) {
        navigatePicker(entry.path).catch(error => notice(error.message));
      } else {
        if (currentPickerState.onSelect) {
          currentPickerState.onSelect(entry.path);
        }
        $("#folder-picker-dialog").close();
      }
    };

    row.onkeydown = event => {
      if (event.key === "Enter") { event.preventDefault(); row.ondblclick(); }
      if (event.key === " ") { event.preventDefault(); row.click(); }
    };
    container.append(row);
  }
}

function openPicker(options) {
  currentPickerState = {
    mode: options.mode || "folder",
    ext: options.ext || "",
    current: "",
    onSelect: options.onSelect,
    allEntries: []
  };

  $("#picker-title").textContent = options.title || (options.mode === "file" ? "Select file" : "Select folder");
  $("#picker-confirm").textContent = options.mode === "file" ? "Select this file" : "Select this folder";
  $("#picker-filter").value = "";

  const dialog = $("#folder-picker-dialog");
  dialog.showModal();
  navigatePicker(options.initialPath || "").catch(error => notice(error.message));
}

async function loadSettings() {
  const data = await (await api("/api/settings")).json();
  const currentH3 = data.settings.h3_models || {};
  const installedH3 = data.h3_models_installed || {};
  const entries = Object.entries(data.settings).filter(([k]) => k !== "h3_models");

  const fields = entries.map(([name, value]) => {
    const tip = settingTooltips[name] || settingLabels[name] || name;
    const label = text("label", settingLabels[name] || name, "", tip);
    let input;
    if (name === "writer_mode") {
      input = document.createElement("select");
      input.append(option("local", "Local", "Local writer engine"), option("api", "API", "Hosted cloud API provider"));
    } else if (name === "backend") {
      input = document.createElement("select");
      input.append(...Object.entries(catalog.backends).map(([key, card]) => option(key, card.name, `${card.name}: ${card.description || key}`)));
    } else if (name === "laya_device") {
      input = document.createElement("select");
      input.append(
        option("cuda_or_cpu", "CUDA with CPU fallback", "Use CUDA when available, otherwise CPU"),
        option("mps_or_cpu", "MPS with CPU fallback", "Use MPS when available, otherwise CPU"),
        option("auto", "Auto (CUDA, MPS, then CPU)", "Choose an available Laya device automatically"),
        option("cpu", "CPU", "Run Laya validator on CPU"),
        option("cuda", "CUDA", "Run Laya validator on NVIDIA GPU (CUDA)"),
        option("mps", "MPS", "Run Laya validator on Apple Silicon (MPS)")
      );
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

    if (folderSettings.has(name) || name in fileSettings) {
      const group = document.createElement("div");
      group.className = "path-input-group";
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "browse-btn";
      btn.textContent = "📁 Browse";
      btn.dataset.tooltip = `Browse filesystem for ${settingLabels[name] || name}`;
      btn.title = btn.dataset.tooltip;
      const isFile = name in fileSettings;
      btn.onclick = (e) => {
        e.preventDefault();
        openPicker({
          title: isFile ? `Select file: ${settingLabels[name] || name}` : `Select folder: ${settingLabels[name] || name}`,
          mode: isFile ? "file" : "folder",
          ext: fileSettings[name] || "",
          initialPath: input.value,
          onSelect: (selectedPath) => {
            input.value = selectedPath;
            input.dispatchEvent(new Event("change", { bubbles: true }));
          }
        });
      };
      group.append(input, btn);
      label.append(group);
    } else {
      label.append(input);
      if (name === "writer_launch") {
        const hint = document.createElement("div");
        hint.style.marginTop = "4px";
        const helpBtn = document.createElement("button");
        helpBtn.type = "button";
        helpBtn.className = "quiet llama-help-btn";
        helpBtn.style.display = "inline";
        helpBtn.style.padding = "0";
        helpBtn.textContent = "ℹ️ Need help with token buffers or launch arguments? Open llama.cpp guide ↗";
        helpBtn.onclick = event => {
          event.preventDefault();
          $("#panel-settings > .panel-header-row .llama-help-btn").click();
        };
        hint.append(helpBtn);
        label.append(hint);
      }
    }
    return label;
  });

  const h3Keys = [
    ["video_vae", "h3_video_vae"],
    ["audio_vae", "h3_audio_vae"],
    ["diffusion_model", "h3_diffusion_model"],
    ["text_encoder", "h3_text_encoder"]
  ];

  for (const [key, fieldName] of h3Keys) {
    const tip = settingTooltips[fieldName];
    const label = text("label", settingLabels[fieldName] || fieldName, "", tip);
    const installed = installedH3[key] || [];
    const currentVal = currentH3[key] || "";
    const select = document.createElement("select");
    select.name = "h3_" + key;
    select.dataset.initialValue = currentVal;
    select.dataset.tooltip = tip;
    select.title = tip;

    const optionsList = Array.from(new Set([currentVal, ...installed].filter(Boolean)));
    if (!currentVal) {
      select.append(option("", "No supported loader in selected workflow"));
      select.disabled = true;
    } else {
      for (const m of optionsList) {
        const label = m === currentVal && !installed.includes(m) ? m + " (current; not detected)" : m;
        select.append(option(m, label, `${settingLabels[fieldName]}: ${m}`));
      }
      select.value = currentVal;
    }
    label.append(select);
    fields.push(label);
  }

  $("#settings-fields").replaceChildren(...fields);
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

async function applyStatus(status) {
  if (!status || !status.state) return;
  currentRun = status.id;
  const busy = ["running", "cancelling"].includes(status.state);
  $("#status-title").textContent = status.state === "idle" ? "READY WHEN YOU ARE" : status.state.toUpperCase();
  $("#status-message").textContent = status.message || "One idea. One production at a time.";
  $("#progress").value = status.progress || 0;
  $("#cancel").hidden = !busy;
  $("#resume-production").hidden = !status.can_resume;
  $("#show-log").hidden = false;
  $$(".operation-action").forEach(button => button.disabled = busy);
  if (lastState && lastState !== status.state && !busy) {
    await Promise.all([loadActors(), loadStyles(), loadOutputs()]);
  }
  lastState = status.state;
}

let sseSource = null;
let sseConnected = false;
let statusTimer = null;
let lastStreamEvent = 0;

function setupEventStream() {
  if (typeof EventSource !== "undefined") {
    try {
      sseSource = new EventSource("/api/events");
      sseSource.addEventListener("status", event => {
        try {
          const status = JSON.parse(event.data);
          lastStreamEvent = Date.now();
          sseConnected = true;
          applyStatus(status).catch(error => notice(error.message));
        } catch {}
      });
      sseSource.onerror = () => { sseConnected = false; };
    } catch { sseConnected = false; }
  }
  // Keep one watchdog alive even while SSE is healthy, so disconnects and
  // proxies buffering events cannot permanently stop operation updates.
  fallbackPoll();
}

async function fallbackPoll() {
  clearTimeout(statusTimer);
  const busy = ["running", "cancelling"].includes(lastState);
  const interval = busy ? 2000 : 10000;
  try {
    if (!sseConnected || Date.now() - lastStreamEvent > 20000) {
      const status = await (await api("/api/status")).json();
      await applyStatus(status);
    }
    if (!$("#operation-log").hidden) await updateLogDisplay();
  } catch {
    $("#status-message").textContent = "Connection unavailable. The server may have stopped.";
  } finally {
    statusTimer = setTimeout(fallbackPoll, interval);
  }
}
window.addEventListener("pagehide", () => {
  if (sseSource) sseSource.close();
  clearTimeout(statusTimer);
});
window.addEventListener("pageshow", event => {
  if (event.persisted) setupEventStream();
});

async function initialize() {
  initTooltips();
  setupOapGuide();
  setupLlamaGuide();
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
      const state = formFiles.get(form);
      if (state.songObjectUrl) {
        updateSongPreview(form, "");
        URL.revokeObjectURL(state.songObjectUrl);
        state.songObjectUrl = undefined;
      }
      state.songObjectUrl = URL.createObjectURL(selected);
      updateSongPreview(form, state.songObjectUrl);
      state.song = undefined; state.songName = undefined; state.pending++;
      song.disabled = true; form.querySelector(".song-receipt").textContent = "Uploading " + selected.name + "…";
      try {
        state.song = await upload(selected, "song");
        state.songName = selected.name;
        form.querySelector(".song-receipt").textContent = "Uploaded: " + selected.name;
        song.required = false;
        scheduleSave();
      }
      catch (error) {
        if (state.songObjectUrl) {
          URL.revokeObjectURL(state.songObjectUrl);
          state.songObjectUrl = undefined;
        }
        updateSongPreview(form, "");
        form.querySelector(".song-receipt").textContent = "Upload failed; select the song again.";
        throw error;
      }
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
  function renderOapReportCard(report, allowUnsigned) {
    const card = $("#oap-report-card");
    if (!card) return;
    const manifest = report.manifest || {}, verification = report.verification || {};
    const identity = manifest.identity || {}, rider = manifest.rider || {};
    const signed = Boolean(verification.signature_valid);
    const valid = Boolean(verification.ok);
    const header = text("div", "", "oap-report-header");
    header.append(text("div", "Package: " + (identity.display_name || identity.actor_id || "Actor"), "oap-report-title"));
    const badge = signed && valid
      ? (verification.agent_known ? "Signature valid · known signer" : "Signature valid · signer not locally trusted")
      : (valid && allowUnsigned ? "Unsigned package · explicitly allowed" : "Verification warning");
    header.append(text("span", badge, "oap-badge-pill " + (signed && valid ? "badge-valid" : "badge-unsigned")));
    const grid = text("div", "", "oap-report-grid");
    const ratings = rider.content && typeof rider.content === "object"
      ? Object.entries(rider.content).map(([key, value]) => `${key}: ${value}`).join(", ")
      : "Not specified in package";
    for (const [label, value] of [
      ["Actor ID", identity.actor_id || "Not specified"],
      ["Display name", identity.display_name || "Not specified"],
      ["Signing public key", signed ? (manifest.agent?.public_key || "Not supplied") : "Unsigned"],
      ["Visual identity", manifest.visual?.core_identity || "Not specified"],
      ["Ratings ceiling", ratings],
      ["Commercial rider", rider.commercial ? JSON.stringify(rider.commercial, null, 2) : "Not specified in package"]
    ]) {
      grid.append(text("div", label + ":", "oap-report-label"), text("div", String(value), "oap-report-value"));
    }
    card.replaceChildren(header, grid);
    card.hidden = false;
    if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = false;
  }

  function setupOapGuide() {
    const dialog = $("#oap-helper-dialog");
    if (!dialog) return;

    $$(".oap-help-btn").forEach(btn => {
      btn.onclick = () => {
        dialog.showModal();
      };
    });

    $$(".close-oap-dialog").forEach(btn => {
      btn.onclick = () => {
        dialog.close();
      };
    });

    $$(".nav-to-actors-btn").forEach(btn => {
      btn.onclick = () => {
        const actorNav = document.querySelector('.nav[data-panel="actors"]');
        if (actorNav) actorNav.click();
        if (dialog.open) dialog.close();
      };
    });

    $$(".oap-tab-btn").forEach(tabBtn => {
      tabBtn.onclick = () => {
        const tabId = tabBtn.dataset.tab;
        $$(".oap-tab-btn").forEach(b => b.classList.toggle("active", b === tabBtn));
        $$(".oap-tab-content").forEach(content => {
          const matches = content.id === `tab-${tabId}`;
          content.classList.toggle("active", matches);
          content.hidden = !matches;
        });
      };
    });

    const toggleRaw = $("#toggle-raw-oap");
    if (toggleRaw) {
      toggleRaw.onclick = () => {
        const pre = $("#oap-report");
        pre.hidden = !pre.hidden;
        toggleRaw.textContent = pre.hidden ? "Show raw manifest JSON" : "Hide raw manifest JSON";
      };
    }
  }

  function setupLlamaGuide() {
    const dialog = $("#llama-helper-dialog");
    if (!dialog) return;
    const picker = $("#writer-tuning-preset");
    function commandPreview() {
      const current = $("input[name=writer_launch]")?.value || "";
      if (picker.value === "current") return current;
      const args = JSON.parse(current);
      if (!Array.isArray(args) || !args.length || args.some(arg => typeof arg !== "string")) {
        throw new Error("Configure a JSON array launch command first.");
      }
      const options = {"-c": "16384", "--ctx-size": "16384", "-b": "2048", "--batch-size": "2048", "-ub": "1024", "--ubatch-size": "1024"};
      if (args.some(arg => arg === "--mmproj" || arg.startsWith("--mmproj="))) options["--image-min-tokens"] = "1024";
      const result = [args[0]];
      for (let i = 1; i < args.length; i++) {
        const flag = args[i].split("=", 1)[0];
        if (Object.hasOwn(options, flag)) {
          if (!args[i].includes("=")) i++;
        } else result.push(args[i]);
      }
      result.push("-c", "16384", "-b", "2048", "-ub", "1024");
      if (options["--image-min-tokens"]) result.push("--image-min-tokens", "1024");
      return JSON.stringify(result);
    }
    function showPreview() {
      try { $("#llama-current-json").textContent = commandPreview() || "No launch command configured."; }
      catch { $("#llama-current-json").textContent = "Configure a valid JSON array launch command before choosing alternate tuning."; }
    }
    function openGuide() { picker.value = "current"; showPreview(); dialog.showModal(); }
    $$(".llama-help-btn").forEach(button => button.onclick = openGuide);
    picker.onchange = showPreview;
    $$(".close-llama-dialog").forEach(button => button.onclick = () => dialog.close());
    $("#copy-llama-json").onclick = handle(async () => {
      const command = commandPreview();
      if (!command) throw new Error("Configure a writer launch command first.");
      if (!await copyToClipboard(command)) throw new Error("Could not copy the launch command.");
      notice("Writer launch preview copied.");
    });
    $("#apply-writer-tuning").onclick = handle(async () => {
      const command = commandPreview();
      if (!command) throw new Error("Configure a writer launch command first.");
      $("input[name=writer_launch]").value = command;
      notice("Writer tuning applied to the field. Save settings to persist it.");
      dialog.close();
    });
  }

  $("#inspect-oap").onclick = handle(async () => {
    const file = $("#oap-file").files[0]; if (!file) throw new Error("Choose an OAP package first");
    $("#oap-import-form").hidden = true;
    $("#oap-import-form").elements.accept_unknown.checked = false;
    $("#oap-report-card").hidden = true;
    $("#oap-raw-toggle-wrap").hidden = true;
    $("#oap-report").hidden = true;
    $("#toggle-raw-oap").textContent = "Show raw manifest JSON";
    currentOap = await upload(file, "oap");
    const allowUnsigned = $("#allow-unsigned").checked;
    const report = await (await api(`/api/oap/inspect/${currentOap}?allow_unsigned=${allowUnsigned}`)).json();
    $("#oap-report").textContent = JSON.stringify(report, null, 2);
    renderOapReportCard(report, allowUnsigned);
    $("#oap-import-form").hidden = false;
  });
  $("#oap-import-form").onsubmit = handle(async event => {
    const body = new FormData(event.target);
    body.set("filename", currentOap);
    body.set("allow_unsigned", String($("#allow-unsigned").checked));
    body.set("accept_unknown", String(event.target.elements.accept_unknown.checked));
    await api("/api/oap/import", {method: "POST", body});
    event.target.hidden = true;
    $("#oap-report").hidden = true;
    if ($("#oap-report-card")) $("#oap-report-card").hidden = true;
    if ($("#oap-raw-toggle-wrap")) $("#oap-raw-toggle-wrap").hidden = true;
    notice("Actor successfully imported into your studio cast library.");
    await loadActors();
  });
  $("#settings-form").onsubmit = handle(async event => {
    const raw = Object.fromEntries(new FormData(event.target));
    const h3_models = {};
    for (const key of ["video_vae", "audio_vae", "diffusion_model", "text_encoder"]) {
      const field = event.target.elements["h3_" + key];
      const value = raw["h3_" + key];
      if (value && value !== field?.dataset.initialValue) h3_models[key] = value;
      delete raw["h3_" + key];
    }
    raw.vision_call_estimate = Number(raw.vision_call_estimate);
    raw.writer_call_estimate = Number(raw.writer_call_estimate);
    if (Object.keys(h3_models).length) raw.h3_models = h3_models;
    await json("/api/settings", raw, "PUT");
    await loadSettings();
    notice("Settings saved.");
  });
  $("#key-form").onsubmit = handle(async event => { await json("/api/key", Object.fromEntries(new FormData(event.target)), "PUT"); event.target.elements.value.value = ""; await loadSettings(); notice("Key saved locally. The settings API does not return it."); });
  $("#upscale-form").onsubmit = handle(async event => { const body = Object.fromEntries(new FormData(event.target)); body.scale = Number(body.scale); await json("/api/upscale", {...body, source: upscaleSource}); $("#upscale-dialog").close(); });

  const pickerFilter = $("#picker-filter");
  if (pickerFilter) pickerFilter.oninput = () => renderPickerEntries();
  const pickerCancel = $("#picker-cancel");
  if (pickerCancel) pickerCancel.onclick = () => $("#folder-picker-dialog").close();
  const pickerConfirm = $("#picker-confirm");
  if (pickerConfirm) {
    pickerConfirm.onclick = () => {
      const selected = $("#picker-selected-path").value;
      if (selected && currentPickerState.onSelect) {
        currentPickerState.onSelect(selected);
      }
      $("#folder-picker-dialog").close();
    };
  }

  await restoreProject();
  setupEventStream();
}
initialize().catch(error => notice(error.message));
