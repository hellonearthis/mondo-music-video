// Studio Settings, API Profiles, Credentials, and Filesystem Browser Picker.

import { $, api, handle, json, notice, option, state, text } from "./core.js";
import { refreshServices } from "./production.js";

export const settingLabels = {
  writer_api_profile: "Writer API profile",
  vision_api_profile: "Vision API profile",
  video_api_profile: "Video API profile",
  auto_updates: "Automatic updates",
  comfy_sdk_url: "Local Comfy API proxy URL",
  backend: "Default renderer",
  comfy_url: "ComfyUI service URL",
  comfy_input: "ComfyUI input folder (shared local path)",
  comfy_output: "ComfyUI output folder (shared local path)",
  writer_launch: "Local writer launch command (JSON arguments)",
  writer_cwd: "Writer working folder",
  comfy_launch: "ComfyUI launch command (JSON arguments)",
  comfy_cwd: "ComfyUI working folder",
  laya_model_dir: "Laya model folder",
  laya_device: "Laya device (cpu, cuda, mps)",
  writer_url: "Writer service URL (OpenAI-compatible /v1)",
  writer_model: "Music-video writer model",
  writer_mode: "Writer service: local or API",
  writer_call_estimate: "API writer estimate per call, USD",
  workflow_map_path: "Workflow binding map JSON path",
  vision_url: "Vision service URL (OpenAI-compatible /v1)",
  vision_model: "Vision model name",
  vision_key_env: "Vision credential name",
  vision_call_estimate: "Vision estimate per call, USD (0 for local)",
  topaz_executable: "Installed Topaz FFmpeg executable path",
  topaz_models: "Installed Topaz models folder",
  h3_video_vae: "H3 video VAE model",
  h3_audio_vae: "H3 audio VAE model",
  h3_diffusion_model: "H3 reference-to-video diffusion model",
  h3_text_encoder: "H3 text encoder (CLIP) model"
};

export const settingTooltips = {
  auto_updates: "At the next launch, install tracked repository updates automatically. Turn off to check and notify only.",
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

export async function navigatePicker(targetPath) {
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

export function renderPickerEntries() {
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

export function openPicker(options) {
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

export async function loadSettings() {
  const data = await (await api("/api/settings")).json();
  const currentH3 = data.settings.h3_models || {};
  const installedH3 = data.h3_models_installed || {};
  const entries = Object.entries(data.settings).filter(([k]) => k !== "h3_models");

  const fields = entries.map(([name, value]) => {
    const tip = settingTooltips[name] || settingLabels[name] || name;
    const label = text("label", settingLabels[name] || name, "", tip);
    let input;
    if (name.endsWith("_api_profile")) {
      const role = name.replace("_api_profile", "");
      input = document.createElement("select");
      input.append(option("", "Manual configuration", "Use the individual settings below"));
      input.append(...(data.api_profiles || []).filter(p => p.role === role).map(p => option(p.name, p.name)));
    } else if (name === "auto_updates") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = Boolean(value);
    } else if (name === "writer_mode") {
      input = document.createElement("select");
      input.append(option("local", "Local", "Local writer engine"), option("api", "API", "Hosted cloud API provider"));
    } else if (name === "backend") {
      input = document.createElement("select");
      input.append(...Object.entries(state.catalog.backends).map(([key, card]) => option(key, card.name, `${card.name}: ${card.description || key}`)));
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
        const optLabel = m === currentVal && !installed.includes(m) ? m + " (current; not detected)" : m;
        select.append(option(m, optLabel, `${settingLabels[fieldName]}: ${m}`));
      }
      select.value = currentVal;
    }
    label.append(select);
    fields.push(label);
  }

  for (const role of ["writer", "vision", "video"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    button.textContent = `Save configured ${role} API as a profile`;
    button.onclick = handle(async () => {
      const name = window.prompt(`Profile ID for the saved ${role} settings (lowercase letters, numbers, underscores or hyphens). Save your settings and key first.`);
      if (!name) return;
      await json("/api/api-profiles", { name, role }, "POST");
      await loadSettings();
      notice("API profile saved privately. Select it and save Settings to activate it.");
    });
    fields.push(button);
  }
  $("#settings-fields").replaceChildren(...fields);
  $("#key-status").textContent = Object.entries(data.keys).map(([name, set]) => `${name}: ${set ? "configured" : "not set"}`).join(" · ");
  return data.settings;
}

export function initSettingsAndPicker() {
  $("#settings-form").onsubmit = handle(async event => {
    const raw = Object.fromEntries(new FormData(event.target));
    const h3_models = {};
    for (const key of ["video_vae", "audio_vae", "diffusion_model", "text_encoder"]) {
      const field = event.target.elements["h3_" + key];
      const value = raw["h3_" + key];
      if (value && value !== field?.dataset.initialValue) h3_models[key] = value;
      delete raw["h3_" + key];
    }
    raw.auto_updates = event.target.elements.auto_updates.checked;
    raw.vision_call_estimate = Number(raw.vision_call_estimate);
    raw.writer_call_estimate = Number(raw.writer_call_estimate);
    if (Object.keys(h3_models).length) raw.h3_models = h3_models;
    await json("/api/settings", raw, "PUT");
    await loadSettings();
    await refreshServices(true);
    notice("Settings saved.");
  });

  $("#key-form").onsubmit = handle(async event => {
    await json("/api/key", Object.fromEntries(new FormData(event.target)), "PUT");
    event.target.elements.value.value = "";
    await loadSettings();
    await refreshServices(true);
    notice("Key saved locally. The settings API does not return it.");
  });

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
}

