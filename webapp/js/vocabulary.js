// Visual Vocabulary Customizer, Category Override Editor, and Preset Manager.

import { $, $$, api, handle, json, notice, option, state } from "./core.js";
import { scheduleSave } from "./project.js";

let vocabDataCache = null;
let vocabActiveCategory = "settings";
let vocabWorkingDraft = {};

export function updateVocabCustomBadge() {
  const badge = $("#vocab-custom-badge");
  if (!badge) return;
  const count = Object.keys(state.currentCustomVocab || {}).length;
  if (count > 0) {
    badge.textContent = `${count} customized`;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

export async function loadVocabularyCatalog(force = false) {
  if (!vocabDataCache || force) {
    vocabDataCache = await (await api("/api/vocabulary")).json();
    populateVocabProfileSelects();
  }
  return vocabDataCache;
}

export function populateVocabProfileSelects() {
  if (!vocabDataCache) return;
  const mainSelect = $("#vocab-profile-select");
  const dialogSelect = $("#vocab-dialog-preset-select");
  const oldMain = mainSelect ? mainSelect.value : "full";
  const oldDialog = dialogSelect ? dialogSelect.value : "full";

  const options = [
    option("full", "Full vocabulary (current default)"),
    option("reduced_flashing", "Reduced flash/strobe cues (hellonearthis)")
  ];

  if (Array.isArray(vocabDataCache.vocabularies)) {
    vocabDataCache.vocabularies.forEach(preset => {
      options.push(option(preset.id, `${preset.name} (${preset.id})`));
    });
  }

  if (mainSelect) {
    mainSelect.replaceChildren(...options.map(o => o.cloneNode(true)));
    if ([...mainSelect.options].some(o => o.value === oldMain)) mainSelect.value = oldMain;
  }
  if (dialogSelect) {
    dialogSelect.replaceChildren(...options.map(o => o.cloneNode(true)));
    if ([...dialogSelect.options].some(o => o.value === oldDialog)) dialogSelect.value = oldDialog;
  }
}

export function setupVocabularyCustomizer() {
  const dialog = $("#vocabulary-dialog");
  const openBtn = $("#open-vocab-dialog");
  if (!dialog || !openBtn) return;

  loadVocabularyCatalog().catch(() => {});

  openBtn.onclick = handle(async () => {
    await loadVocabularyCatalog();
    vocabWorkingDraft = JSON.parse(JSON.stringify(state.currentCustomVocab || {}));
    const currentProfile = $("#vocab-profile-select")?.value || "full";
    if ($("#vocab-dialog-preset-select")) $("#vocab-dialog-preset-select").value = currentProfile;
    updateDeletePresetBtnVisibility();
    renderVocabTabs();
    selectVocabCategory(vocabActiveCategory);
    dialog.showModal();
  });

  const dialogSelect = $("#vocab-dialog-preset-select");
  if (dialogSelect) {
    dialogSelect.onchange = updateDeletePresetBtnVisibility;
  }

  const loadPresetBtn = $("#vocab-load-preset-btn");
  if (loadPresetBtn) {
    loadPresetBtn.onclick = handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      if (selectedId === "full") {
        vocabWorkingDraft = {};
      } else if (selectedId === "reduced_flashing") {
        const profile = vocabDataCache.profiles?.reduced_flashing?.exclude || {};
        vocabWorkingDraft = {};
        for (const [cat, excluded] of Object.entries(profile)) {
          vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [...excluded] };
        }
      } else {
        const preset = vocabDataCache.vocabularies.find(p => p.id === selectedId);
        if (preset) {
          vocabWorkingDraft = JSON.parse(JSON.stringify(preset.tables || {}));
        }
      }
      renderVocabTabs();
      selectVocabCategory(vocabActiveCategory);
      notice(`Loaded preset "${selectedId}" into editor.`);
    });
  }

  const deletePresetBtn = $("#vocab-delete-preset-btn");
  if (deletePresetBtn) {
    deletePresetBtn.onclick = handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      if (!window.confirm(`Delete vocabulary preset "${selectedId}" from this machine?`)) return;
      await api(`/api/vocabularies/${encodeURIComponent(selectedId)}`, { method: "DELETE" });
      await loadVocabularyCatalog(true);
      notice("Vocabulary preset deleted.");
      selectVocabCategory(vocabActiveCategory);
    });
  }

  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) {
    modeSelect.onchange = () => {
      saveActiveCategoryCustomText();
      const cat = vocabActiveCategory;
      if (!vocabWorkingDraft[cat]) {
        vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [] };
      }
      vocabWorkingDraft[cat].mode = modeSelect.value;
      renderVocabCategoryContent(cat);
      updateTabBadges();
    };
  }

  const searchInput = $("#vocab-search-input");
  if (searchInput) {
    searchInput.oninput = () => filterCheckboxGrid(searchInput.value);
  }

  const selectAllBtn = $("#vocab-select-all-btn");
  if (selectAllBtn) {
    selectAllBtn.onclick = () => {
      const cat = vocabActiveCategory;
      if (vocabWorkingDraft[cat]) vocabWorkingDraft[cat].exclude = [];
      $("#vocab-checkbox-grid").querySelectorAll("input[type=checkbox]").forEach(cb => cb.checked = true);
      updateActiveCategoryCount();
      updateTabBadges();
    };
  }

  const clearAllBtn = $("#vocab-clear-all-btn");
  if (clearAllBtn) {
    clearAllBtn.onclick = () => {
      const cat = vocabActiveCategory;
      const baseItems = vocabDataCache?.base?.[cat] || [];
      if (!vocabWorkingDraft[cat]) {
        vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [] };
      }
      vocabWorkingDraft[cat].exclude = [...baseItems];
      $("#vocab-checkbox-grid").querySelectorAll("input[type=checkbox]").forEach(cb => cb.checked = false);
      updateActiveCategoryCount();
      updateTabBadges();
    };
  }

  const resetCatBtn = $("#vocab-reset-cat-btn");
  if (resetCatBtn) {
    resetCatBtn.onclick = () => {
      const cat = vocabActiveCategory;
      delete vocabWorkingDraft[cat];
      renderVocabCategoryContent(cat);
      updateTabBadges();
      notice(`Category "${cat}" reset to default.`);
    };
  }

  const applyBtn = $("#vocab-apply-btn");
  if (applyBtn) {
    applyBtn.onclick = handle(() => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      state.currentCustomVocab = JSON.parse(JSON.stringify(vocabWorkingDraft));
      updateVocabCustomBadge();
      scheduleSave();
      dialog.close();
      notice("Vocabulary customizations applied to current video.");
    });
  }

  const resetAllBtn = $("#vocab-reset-all-btn");
  if (resetAllBtn) {
    resetAllBtn.onclick = () => {
      if (!window.confirm("Reset all vocabulary customizations back to standard?")) return;
      vocabWorkingDraft = {};
      renderVocabTabs();
      selectVocabCategory(vocabActiveCategory);
      notice("All category customizations cleared.");
    };
  }

  const savePresetBtn = $("#vocab-save-preset-btn");
  if (savePresetBtn) {
    savePresetBtn.onclick = handle(async () => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      const presetId = ($("#vocab-preset-id").value || "").trim().toLowerCase();
      const presetName = ($("#vocab-preset-name").value || "").trim();
      if (!presetId) throw new Error("Enter a preset ID (lowercase letters, numbers, hyphens)");
      if (!presetName) throw new Error("Enter a display name for this preset");

      await json("/api/vocabularies", {
        id: presetId,
        name: presetName,
        base_profile: "full",
        tables: vocabWorkingDraft
      });

      await loadVocabularyCatalog(true);
      if ($("#vocab-profile-select")) $("#vocab-profile-select").value = presetId;
      notice(`Preset "${presetName}" saved!`);
      scheduleSave();
    });
  }
}

export function updateDeletePresetBtnVisibility() {
  const deleteBtn = $("#vocab-delete-preset-btn");
  const selected = $("#vocab-dialog-preset-select")?.value;
  if (!deleteBtn) return;
  if (selected && selected !== "full" && selected !== "reduced_flashing") {
    deleteBtn.style.display = "inline";
  } else {
    deleteBtn.style.display = "none";
  }
}

export function renderVocabTabs() {
  const container = $("#vocab-category-tabs");
  if (!container || !vocabDataCache) return;
  const categories = vocabDataCache.categories || [];
  container.replaceChildren(...categories.map(cat => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "vocab-tab-btn" + (cat === vocabActiveCategory ? " active" : "");
    btn.dataset.category = cat;
    const label = cat.replace(/_/g, " ");
    const badge = document.createElement("span");
    badge.className = "vocab-tab-badge";
    btn.append(document.createTextNode(label), badge);
    btn.onclick = () => selectVocabCategory(cat);
    return btn;
  }));
  updateTabBadges();
}

export function selectVocabCategory(cat) {
  saveActiveCategoryCustomText();
  vocabActiveCategory = cat;
  $$(".vocab-tab-btn").forEach(b => b.classList.toggle("active", b.dataset.category === cat));
  renderVocabCategoryContent(cat);
}

export function renderVocabCategoryContent(cat) {
  if (!vocabDataCache) return;
  $("#vocab-active-category-title").textContent = cat.replace(/_/g, " ").toUpperCase();
  const override = vocabWorkingDraft[cat] || { mode: "append", add: [], exclude: [] };
  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) modeSelect.value = override.mode || "append";

  const builtinSection = $("#vocab-builtin-section");
  if (builtinSection) {
    builtinSection.hidden = override.mode === "replace";
  }

  const baseItems = vocabDataCache.base?.[cat] || [];
  const excludedSet = new Set(override.exclude || []);
  const grid = $("#vocab-checkbox-grid");
  grid.replaceChildren();

  baseItems.forEach(item => {
    const label = document.createElement("label");
    label.className = "vocab-item-label";
    label.title = item;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = item;
    cb.checked = !excludedSet.has(item);
    cb.onchange = () => {
      if (!vocabWorkingDraft[cat]) {
        vocabWorkingDraft[cat] = { mode: modeSelect.value, add: [], exclude: [] };
      }
      const exc = new Set(vocabWorkingDraft[cat].exclude || []);
      if (cb.checked) {
        exc.delete(item);
      } else {
        exc.add(item);
      }
      vocabWorkingDraft[cat].exclude = [...exc];
      updateActiveCategoryCount();
      updateTabBadges();
    };
    label.append(cb, document.createTextNode(item));
    grid.append(label);
  });

  const textarea = $("#vocab-custom-textarea");
  if (textarea) {
    textarea.value = (override.add || []).join("\n");
    textarea.oninput = () => {
      saveActiveCategoryCustomText();
      updateActiveCategoryCount();
      updateTabBadges();
    };
  }

  $("#vocab-search-input").value = "";
  filterCheckboxGrid("");
  updateActiveCategoryCount();
}

export function filterCheckboxGrid(term) {
  const grid = $("#vocab-checkbox-grid");
  if (!grid) return;
  const q = term.toLowerCase().trim();
  grid.querySelectorAll(".vocab-item-label").forEach(label => {
    const match = !q || label.textContent.toLowerCase().includes(q);
    label.style.display = match ? "flex" : "none";
  });
}

export function saveActiveCategoryCustomText() {
  const cat = vocabActiveCategory;
  const textarea = $("#vocab-custom-textarea");
  if (!textarea || !vocabDataCache) return;
  const lines = textarea.value.split("\n").map(s => s.trim()).filter(Boolean);
  if (lines.length > 0 || (vocabWorkingDraft[cat] && vocabWorkingDraft[cat].exclude?.length) || vocabWorkingDraft[cat]?.mode === "replace") {
    if (!vocabWorkingDraft[cat]) {
      vocabWorkingDraft[cat] = { mode: $("#vocab-category-mode")?.value || "append", add: [], exclude: [] };
    }
    vocabWorkingDraft[cat].add = lines;
  } else if (vocabWorkingDraft[cat]) {
    vocabWorkingDraft[cat].add = [];
  }
}

export function updateActiveCategoryCount() {
  const cat = vocabActiveCategory;
  if (!vocabDataCache) return;
  const baseItems = vocabDataCache.base?.[cat] || [];
  const override = vocabWorkingDraft[cat] || { mode: "append", add: [], exclude: [] };
  let count = 0;
  if (override.mode === "replace") {
    count = (override.add || []).length;
  } else {
    const excludedSet = new Set(override.exclude || []);
    const remaining = baseItems.filter(item => !excludedSet.has(item));
    const addedSet = new Set(override.add || []);
    count = remaining.length + addedSet.size;
  }
  const badge = $("#vocab-active-count-badge");
  if (badge) {
    badge.textContent = `${count} active`;
    badge.style.color = count === 0 ? "var(--muted)" : "var(--green)";
  }
}

export function updateTabBadges() {
  if (!vocabDataCache) return;
  $$(".vocab-tab-btn").forEach(btn => {
    const cat = btn.dataset.category;
    const baseItems = vocabDataCache.base?.[cat] || [];
    const override = vocabWorkingDraft[cat];
    let count = baseItems.length;
    let isModified = false;
    if (override) {
      if (override.mode === "replace") {
        count = (override.add || []).length;
        isModified = true;
      } else {
        const excludedSet = new Set(override.exclude || []);
        const added = override.add || [];
        count = baseItems.filter(x => !excludedSet.has(x)).length + added.length;
        if (excludedSet.size > 0 || added.length > 0) isModified = true;
      }
    }
    const badge = btn.querySelector(".vocab-tab-badge");
    if (badge) {
      badge.textContent = count;
      btn.style.fontWeight = isModified ? "700" : "600";
    }
  });
}

export function cleanWorkingDraft() {
  if (!vocabDataCache) return;
  for (const cat of Object.keys(vocabWorkingDraft)) {
    const override = vocabWorkingDraft[cat];
    const noAdd = !override.add || override.add.length === 0;
    const noExclude = !override.exclude || override.exclude.length === 0;
    if (override.mode === "append" && noAdd && noExclude) {
      delete vocabWorkingDraft[cat];
    }
  }
}

