// Visual Vocabulary Customizer — Functional HTML Templates & Delegated UI Controller.

import { $, $$, api, handle, json, notice, option, state } from "./core.js";
import { scheduleSave } from "./project.js";
import {
  cleanDraft,
  cloneDraft,
  computePseudoRandomDraft,
  deleteSavedVocabKey,
   generateRandomKey,
  getCategoryStats,
  getSavedVocabKeys,
  getSummaryStats,
  parseRandomKey,
  presetToDraft,
  saveVocabKey,
  withAddedRandomItem,
  withCustomLines,
  withoutCategoryItem,
  withRandomizedCategory,
  withToggledBuiltinItem
} from "./vocab-model.js";

export {
  deleteSavedVocabKey,
  generateRandomKey,
  getSavedVocabKeys,
  parseRandomKey,
  saveVocabKey
};

let vocabDataCache = null;
let vocabActiveCategory = "settings";
let vocabWorkingDraft = {};
let vocabCurrentRandomKey = "";

const MAX_SUMMARY_CHIPS = 20;

// --- Pure HTML Template Builders (Option A) ---

const escapeHtml = (s = "") =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

const formatCatLabel = (cat = "") => cat.replace(/_/g, " ");

const tabsHtml = (categories, activeCat, catalog, draft) =>
  categories
    .map((cat) => {
      const { count, isModified } = getCategoryStats(catalog, draft, cat);
      const escCat = escapeHtml(cat);
      const active = cat === activeCat ? " active" : "";
      const weight = isModified ? "700" : "600";
      return `<button type="button" class="vocab-tab-btn${active}" data-category="${escCat}" style="font-weight:${weight}">${escapeHtml(formatCatLabel(cat))}<span class="vocab-tab-badge">${count}</span></button>`;
    })
    .join("");

const checkboxGridHtml = (baseItems, excludedSet) =>
  baseItems
    .map((item) => {
      const esc = escapeHtml(item);
      const checked = excludedSet.has(item) ? "" : " checked";
      return `<label class="vocab-item-label" title="${esc}"><input type="checkbox" value="${esc}"${checked}>${esc}</label>`;
    })
    .join("");

const chipsHtml = (cat, activeItems) => {
  if (!activeItems.length) {
    return `<div class="vocab-summary-chips"><span class="vocab-chip-empty">No active items</span></div>`;
  }
  const escCat = escapeHtml(cat);
  const itemsHtml = activeItems
    .slice(0, MAX_SUMMARY_CHIPS)
    .map((item) => {
      const esc = escapeHtml(item);
      return `<span class="vocab-chip"><span class="vocab-chip-text">${esc}</span><button type="button" class="vocab-chip-remove" data-action="remove-chip" data-category="${escCat}" data-item="${esc}" aria-label="Remove ${esc}">×</button></span>`;
    })
    .join("");
  const moreHtml =
    activeItems.length > MAX_SUMMARY_CHIPS
      ? `<button type="button" class="vocab-chip-more" data-action="select-cat" data-category="${escCat}" aria-label="Show all entries in ${escapeHtml(cat.replace(/_/g, " "))}">+${activeItems.length - MAX_SUMMARY_CHIPS} more (open tab)</button>`
      : "";
  return `<div class="vocab-summary-chips">${itemsHtml}${moreHtml}</div>`;
};

const summaryCardHtml = (cat, activeItems) => {
  const escCat = escapeHtml(cat);
  return `<div class="vocab-summary-cat-card" data-category="${escCat}">
    <div class="vocab-summary-cat-header" data-action="select-cat" data-category="${escCat}">
      <div class="vocab-summary-cat-title-wrap">
        <span class="vocab-summary-cat-name">${escapeHtml(formatCatLabel(cat))}</span>
        <span class="vocab-summary-cat-count">${activeItems.length} active</span>
      </div>
      <div class="vocab-summary-cat-actions">
        <button type="button" class="quiet" data-action="add-one" data-category="${escCat}" title="Draw one more random item into this category">+1</button>
        <button type="button" class="quiet" data-action="reroll-cat" data-category="${escCat}" title="Randomize this category only">🎲</button>
      </div>
    </div>
    ${chipsHtml(cat, activeItems)}
  </div>`;
};

// --- Backwards-Compatible Model Wrapper ---

export const buildPseudoRandomDraft = (rawKey, fallbackCount = 5, existingDraft = {}) =>
  computePseudoRandomDraft(vocabDataCache, rawKey, fallbackCount, existingDraft);

// --- DOM Sync & Render Functions ---

const copyToClipboard = (text) => {
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {});
};

export function renderSavedKeysSelect() {
  const select = $("#vocab-saved-keys-select");
  const row = $("#vocab-saved-keys-row");
  if (!select) return;
  const keys = getSavedVocabKeys();
  if (row) row.hidden = keys.length === 0;
  select.replaceChildren(
    option("", keys.length ? `Saved keys (${keys.length})…` : "No saved keys yet"),
    ...keys.map((k) => option(k, `🎲 ${k}`))
  );
}

export function updateVocabCustomBadge() {
  const badge = $("#vocab-custom-badge");
  const quickBar = $("#vocab-random-quick-bar");
  const quickKeyInput = $("#vocab-quick-key-input");
  const customCount = Object.keys(state.currentCustomVocab || {}).length;
  const randomKey = state.currentVocabRandomKey || "";

  if (badge) {
    badge.textContent = randomKey ? `🎲 ${randomKey}` : `${customCount} customized`;
    badge.hidden = !randomKey && customCount === 0;
  }
  if (quickBar) {
    quickBar.hidden = !randomKey;
    if (randomKey && quickKeyInput) quickKeyInput.value = randomKey;
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
  const presets = (vocabDataCache.vocabularies || []).map((p) => [p.id, `${p.name} (${p.id})`]);
  const entries = [
    ["full", "Full vocabulary (current default)"],
    ["reduced_flashing", "Reduced flash/strobe cues (hellonearthis)"],
    ...presets
  ];

  ["#vocab-profile-select", "#vocab-dialog-preset-select"].forEach((sel) => {
    const el = $(sel);
    if (!el) return;
    const prev = el.value || "full";
    el.replaceChildren(...entries.map(([val, label]) => option(val, label)));
    if (entries.some(([val]) => val === prev)) el.value = prev;
  });
}

export function updateDeletePresetBtnVisibility() {
  const deleteBtn = $("#vocab-delete-preset-btn");
  const selected = $("#vocab-dialog-preset-select")?.value;
  if (deleteBtn) {
    deleteBtn.style.display =
      selected && selected !== "full" && selected !== "reduced_flashing" ? "inline" : "none";
  }
}

const applySummaryBadgeStyle = (totalActive, customizedCats) => {
  const badge = $("#vocab-random-status-badge");
  if (!badge) return;
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
};

function updateVocabSummaryBadge() {
  if (!vocabDataCache) return;
  const { totalActive, customizedCats } = getSummaryStats(vocabDataCache, vocabWorkingDraft);
  applySummaryBadgeStyle(totalActive, customizedCats);
}

export function renderVocabSelectionSummary(force = false) {
  const grid = $("#vocab-random-summary-grid");
  if (!grid || !vocabDataCache) return;
  const details = $("#vocab-random-summary-details");
  if (!force && details && !details.open) {
    updateVocabSummaryBadge();
    return;
  }
  const { categories, byCategory, totalActive, customizedCats } = getSummaryStats(
    vocabDataCache,
    vocabWorkingDraft
  );
  grid.innerHTML = categories
    .map((cat) => summaryCardHtml(cat, byCategory[cat].activeItems))
    .join("");
  applySummaryBadgeStyle(totalActive, customizedCats);
}

export function updateVocabCategoryCard(cat) {
  const card = $(`#vocab-random-summary-grid .vocab-summary-cat-card[data-category="${cat}"]`);
  if (!card || !vocabDataCache) {
    renderVocabSelectionSummary();
    return;
  }
  const { activeItems, count } = getCategoryStats(vocabDataCache, vocabWorkingDraft, cat);
  const countBadge = card.querySelector(".vocab-summary-cat-count");
  if (countBadge) countBadge.textContent = `${count} active`;
  const oldChips = card.querySelector(".vocab-summary-chips");
  if (oldChips) oldChips.outerHTML = chipsHtml(cat, activeItems);
  updateVocabSummaryBadge();
}

export function renderVocabTabs() {
  const container = $("#vocab-category-tabs");
  if (!container || !vocabDataCache) return;
  const categories = vocabDataCache.categories || [];
  container.innerHTML = tabsHtml(categories, vocabActiveCategory, vocabDataCache, vocabWorkingDraft);
}

export function updateTabBadges() {
  if (!vocabDataCache) return;
  $$(".vocab-tab-btn").forEach((btn) => {
    const { count, isModified } = getCategoryStats(
      vocabDataCache,
      vocabWorkingDraft,
      btn.dataset.category
    );
    const badge = btn.querySelector(".vocab-tab-badge");
    if (badge) badge.textContent = count;
    btn.style.fontWeight = isModified ? "700" : "600";
  });
}

export function updateActiveCategoryCount() {
  if (!vocabDataCache) return;
  const { count } = getCategoryStats(vocabDataCache, vocabWorkingDraft, vocabActiveCategory);
  const badge = $("#vocab-active-count-badge");
  if (badge) {
    badge.textContent = `${count} active`;
    badge.style.color = count === 0 ? "var(--muted)" : "var(--green)";
  }
}

export function renderVocabCategoryContent(cat) {
  if (!vocabDataCache) return;
  const titleEl = $("#vocab-active-category-title");
  if (titleEl) titleEl.textContent = formatCatLabel(cat).toUpperCase();

  const override = vocabWorkingDraft[cat] || { mode: "append", add: [], exclude: [] };
  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) modeSelect.value = override.mode || "append";

  const builtinSection = $("#vocab-builtin-section");
  if (builtinSection) builtinSection.hidden = override.mode === "replace";

  const grid = $("#vocab-checkbox-grid");
  if (grid) {
    const baseItems = vocabDataCache.base?.[cat] || [];
    const excludedSet = new Set(override.exclude || []);
    grid.innerHTML = checkboxGridHtml(baseItems, excludedSet);
  }

  const textarea = $("#vocab-custom-textarea");
  if (textarea) textarea.value = (override.add || []).join("\n");

  const searchInput = $("#vocab-search-input");
  if (searchInput) searchInput.value = "";
  updateActiveCategoryCount();
}

export function showVocabCategory(cat) {
  vocabActiveCategory = cat;
  $$(".vocab-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.category === cat));
  renderVocabCategoryContent(cat);
}

export function selectVocabCategory(cat) {
  saveActiveCategoryCustomText();
  showVocabCategory(cat);
}

export function saveActiveCategoryCustomText() {
  const textarea = $("#vocab-custom-textarea");
  if (!textarea || !vocabDataCache) return;
  const mode = $("#vocab-category-mode")?.value || "append";
  vocabWorkingDraft = withCustomLines(vocabWorkingDraft, vocabActiveCategory, textarea.value, mode);
}

export function cleanWorkingDraft() {
  vocabWorkingDraft = cleanDraft(vocabWorkingDraft);
}

export function filterCheckboxGrid(term) {
  const grid = $("#vocab-checkbox-grid");
  if (!grid) return;
  const q = (term || "").toLowerCase().trim();
  grid.querySelectorAll(".vocab-item-label").forEach((label) => {
    label.style.display = !q || label.textContent.toLowerCase().includes(q) ? "flex" : "none";
  });
}

// --- Category Item Mutations ---

const refreshCategoryUI = (cat, fullSummary = false) => {
  if (vocabActiveCategory === cat) renderVocabCategoryContent(cat);
  updateTabBadges();
  if (fullSummary) renderVocabSelectionSummary();
  else updateVocabCategoryCard(cat);
};

export function randomizeSingleCategory(cat) {
  const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
  const res = withRandomizedCategory(vocabDataCache, vocabWorkingDraft, cat, count);
  if (!res) return;
  vocabWorkingDraft = res.draft;
  refreshCategoryUI(cat, true);
  notice(`Randomized category "${formatCatLabel(cat)}" with ${res.sampleSize} items.`);
}

export function drawOneAdditionalRandomItem(cat) {
  if (!vocabDataCache?.base?.[cat]) return;
  const { draft, picked } = withAddedRandomItem(vocabDataCache, vocabWorkingDraft, cat);
  if (!picked) {
    notice(`All built-in items for "${formatCatLabel(cat)}" are already active.`);
    return;
  }
  vocabWorkingDraft = draft;
  refreshCategoryUI(cat, false);
  notice(`Added "${picked}" to ${formatCatLabel(cat)}.`);
}

export function removeSingleItemFromCategory(cat, item) {
  const { draft, removed, minReached } = withoutCategoryItem(vocabDataCache, vocabWorkingDraft, cat, item);
  if (minReached) {
    notice("Each category must keep at least 1 active entry.");
    return;
  }
  if (removed) {
    vocabWorkingDraft = draft;
    refreshCategoryUI(cat, false);
  }
}

// --- Panel / Dialog Lifecycle ---

const refreshEditorAll = () => {
  renderVocabTabs();
  showVocabCategory(vocabActiveCategory);
  renderVocabSelectionSummary();
};

const applyRandomToProject = (res, msg) => {
  if (!res) return;
  state.currentCustomVocab = res.draft;
  state.currentVocabRandomKey = res.key;
  vocabWorkingDraft = cloneDraft(res.draft);
  vocabCurrentRandomKey = res.key;
  updateVocabCustomBadge();
  scheduleSave();
  notice(msg);
};

const applyRandomToEditor = (res, msg, openDetails = true) => {
  if (!res) return;
  vocabWorkingDraft = res.draft;
  vocabCurrentRandomKey = res.key;
  if ($("#vocab-random-key")) $("#vocab-random-key").value = res.key;
  if ($("#vocab-random-count")) $("#vocab-random-count").value = res.count;
  refreshEditorAll();
  if (openDetails && $("#vocab-random-summary-details")) {
    $("#vocab-random-summary-details").open = true;
  }
  notice(msg);
};

export async function openVocabularyPanel() {
  await loadVocabularyCatalog();
  vocabWorkingDraft = cloneDraft(state.currentCustomVocab || {});
  vocabCurrentRandomKey = state.currentVocabRandomKey || "";
  const currentProfile = $("#vocab-profile-select")?.value || "full";
  if ($("#vocab-dialog-preset-select")) $("#vocab-dialog-preset-select").value = currentProfile;
  updateDeletePresetBtnVisibility();
  renderSavedKeysSelect();
  if ($("#vocab-random-key")) $("#vocab-random-key").value = vocabCurrentRandomKey;
  renderVocabTabs();
  showVocabCategory(vocabActiveCategory);

  const summaryDetails = $("#vocab-random-summary-details");
  if (summaryDetails?.open) renderVocabSelectionSummary();
  else updateVocabSummaryBadge();

  const panelVocab = $("#panel-vocab");
  if (panelVocab) {
    if (panelVocab.hidden) {
      $$(".panel").forEach((node) => (node.hidden = node.id !== "panel-vocab"));
      $$(".nav[data-panel]").forEach((node) => {
        const active = node.dataset.panel === "vocab";
        node.classList.toggle("active", active);
        node.setAttribute("aria-current", active ? "page" : "false");
      });
      scheduleSave();
    }
  } else {
    $("#vocabulary-dialog")?.showModal?.();
  }
}

// --- Delegated Listeners & Declarative Action Wiring ---

export function setupVocabularyCustomizer() {
  if (!$("#panel-vocab") && !$("#vocabulary-dialog")) return;
  loadVocabularyCatalog().catch(() => {});

  // 1. Single delegated click handler for Category Tabs
  $("#vocab-category-tabs")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".vocab-tab-btn[data-category]");
    if (btn) selectVocabCategory(btn.dataset.category);
  });

  // 2. Single delegated change handler for Built-in Checkboxes
  $("#vocab-checkbox-grid")?.addEventListener("change", (e) => {
    const cb = e.target;
    if (cb?.type !== "checkbox") return;
    const mode = $("#vocab-category-mode")?.value || "append";
    vocabWorkingDraft = withToggledBuiltinItem(
      vocabWorkingDraft,
      vocabActiveCategory,
      cb.value,
      cb.checked,
      mode
    );
    updateActiveCategoryCount();
    updateTabBadges();
    updateVocabCategoryCard(vocabActiveCategory);
  });

  // 3. Single delegated click handler for Summary Cards & Chips
  $("#vocab-random-summary-grid")?.addEventListener("click", (e) => {
    const actionEl = e.target.closest("[data-action]");
    if (!actionEl) return;
    const { action, category, item } = actionEl.dataset;
    if (action === "remove-chip") removeSingleItemFromCategory(category, item);
    else if (action === "add-one") drawOneAdditionalRandomItem(category);
    else if (action === "reroll-cat") randomizeSingleCategory(category);
    else if (action === "select-cat") selectVocabCategory(category);
  });

  // 4. Summary drawer lazy render on open
  $("#vocab-random-summary-details")?.addEventListener("toggle", (e) => {
    if (e.currentTarget.open) renderVocabSelectionSummary(true);
  });

  // 5. Textarea, Mode & Filter inputs
  const textarea = $("#vocab-custom-textarea");
  if (textarea) {
    textarea.oninput = () => {
      saveActiveCategoryCustomText();
      updateActiveCategoryCount();
      updateTabBadges();
      updateVocabCategoryCard(vocabActiveCategory);
    };
  }

  const modeSelect = $("#vocab-category-mode");
  if (modeSelect) {
    modeSelect.onchange = () => {
      saveActiveCategoryCustomText();
      const cat = vocabActiveCategory;
      vocabWorkingDraft[cat] = {
        ...(vocabWorkingDraft[cat] || { add: [], exclude: [] }),
        mode: modeSelect.value
      };
      refreshCategoryUI(cat, true);
    };
  }

  const searchInput = $("#vocab-search-input");
  if (searchInput) searchInput.oninput = () => filterCheckboxGrid(searchInput.value);

  const dialogSelect = $("#vocab-dialog-preset-select");
  if (dialogSelect) dialogSelect.onchange = updateDeletePresetBtnVisibility;

  // 6. Declarative Button Action Map
  const actions = {
    "#open-vocab-panel-btn, #open-vocab-dialog": handle(() => openVocabularyPanel()),

    "#roll-vocab-random-btn": handle(async () => {
      await loadVocabularyCatalog();
      const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const res = buildPseudoRandomDraft(generateRandomKey(count), count, state.currentCustomVocab || {});
      applyRandomToProject(res, `Rolled pseudo-random vocabulary key: ${res?.key}`);
    }),

    "#vocab-quick-apply-key-btn": handle(async () => {
      await loadVocabularyCatalog();
      const raw = ($("#vocab-quick-key-input")?.value || "").trim();
      if (!raw) throw new Error("Enter a pseudo-random key (e.g. 482910:5)");
      const res = buildPseudoRandomDraft(raw, 5, state.currentCustomVocab || {});
      if (!res) throw new Error("Invalid key format. Use seed:count (e.g. 482910:5)");
      applyRandomToProject(res, `Applied pseudo-random key: ${res.key}`);
    }),

    "#vocab-quick-reroll-btn": handle(async () => {
      await loadVocabularyCatalog();
      const count = parseRandomKey(state.currentVocabRandomKey || "", 5)?.count || 5;
      const res = buildPseudoRandomDraft(generateRandomKey(count), count, state.currentCustomVocab || {});
      applyRandomToProject(res, `Rerolled pseudo-random key: ${res?.key}`);
    }),

    "#vocab-quick-save-key-btn": handle(() => {
      const key = state.currentVocabRandomKey || ($("#vocab-quick-key-input")?.value || "").trim();
      if (!key) throw new Error("No pseudo-random key to save.");
      saveVocabKey(key);
      renderSavedKeysSelect();
      copyToClipboard(key);
      notice(`Saved key "${key}" and copied to clipboard.`);
    }),

    "#vocab-quick-edit-btn": handle(async () => {
      await openVocabularyPanel();
      if ($("#vocab-random-summary-details")) $("#vocab-random-summary-details").open = true;
    }),

    "#vocab-quick-clear-btn": handle(() => {
      state.currentVocabRandomKey = "";
      state.currentCustomVocab = {};
      vocabWorkingDraft = {};
      vocabCurrentRandomKey = "";
      updateVocabCustomBadge();
      scheduleSave();
      notice("Cleared pseudo-random vocabulary. Restored full built-in vocabulary.");
    }),

    "#vocab-roll-random-btn": handle(() => {
      const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const res = buildPseudoRandomDraft(generateRandomKey(count), count, vocabWorkingDraft);
      if (res) {
        if ($("#vocab-preset-id") && !$("#vocab-preset-id").value) {
          $("#vocab-preset-id").value = `random_${res.seed}`;
        }
        if ($("#vocab-preset-name") && !$("#vocab-preset-name").value) {
          $("#vocab-preset-name").value = `Random ${res.seed} (${res.count}/cat)`;
        }
        applyRandomToEditor(res, `Rolled key: ${res.key}. Overview updated below.`);
      }
    }),

    "#vocab-apply-key-btn": handle(() => {
      const raw = ($("#vocab-random-key")?.value || "").trim();
      if (!raw) throw new Error("Enter a key in format seed:count (e.g. 482910:5)");
      const count = parseInt($("#vocab-random-count")?.value, 10) || 5;
      const res = buildPseudoRandomDraft(raw, count, vocabWorkingDraft);
      if (!res) throw new Error("Invalid key format. Expected seed:count");
      applyRandomToEditor(res, `Applied key "${res.key}".`);
    }),

    "#vocab-copy-key-btn": handle(() => {
      const key = ($("#vocab-random-key")?.value || vocabCurrentRandomKey || "").trim();
      if (!key) throw new Error("No pseudo-random key to copy.");
      copyToClipboard(key);
      notice(`Copied key "${key}" to clipboard.`);
    }),

    "#vocab-save-key-btn": handle(() => {
      const key = ($("#vocab-random-key")?.value || vocabCurrentRandomKey || "").trim();
      if (!key) throw new Error("No pseudo-random key to save.");
      saveVocabKey(key);
      renderSavedKeysSelect();
      copyToClipboard(key);
      notice(`Key "${key}" saved to bookmarks!`);
    }),

    "#vocab-load-saved-key-btn": handle(() => {
      const key = $("#vocab-saved-keys-select")?.value;
      if (!key) throw new Error("Select a saved key from the dropdown first.");
      const res = buildPseudoRandomDraft(key, 5, vocabWorkingDraft);
      applyRandomToEditor(res, `Loaded saved key "${key}".`, false);
    }),

    "#vocab-delete-key-btn": handle(() => {
      const key = $("#vocab-saved-keys-select")?.value;
      if (!key) throw new Error("Select a saved key to remove.");
      deleteSavedVocabKey(key);
      renderSavedKeysSelect();
      notice(`Removed saved key "${key}".`);
    }),

    "#vocab-random-cat-btn": handle(() => randomizeSingleCategory(vocabActiveCategory)),

    "#vocab-load-preset-btn": handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      vocabCurrentRandomKey = "";
      if ($("#vocab-random-key")) $("#vocab-random-key").value = "";
      vocabWorkingDraft = presetToDraft(vocabDataCache, selectedId);
      refreshEditorAll();
      notice(`Loaded preset "${selectedId}" into editor.`);
    }),

    "#vocab-delete-preset-btn": handle(async () => {
      const selectedId = $("#vocab-dialog-preset-select").value;
      if (!window.confirm(`Delete vocabulary preset "${selectedId}" from this machine?`)) return;
      await api(`/api/vocabularies/${encodeURIComponent(selectedId)}`, { method: "DELETE" });
      await loadVocabularyCatalog(true);
      notice("Vocabulary preset deleted.");
      selectVocabCategory(vocabActiveCategory);
      renderVocabSelectionSummary();
    }),

    "#vocab-select-all-btn": () => {
      const cat = vocabActiveCategory;
      if (vocabWorkingDraft[cat]) vocabWorkingDraft[cat].exclude = [];
      $$("#vocab-checkbox-grid input[type=checkbox]").forEach((cb) => (cb.checked = true));
      updateActiveCategoryCount();
      updateTabBadges();
      renderVocabSelectionSummary();
    },

    "#vocab-clear-all-btn": () => {
      const cat = vocabActiveCategory;
      const baseItems = vocabDataCache?.base?.[cat] || [];
      vocabWorkingDraft[cat] = {
        mode: vocabWorkingDraft[cat]?.mode || "append",
        add: [...(vocabWorkingDraft[cat]?.add || [])],
        exclude: [...baseItems]
      };
      $$("#vocab-checkbox-grid input[type=checkbox]").forEach((cb) => (cb.checked = false));
      updateActiveCategoryCount();
      updateTabBadges();
      renderVocabSelectionSummary();
    },

    "#vocab-reset-cat-btn": () => {
      const cat = vocabActiveCategory;
      delete vocabWorkingDraft[cat];
      refreshCategoryUI(cat, true);
      notice(`Category "${cat}" reset to default.`);
    },

    "#vocab-apply-btn": handle(() => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      state.currentCustomVocab = cloneDraft(vocabWorkingDraft);
      state.currentVocabRandomKey = vocabCurrentRandomKey || "";
      updateVocabCustomBadge();
      scheduleSave();
      const dialog = $("#vocabulary-dialog");
      if (dialog?.open) dialog.close?.();
      const videoNavBtn = $(".nav[data-panel='video']");
      if (videoNavBtn && $("#panel-vocab") && !$("#panel-vocab").hidden) videoNavBtn.click();
      notice("Vocabulary customizations applied to current video.");
    }),

    "#vocab-reset-all-btn": () => {
      if (!window.confirm("Reset all vocabulary customizations back to standard?")) return;
      vocabWorkingDraft = {};
      vocabCurrentRandomKey = "";
      if ($("#vocab-random-key")) $("#vocab-random-key").value = "";
      refreshEditorAll();
      notice("All category customizations cleared.");
    },

    "#vocab-save-preset-btn": handle(async () => {
      saveActiveCategoryCustomText();
      cleanWorkingDraft();
      const presetId = ($("#vocab-preset-id")?.value || "").trim().toLowerCase();
      const presetName = ($("#vocab-preset-name")?.value || "").trim();
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
    })
  };

  for (const [selector, fn] of Object.entries(actions)) {
    $$(selector).forEach((el) => (el.onclick = fn));
  }
}
