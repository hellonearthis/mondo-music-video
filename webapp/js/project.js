import { openWorldsPanel } from "./worlds.js";
import { $, $$, api, json, notice, option, state, updateLogDisplay } from "./core.js";
import { openVocabularyPanel, updateVocabCustomBadge } from "./vocabulary.js";

import { syncInstrumentControls } from "./instruments.js";
import { syncDanceControls } from "./dance.js";

let saveDebounceTimer = null;

export function panel(name) {
  $$(".panel").forEach(node => node.hidden = node.id !== "panel-" + name);
  $$(".nav[data-panel]").forEach(node => {
    const active = node.dataset.panel === name;
    node.classList.toggle("active", active);
    node.setAttribute("aria-current", active ? "page" : "false");
  });
  if (name === "vocab") {
    openVocabularyPanel().catch(error => notice(error.message));
  }
  if (name === "worlds") {
    openWorldsPanel().catch(error => notice(error.message));
  }
  scheduleSave();
}

export function updateSongPreview(form, src) {
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

export function resolutionSelect(form) {
  if (!state.catalog) return;
  const backend = form.querySelector(".backend-select").value;
  const select = form.querySelector(".resolution-select");
  const old = select.value;
  const resolutions = state.catalog.backends[backend]?.resolutions || [];
  select.replaceChildren(...resolutions.map(value =>
    option(value, value, `Render resolution ${value} for ${state.catalog.backends[backend]?.name || backend}`)
  ));
  if ([...select.options].some(item => item.value === old)) select.value = old;
}

export function getProjectState() {
  const activeNav = $(".nav.active[data-panel]");
  const panelName = activeNav ? activeNav.dataset.panel : "video";
  const forms = {};
  const files = {};

  ["video-form", "harvest-form", "ident-form", "actor-form", "style-form", "world-form"].forEach(id => {
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

    const fileState = state.formFiles.get(form);
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
    custom_vocabulary: state.currentCustomVocab,
    vocab_random_key: state.currentVocabRandomKey || "",
    thematic_worlds: state.thematicWorlds || null,
    details_open: Boolean($("#video-form details[open]")),
    details_sections: Object.fromEntries($$("#video-form details[id]").map(el => [el.id, el.open])),
    log_open: Boolean($("#operation-log") && !$("#operation-log").hidden)
  };
}

export async function saveProject() {
  const projectState = getProjectState();
  try { localStorage.setItem("mmv_project_draft", JSON.stringify(projectState)); } catch {}
  try { await json("/api/project", projectState, "PUT"); } catch {}
}

export function scheduleSave() {
  clearTimeout(saveDebounceTimer);
  saveDebounceTimer = setTimeout(saveProject, 250);
}

export async function restoreProject() {
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

  // Restore vocabulary state and profile before opening its workspace.
  if (saved.details_sections && Object.keys(saved.details_sections).length) {
    $$("#video-form details[id]").forEach(el => {
      el.open = Boolean(saved.details_sections[el.id]);
    });
  } else if (saved.details_open !== undefined) {
    $$("#video-form details").forEach(el => el.open = Boolean(saved.details_open));
  }
  if (saved.log_open && $("#operation-log")) {
    $("#operation-log").hidden = false;
    $("#show-log").textContent = "Hide log";
    updateLogDisplay();
  }
  if (saved.vocab_random_key) {
    state.currentVocabRandomKey = String(saved.vocab_random_key);
  }
  if (saved.thematic_worlds && typeof saved.thematic_worlds === "object") {
    state.thematicWorlds = saved.thematic_worlds;
  }
  if (saved.custom_vocabulary && typeof saved.custom_vocabulary === "object") {
    state.currentCustomVocab = saved.custom_vocabulary;
    updateVocabCustomBadge();
  }

  const formsData = saved.forms || {};
  // Projects saved before lip sync stored the mouth setting as a true/false silent_mouths value.
  const legacy = formsData["video-form"];
  if (legacy && legacy.silent_mouths !== undefined && legacy.mouth_mode === undefined) {
    legacy.mouth_mode = String(legacy.silent_mouths) === "false" ? "natural" : "sealed";
  }
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
    syncDanceControls(form);
    syncInstrumentControls(form);
  });
  $("#world-form")?.elements.world_mode.dispatchEvent(new Event("change"));

  const filesData = saved.files || {};
  Object.entries(filesData).forEach(([formId, fileState]) => {
    const form = $("#" + formId);
    if (!form) return;
    const fState = state.formFiles.get(form) || { references: [], pending: 0 };
    if (fileState.song) {
      fState.song = fileState.song;
      fState.songName = fileState.songName || fileState.song;
      const receipt = form.querySelector(".song-receipt");
      if (receipt) receipt.textContent = "Uploaded: " + fState.songName;
      const songInput = form.querySelector(".song-input");
      if (songInput) songInput.required = false;
      updateSongPreview(form, "/api/uploads/song/" + encodeURIComponent(fState.song));
    }
    if (Array.isArray(fileState.references) && fileState.references.length) {
      fState.references = fileState.references;
      fState.referenceNames = fileState.referenceNames || fileState.references;
      const receipt = form.querySelector(".refs-receipt");
      if (receipt) receipt.textContent = fState.referenceNames.join(" · ");
      const refsInput = form.querySelector(".refs-input");
      if (refsInput && form.dataset.kind === "harvest") refsInput.required = false;
    }
    state.formFiles.set(form, fState);
  });
  if (saved.panel) panel(saved.panel);
}

export function initNavigation() {
  $$(".nav[data-panel]").forEach(button => {
    button.onclick = () => panel(button.dataset.panel);
  });

  const teasers = {
    "Short films": "From screenplay to screen, with the full studio's film production tools.",
    "Micro Drama": "A home for episodic stories and serial drama in the full studio.",
    "Hodge TV": "Channel-surf broadcasts and programme variety in the full studio.",
    "The cutting room": "Editing and production refinement in the full studio.",
    "The Vault": "A library of archival footage in the full studio."
  };

  $$(".teaser").forEach(button => {
    button.onclick = () => {
      $("#teaser-title").textContent = button.dataset.feature;
      $("#teaser-description").textContent = teasers[button.dataset.feature];
      panel("teaser");
    };
  });

  const backBtn = $("#back-to-video");
  if (backBtn) backBtn.onclick = () => panel("video");

  $$(".production-form, #actor-form, #style-form, #world-form").forEach(form => {
    form.addEventListener("input", scheduleSave);
    form.addEventListener("change", scheduleSave);
  });

  $$("#video-form details").forEach(details => {
    details.addEventListener("toggle", scheduleSave);
  });
}

