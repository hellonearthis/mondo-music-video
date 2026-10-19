// Visual Vocabulary Customizer, Category Override Editor, and Preset Manager.

import { $, $$, api, handle, json, notice, option, state } from "./core.js";
import { scheduleSave } from "./project.js";

let vocabDataCache = null;
let vocabActiveCategory = "settings";
let vocabWorkingDraft = {};
let vocabCurrentRandomKey = "";

const SAVED_KEYS_STORAGE_KEY = "mmv_saved_vocab_keys";

// Deterministic 32-bit FNV-1a hash
function hashSeed(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// Deterministic Mulberry32 PRNG generator
function mulberry32(a) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function parseRandomKey(rawKey, fallbackCount = 5) {
  const cleaned = (rawKey || "").trim();
  if (!cleaned) return null;
  const parts = cleaned.split(":");
  const seedStr = parts[0].trim();
  if (!seedStr) return null;
  let count = parseInt(parts[1], 10);
  if (isNaN(count) || count < 1) count = Math.max(1, parseInt(fallbackCount, 10) || 5);
  return { seedStr, count, key: `${seedStr}:${count}` };
}

export function generateRandomKey(count = 5) {
  const seed = Math.floor(100000 + Math.random() * 900000).toString();
  const safeCount = Math.max(1, parseInt(count, 10) || 5);
  return `${seed}:${safeCount}`;
}

export function buildPseudoRandomDraft(rawKey, fallbackCount = 5, existingDraft = {}) {
  const parsed = parseRandomKey(rawKey, fallbackCount);
  if (!parsed || !vocabDataCache || !vocabDataCache.base) return null;
  const { seedStr, count } = parsed;
  const categories = vocabDataCache.categories || Object.keys(vocabDataCache.base);
  const newDraft = {};

  categories.forEach(cat => {
    const baseItems = vocabDataCache.base[cat] || [];
    if (baseItems.length === 0) return;
    const catSeed = hashSeed(`${seedStr}::${cat}`);
    const rand = mulberry32(catSeed);
    // Fisher-Yates deterministic shuffle of indices
    const indices = baseItems.map((_, i) => i);
    for (let i = indices.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [indices[i], indices[j]] = [indices[j], indices[i]];
    }
    const sampleSize = Math.min(Math.max(1, count), baseItems.length);
    const chosenIndices = new Set(indices.slice(0, sampleSize));
    const excluded = baseItems.filter((_, idx) => !chosenIndices.has(idx));
    
    // Preserve custom additions if previously added by user
    const existingAdd = existingDraft[cat]?.add || [];
    newDraft[cat] = {
      mode: "append",
      add: [...existingAdd],
      exclude: excluded
    };
  });

  return { draft: newDraft, key: parsed.key, seed: seedStr, count };
}

export function getSavedVocabKeys() {
  try {
    const raw = localStorage.getItem(SAVED_KEYS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveVocabKey(key) {
  if (!key) return;
  const list = getSavedVocabKeys().filter(k => k !== key);
  list.unshift(key);
  if (list.length > 50) list.length = 50;
  try {
    localStorage.setItem(SAVED_KEYS_STORAGE_KEY, JSON.stringify(list));
  } catch {}
}

export function deleteSavedVocabKey(key) {
  if (!key) return;
  const list = getSavedVocabKeys().filter(k => k !== key);
  try {
    localStorage.setItem(SAVED_KEYS_STORAGE_KEY, JSON.stringify(list));
  } catch {}
}

export function renderSavedKeysSelect() {
  const select = $("#vocab-saved-keys-select");
  const row = $("#vocab-saved-keys-row");
  if (!select) return;
  const keys = getSavedVocabKeys();
  if (keys.length === 0) {
    if (row) row.hidden = true;
    select.replaceChildren(option("", "No saved keys yet"));
    return;
  }
  if (row) row.hidden = false;
  select.replaceChildren(
    option("", `Saved keys (${keys.length})…`),
    ...keys.map(k => option(k, `🎲 ${k}`))
  );
}

export function updateVocabCustomBadge() {
  const badge = $("#vocab-custom-badge");
  const quickBar = $("#vocab-random-quick-bar");
  const quickKeyInput = $("#vocab-quick-key-input");
  const customCount = Object.keys(state.currentCustomVocab || {}).length;
  const randomKey = state.currentVocabRandomKey || "";

  if (badge) {
    if (randomKey) {
      badge.textContent = `🎲 ${randomKey}`;
      badge.hidden = false;
    } else if (customCount > 0) {
      badge.textContent = `${customCount} customized`;
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  }

  if (quickBar) {
    if (randomKey) {
      quickBar.hidden = false;
      if (quickKeyInput) quickKeyInput.value = randomKey;
    } else {
      quickBar.hidden = true;
    }
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
  const quickBarRollBtn = $("#roll-vocab-random-btn");
  if (!dialog || !openBtn) return;

  loadVocabularyCatalog().catch(() => {});

  openBtn.onclick = handle(async () => {
    await loadVocabularyCatalog();
    vocabWorkingDraft = JSON.parse(JSON.stringify(state.currentCustomVocab || {}));
    vocabCurrentRandomKey = state.currentVocabRandomKey || "";
    const currentProfile = $("#vocab-profile-select")?.value || "full";
    if ($("#vocab-dialog-preset-select")) $("#vocab-dialog-preset-select").value = currentProfile;
    updateDeletePresetBtnVisibility();
    renderSavedKeysSelect();

    if ($("#vocab-random-key")) $("#vocab-random-key").value = vocabCurrentRandomKey;
    renderVocabTabs();
    selectVocabCategory(vocabActiveCategory);
    renderVocabSelectionSummary();
    dialog.showModal();
  });

  // Quick bar "Roll Random" button in main panel
  if (quickBarRollBtn) {
    quickBarRollBtn.onclick = handle(async () => {
      await loadVocabularyCatalog();
      const currentCount = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const key = generateRandomKey(currentCount);
      const res = buildPseudoRandomDraft(key, currentCount, state.currentCustomVocab || {});
      if (res) {
        state.currentCustomVocab = res.draft;
        state.currentVocabRandomKey = res.key;
        vocabWorkingDraft = JSON.parse(JSON.stringify(res.draft));
        vocabCurrentRandomKey = res.key;
        updateVocabCustomBadge();
        scheduleSave();
        notice(`Rolled pseudo-random vocabulary key: ${res.key}`);
      }
    });
  }

  // Quick bar buttons
  const quickApplyBtn = $("#vocab-quick-apply-key-btn");
  if (quickApplyBtn) {
    quickApplyBtn.onclick = handle(async () => {
      await loadVocabularyCatalog();
      const raw = ($("#vocab-quick-key-input")?.value || "").trim();
      if (!raw) throw new Error("Enter a pseudo-random key (e.g. 482910:5)");
      const res = buildPseudoRandomDraft(raw, 5, state.currentCustomVocab || {});
      if (!res) throw new Error("Invalid key format. Use seed:count (e.g. 482910:5)");
      state.currentCustomVocab = res.draft;
      state.currentVocabRandomKey = res.key;
      vocabWorkingDraft = JSON.parse(JSON.stringify(res.draft));
      vocabCurrentRandomKey = res.key;
      updateVocabCustomBadge();
      scheduleSave();
      notice(`Applied pseudo-random key: ${res.key}`);
    });
  }

  const quickRerollBtn = $("#vocab-quick-reroll-btn");
  if (quickRerollBtn) {
    quickRerollBtn.onclick = handle(async () => {
      await loadVocabularyCatalog();
      const parsed = parseRandomKey(state.currentVocabRandomKey || "", 5);
      const count = parsed?.count || 5;
      const key = generateRandomKey(count);
      const res = buildPseudoRandomDraft(key, count, state.currentCustomVocab || {});
      if (res) {
        state.currentCustomVocab = res.draft;
        state.currentVocabRandomKey = res.key;
        vocabWorkingDraft = JSON.parse(JSON.stringify(res.draft));
        vocabCurrentRandomKey = res.key;
        updateVocabCustomBadge();
        scheduleSave();
        notice(`Rerolled pseudo-random key: ${res.key}`);
      }
    });
  }

  const quickSaveKeyBtn = $("#vocab-quick-save-key-btn");
  if (quickSaveKeyBtn) {
    quickSaveKeyBtn.onclick = handle(() => {
      const key = state.currentVocabRandomKey || ($("#vocab-quick-key-input")?.value || "").trim();
      if (!key) throw new Error("No pseudo-random key to save.");
      saveVocabKey(key);
      renderSavedKeysSelect();
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(key).catch(() => {});
      }
      notice(`Saved key "${key}" and copied to clipboard.`);
    });
  }

  const quickEditBtn = $("#vocab-quick-edit-btn");
  if (quickEditBtn) {
    quickEditBtn.onclick = () => {
      openBtn.click();
      const details = $("#vocab-random-summary-details");
      if (details) details.open = true;
    };
  }

  const quickClearBtn = $("#vocab-quick-clear-btn");
  if (quickClearBtn) {
    quickClearBtn.onclick = handle(() => {
      state.currentVocabRandomKey = "";
      state.currentCustomVocab = {};
      vocabWorkingDraft = {};
      vocabCurrentRandomKey = "";
      updateVocabCustomBadge();
      scheduleSave();
      notice("Cleared pseudo-random vocabulary. Restored full built-in vocabulary.");
    });
  }

  // Dialog toolbar buttons
  const rollDialogBtn = $("#vocab-roll-random-btn");
  if (rollDialogBtn) {
    rollDialogBtn.onclick = handle(() => {
      const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const key = generateRandomKey(count);
      const res = buildPseudoRandomDraft(key, count, vocabWorkingDraft);
      if (res) {
        vocabWorkingDraft = res.draft;
        vocabCurrentRandomKey = res.key;
        if ($("#vocab-random-key")) $("#vocab-random-key").value = res.key;
        if ($("#vocab-preset-id") && !$("#vocab-preset-id").value) {
          $("#vocab-preset-id").value = `random_${res.seed}`;
        }
        if ($("#vocab-preset-name") && !$("#vocab-preset-name").value) {
          $("#vocab-preset-name").value = `Random ${res.seed} (${res.count}/cat)`;
        }
        renderVocabTabs();
        selectVocabCategory(vocabActiveCategory);
        renderVocabSelectionSummary();
        const details = $("#vocab-random-summary-details");
        if (details) details.open = true;
        notice(`Rolled key: ${res.key}. Overview updated below.`);
      }
    });
  }

  const applyKeyBtn = $("#vocab-apply-key-btn");
  if (applyKeyBtn) {
    applyKeyBtn.onclick = handle(() => {
      const raw = ($("#vocab-random-key")?.value || "").trim();
      if (!raw) throw new Error("Enter a key in format seed:count (e.g. 482910:5)");
      const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const res = buildPseudoRandomDraft(raw, count, vocabWorkingDraft);
      if (!res) throw new Error("Invalid key format. Expected seed:count");
      vocabWorkingDraft = res.draft;
      vocabCurrentRandomKey = res.key;
      if ($("#vocab-random-count")) $("#vocab-random-count").value = res.count;
      renderVocabTabs();
      selectVocabCategory(vocabActiveCategory);
      renderVocabSelectionSummary();
      const details = $("#vocab-random-summary-details");
      if (details) details.open = true;
      notice(`Applied key "${res.key}".`);
    });
  }

  const copyKeyBtn = $("#vocab-copy-key-btn");
  if (copyKeyBtn) {
    copyKeyBtn.onclick = handle(() => {
      const key = ($("#vocab-random-key")?.value || vocabCurrentRandomKey || "").trim();
      if (!key) throw new Error("No pseudo-random key to copy.");
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(key).catch(() => {});
      }
      notice(`Copied key "${key}" to clipboard.`);
    });
  }

  const saveKeyBtn = $("#vocab-save-key-btn");
  if (saveKeyBtn) {
    saveKeyBtn.onclick = handle(() => {
      const key = ($("#vocab-random-key")?.value || vocabCurrentRandomKey || "").trim();
      if (!key) throw new Error("No pseudo-random key to save.");
      saveVocabKey(key);
      renderSavedKeysSelect();
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(key).catch(() => {});
      }
      notice(`Key "${key}" saved to bookmarks!`);
    });
  }

  const loadSavedKeyBtn = $("#vocab-load-saved-key-btn");
  if (loadSavedKeyBtn) {
    loadSavedKeyBtn.onclick = handle(() => {
      const sel = $("#vocab-saved-keys-select");
      const key = sel?.value;
      if (!key) throw new Error("Select a saved key from the dropdown first.");
      if ($("#vocab-random-key")) $("#vocab-random-key").value = key;
      const res = buildPseudoRandomDraft(key, 5, vocabWorkingDraft);
      if (res) {
        vocabWorkingDraft = res.draft;
        vocabCurrentRandomKey = res.key;
        if ($("#vocab-random-count")) $("#vocab-random-count").value = res.count;
        renderVocabTabs();
        selectVocabCategory(vocabActiveCategory);
        renderVocabSelectionSummary();
        notice(`Loaded saved key "${key}".`);
      }
    });
  }

  const deleteKeyBtn = $("#vocab-delete-key-btn");
  if (deleteKeyBtn) {
    deleteKeyBtn.onclick = handle(() => {
      const sel = $("#vocab-saved-keys-select");
      const key = sel?.value;
      if (!key) throw new Error("Select a saved key to remove.");
      deleteSavedVocabKey(key);
      renderSavedKeysSelect();
      notice(`Removed saved key "${key}".`);
    });
  }

  const randomCatBtn = $("#vocab-random-cat-btn");
  if (randomCatBtn) {
    randomCatBtn.onclick = handle(() => {
      const cat = vocabActiveCategory;
      randomizeSingleCategory(cat);
    });
  }

  const dialogSelect = $("#vocab-dialog-preset-select");
  if (dialogSelect) {
    dialogSelect.onchange = updateDeletePresetBtnVisibility;
  }

  const loadPresetBtn = $("#vocab-load-preset-btn");
  if (loadPresetBtn) {
    loadPresetBtn.onclick = handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      vocabCurrentRandomKey = "";
      if ($("#vocab-random-key")) $("#vocab-random-key").value = "";
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
      renderVocabSelectionSummary();
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
      renderVocabSelectionSummary();
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
      renderVocabSelectionSummary();
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
      renderVocabSelectionSummary();
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
      renderVocabSelectionSummary();
    };
  }

  const resetCatBtn = $("#vocab-reset-cat-btn");
  if (resetCatBtn) {
    resetCatBtn.onclick = () => {
      const cat = vocabActiveCategory;
      delete vocabWorkingDraft[cat];
      renderVocabCategoryContent(cat);
      updateTabBadges();
      renderVocabSelectionSummary();
      notice(`Category "${cat}" reset to default.`);
    };
  }

  const applyBtn = $("#vocab-apply-btn");
  if (applyBtn) {
    applyBtn.onclick = handle(() => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      state.currentCustomVocab = JSON.parse(JSON.stringify(vocabWorkingDraft));
      state.currentVocabRandomKey = vocabCurrentRandomKey || "";
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
      vocabCurrentRandomKey = "";
      if ($("#vocab-random-key")) $("#vocab-random-key").value = "";
      renderVocabTabs();
      selectVocabCategory(vocabActiveCategory);
      renderVocabSelectionSummary();
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

export function randomizeSingleCategory(cat) {
  if (!vocabDataCache || !vocabDataCache.base?.[cat]) return;
  const baseItems = vocabDataCache.base[cat] || [];
  if (baseItems.length === 0) return;
  const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
  const sampleSize = Math.min(Math.max(1, count), baseItems.length);

  // Random shuffle of indices
  const indices = baseItems.map((_, i) => i);
  for (let i = indices.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  const chosenIndices = new Set(indices.slice(0, sampleSize));
  const excluded = baseItems.filter((_, idx) => !chosenIndices.has(idx));

  if (!vocabWorkingDraft[cat]) {
    vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [] };
  }
  vocabWorkingDraft[cat].mode = "append";
  vocabWorkingDraft[cat].exclude = excluded;

  if (vocabActiveCategory === cat) {
    renderVocabCategoryContent(cat);
  }
  updateTabBadges();
  renderVocabSelectionSummary();
  notice(`Randomized category "${cat.replace(/_/g, " ")}" with ${sampleSize} items.`);
}

export function drawOneAdditionalRandomItem(cat) {
  if (!vocabDataCache || !vocabDataCache.base?.[cat]) return;
  const baseItems = vocabDataCache.base[cat] || [];
  const override = vocabWorkingDraft[cat];
  const excluded = new Set(override?.exclude || []);
  const candidates = baseItems.filter(item => excluded.has(item));
  if (candidates.length === 0) {
    notice(`All built-in items for "${cat.replace(/_/g, " ")}" are already active.`);
    return;
  }
  const pick = candidates[Math.floor(Math.random() * candidates.length)];
  excluded.delete(pick);
  if (!vocabWorkingDraft[cat]) {
    vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [] };
  }
  vocabWorkingDraft[cat].exclude = [...excluded];

  if (vocabActiveCategory === cat) {
    renderVocabCategoryContent(cat);
  }
  updateTabBadges();
  renderVocabSelectionSummary();
  notice(`Added "${pick}" to ${cat.replace(/_/g, " ")}.`);
}

export function removeSingleItemFromCategory(cat, item) {
  const override = vocabWorkingDraft[cat];
  const baseItems = vocabDataCache?.base?.[cat] || [];
  const isCustom = override?.add?.includes(item);

  // Check if removing this would leave category empty
  const activeCount = getCategoryActiveCount(cat);
  if (activeCount <= 1) {
    notice("Each category must keep at least 1 active entry.");
    return;
  }

  if (isCustom) {
    override.add = override.add.filter(x => x !== item);
  } else {
    if (!vocabWorkingDraft[cat]) {
      vocabWorkingDraft[cat] = { mode: "append", add: [], exclude: [] };
    }
    const exc = new Set(vocabWorkingDraft[cat].exclude || []);
    exc.add(item);
    vocabWorkingDraft[cat].exclude = [...exc];
  }

  if (vocabActiveCategory === cat) {
    renderVocabCategoryContent(cat);
  }
  updateTabBadges();
  renderVocabSelectionSummary();
}

function getCategoryActiveCount(cat) {
  if (!vocabDataCache) return 0;
  const baseItems = vocabDataCache.base?.[cat] || [];
  const override = vocabWorkingDraft[cat];
  if (!override) return baseItems.length;
  if (override.mode === "replace") return (override.add || []).length;
  const exc = new Set(override.exclude || []);
  const remaining = baseItems.filter(x => !exc.has(x)).length;
  return remaining + (override.add || []).length;
}

export function renderVocabSelectionSummary() {
  const grid = $("#vocab-random-summary-grid");
  const badge = $("#vocab-random-status-badge");
  if (!grid || !vocabDataCache) return;

  const categories = vocabDataCache.categories || Object.keys(vocabDataCache.base || {});
  let totalActive = 0;
  let customizedCats = 0;

  const cards = categories.map(cat => {
    const baseItems = vocabDataCache.base?.[cat] || [];
    const override = vocabWorkingDraft[cat];
    let activeItems = [];
    if (override?.mode === "replace") {
      activeItems = [...(override.add || [])];
      customizedCats++;
    } else {
      const exc = new Set(override?.exclude || []);
      const remaining = baseItems.filter(x => !exc.has(x));
      const added = override?.add || [];
      activeItems = [...remaining, ...added];
      if (exc.size > 0 || added.length > 0) customizedCats++;
    }
    totalActive += activeItems.length;

    const card = document.createElement("div");
    card.className = "vocab-summary-cat-card";

    const header = document.createElement("div");
    header.className = "vocab-summary-cat-header";

    const titleWrap = document.createElement("div");
    titleWrap.className = "vocab-summary-cat-title-wrap";
    const nameSpan = document.createElement("span");
    nameSpan.className = "vocab-summary-cat-name";
    nameSpan.textContent = cat.replace(/_/g, " ");
    const countBadge = document.createElement("span");
    countBadge.className = "vocab-summary-cat-count";
    countBadge.textContent = `${activeItems.length} active`;
    titleWrap.append(nameSpan, countBadge);

    const actions = document.createElement("div");
    actions.className = "vocab-summary-cat-actions";

    const addOneBtn = document.createElement("button");
    addOneBtn.type = "button";
    addOneBtn.className = "quiet";
    addOneBtn.title = "Draw one more random item into this category";
    addOneBtn.textContent = "+1";
    addOneBtn.onclick = (e) => {
      e.stopPropagation();
      drawOneAdditionalRandomItem(cat);
    };

    const rerollBtn = document.createElement("button");
    rerollBtn.type = "button";
    rerollBtn.className = "quiet";
    rerollBtn.title = "Randomize this category only";
    rerollBtn.textContent = "🎲";
    rerollBtn.onclick = (e) => {
      e.stopPropagation();
      randomizeSingleCategory(cat);
    };

    actions.append(addOneBtn, rerollBtn);
    header.append(titleWrap, actions);

    header.onclick = () => {
      selectVocabCategory(cat);
    };

    const chipsWrap = document.createElement("div");
    chipsWrap.className = "vocab-summary-chips";

    activeItems.forEach(item => {
      const chip = document.createElement("span");
      chip.className = "vocab-chip";
      const textSpan = document.createElement("span");
      textSpan.className = "vocab-chip-text";
      textSpan.textContent = item;

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "vocab-chip-remove";
      removeBtn.setAttribute("aria-label", `Remove ${item}`);
      removeBtn.textContent = "×";
      removeBtn.onclick = (e) => {
        e.stopPropagation();
        removeSingleItemFromCategory(cat, item);
      };

      chip.append(textSpan, removeBtn);
      chipsWrap.append(chip);
    });

    if (activeItems.length === 0) {
      const emptyNote = document.createElement("span");
      emptyNote.className = "vocab-chip-empty";
      emptyNote.textContent = "No active items";
      chipsWrap.append(emptyNote);
    }

    card.append(header, chipsWrap);
    return card;
  });

  grid.replaceChildren(...cards);

  if (badge) {
    if (vocabCurrentRandomKey) {
      badge.textContent = `🎲 ${vocabCurrentRandomKey} (${totalActive} active)`;
      badge.style.color = "var(--accent)";
    } else if (customizedCats > 0) {
      badge.textContent = `${customizedCats} categories customized (${totalActive} active)`;
      badge.style.color = "var(--green)";
    } else {
      badge.textContent = `All built-in (${totalActive} active)`;
      badge.style.color = "var(--muted)";
    }
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
      renderVocabSelectionSummary();
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
      renderVocabSelectionSummary();
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

