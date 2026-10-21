// Thematic Worlds, Classification Mode & Juxtaposition Arc Workspace.
// Pure functional architecture: deterministic calculations, explicit inputs/outputs, side-effect isolation.

import { $, $$, copyToClipboard, notice, state as appState } from "./core.js";
import { scheduleSave } from "./project.js";
import { loadVocabularyCatalog, updateVocabCustomBadge } from "./vocabulary.js";

export const DEFAULT_WORLDS = [
  { name: "Bureaucratic / Carceral", score: 0.81, active: true, locked: false },
  { name: "Brutalist Concrete", score: 0.70, active: true, locked: false },
  { name: "Industrial Decay", score: 0.62, active: false, locked: false },
  { name: "Maritime / Salt", score: 0.31, active: false, locked: false }
];

export const DEFAULT_SECTIONS = [
  { name: "Verse 1", baseKappa: 0.08 },
  { name: "Pre-chorus", baseKappa: 0.35 },
  { name: "Chorus", baseKappa: 0.75 },
  { name: "Verse 2", baseKappa: 0.20 },
  { name: "Bridge", baseKappa: 0.90 },
  { name: "Final chorus", baseKappa: 0.80 },
  { name: "Outro", baseKappa: 0.05 }
];

export const DEFAULT_POOLS = [
  {
    dimension: "Settings",
    pool: 14,
    need: 9,
    terms: ["evidence locker", "sodium-lit stairwell", "records annex", "flooded basement"]
  },
  {
    dimension: "Lighting",
    pool: 11,
    need: 6,
    terms: ["flickering fluorescent tube", "single desk lamp", "amber exit signs"]
  },
  {
    dimension: "Mechanisms",
    pool: 17,
    need: 10,
    terms: ["pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending"]
  },
  {
    dimension: "Costume",
    pool: 4,
    need: 6,
    terms: ["grey wool cardigan", "laminated lanyard"]
  },
  {
    dimension: "Practical Effects",
    pool: 9,
    need: 5,
    terms: ["drifting paper dust", "steam from a vent"]
  }
];

export const MODE_DESCRIPTIONS = {
  off: "Sampling from the entire visual vocabulary pool. Thematic worlds and juxtaposition levels are ignored.",
  guided: "Matched thematic worlds are weighted up. Diverse strays remain possible across musical passages.",
  strict: "Strictly confined to matched anchor worlds plus kappa-governed strays on high-energy sections."
};

const escapeHtml = (s = "") =>
  s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

export const computeEffectiveKappa = (baseKappa, sliderValue) => {
  const s = sliderValue / 100;
  return Math.max(0, Math.min(1, baseKappa * 2 * s));
};

export const renderWorldsHtml = (worlds, isOff) => {
  if (!worlds.length) return `<div class="sub">No worlds matched.</div>`;
  const items = worlds.map((w, i) => {
    const checked = w.active ? "checked" : "";
    const pct = Math.round(w.score * 100);
    const lockIcon = w.locked ? "🔒" : "🔓";
    const lockTitle = w.locked ? "Locked to prevent prompt overwrite" : "Lock this world";
    return `
      <div class="worlds-cluster-row" data-index="${i}">
        <label class="worlds-cluster-label">
          <input type="checkbox" class="worlds-cluster-check" data-index="${i}" ${checked} ${isOff ? "disabled" : ""}>
          <span class="worlds-cluster-name">${escapeHtml(w.name)}</span>
        </label>
        <div class="worlds-meter-track" data-tooltip="Semantic similarity score: ${w.score.toFixed(2)}">
          <span class="worlds-meter-fill" style="width:${pct}%;"></span>
        </div>
        <span class="worlds-score-val">${w.score.toFixed(2)}</span>
        <button type="button" class="worlds-lock-btn quiet" data-index="${i}" data-tooltip="${lockTitle}" ${isOff ? "disabled" : ""}>
          ${lockIcon}
        </button>
      </div>
    `;
  }).join("");

  const margin = worlds.length >= 2 ? (worlds[0].score - worlds[1].score).toFixed(2) : "0.00";
  const gapNote = `<div class="sub worlds-gap-note">Top match leads the next by ${margin}, indicating a strong thematic anchor.</div>`;

  return items + gapNote;
};

export const renderBarsHtml = (sections, sliderValue, mode) => {
  const isOff = mode === "off";
  const s = sliderValue / 100;
  const multText = `x${(2 * s).toFixed(1)}`;

  const bars = sections.map((sec) => {
    const effKappa = isOff ? 0 : computeEffectiveKappa(sec.baseKappa, sliderValue);
    const heightPx = isOff ? 2 : Math.max(2, Math.round(effKappa * 72));
    const isHot = !isOff && effKappa >= 0.90;
    const hotClass = isHot ? " hot-bar" : "";
    const valDisplay = isOff ? "—" : effKappa.toFixed(2);
    const tooltipText = `${sec.name}: κ = ${valDisplay}${isHot ? " (Tier adjacency suspended)" : ""}`;

    return `
      <div class="worlds-bar-col" data-tooltip="${tooltipText}">
        <div class="worlds-bar-val">${valDisplay}</div>
        <div class="worlds-bar-visual-wrap">
          <div class="worlds-bar-visual${hotClass}" style="height:${heightPx}px;"></div>
        </div>
        <div class="worlds-bar-label">${escapeHtml(sec.name)}</div>
      </div>
    `;
  }).join("");

  return { barsHtml: bars, multiplierText: multText };
};

export const dimensionToCategoryKey = (dim) => {
  const normalized = String(dim || "").toLowerCase().trim();
  const map = {
    settings: "settings",
    lighting: "lighting",
    mechanisms: "mechanisms",
    costume: "costume",
    "practical effects": "practical_effects",
    practical_effects: "practical_effects"
  };
  return map[normalized] || normalized.replace(/\s+/g, "_");
};

export const renderPoolsHtml = (pools, borrowed, catalog = null) => {
  return pools.map((p, poolIdx) => {
    const isCostume = p.dimension === "Costume";
    const currentPoolCount = (isCostume && borrowed) ? 9 : p.pool;
    const isLow = currentPoolCount < p.need;
    const lowClass = isLow ? " pool-low" : "";
    const borrowedNote = (isCostume && borrowed) ? " (borrowed from Brutalist concrete)" : "";
    const borrowBtn = isLow
      ? `<button type="button" class="quiet worlds-borrow-btn" data-pool="${poolIdx}" data-tooltip="Temporarily borrow terms from the nearest semantic world">Borrow from nearest world</button>`
      : "";

    const chips = p.terms.map((term, termIdx) => {
      return `<button type="button" class="worlds-term-chip" data-pool="${poolIdx}" data-term="${termIdx}" data-state="0" data-tooltip="Click to cycle: Included → Pinned (must appear) → Excluded">${escapeHtml(term)}</button>`;
    }).join("");

    const catKey = dimensionToCategoryKey(p.dimension);
    const catalogItems = catalog?.base?.[catKey] || [];
    const existingTermsSet = new Set(p.terms.map(t => t.toLowerCase().trim()));
    const candidateTerms = catalogItems
      .filter(item => !existingTermsSet.has(item.toLowerCase().trim()))
      .sort((a, b) => a.localeCompare(b));

    const dropdownHtml = candidateTerms.length > 0
      ? `
        <select class="worlds-select-term-dropdown" data-pool="${poolIdx}" data-tooltip="Add a relevant built-in ${escapeHtml(p.dimension)} term to this pool" aria-label="Add built-in ${escapeHtml(p.dimension)} term">
          <option value="">+ Add from ${escapeHtml(p.dimension)} catalog (${candidateTerms.length})…</option>
          ${candidateTerms.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}
        </select>
      `
      : "";

    return `
      <div class="worlds-pool-dimension-row">
        <div class="worlds-pool-dim-header">
          <span class="worlds-pool-dim-title">${escapeHtml(p.dimension)}</span>
          <span class="sub${lowClass}">${currentPoolCount} in pool, about ${p.need} needed${borrowedNote}</span>
          ${borrowBtn}
        </div>
        <div class="worlds-chips-wrap">
          ${chips}
          <button type="button" class="worlds-term-chip worlds-add-term-btn" data-pool="${poolIdx}" data-tooltip="Type a custom keyword to add to this world pool">+ Add custom</button>
          ${dropdownHtml}
        </div>
      </div>
    `;
  }).join("");
};

export const compileWorldsToCustomVocab = (pools, mode, domContainer) => {
  if (mode === "off") return {};

  const dimToKey = {
    settings: "settings",
    lighting: "lighting",
    mechanisms: "mechanisms",
    costume: "costume",
    "practical effects": "practical_effects",
    practical_effects: "practical_effects"
  };

  const draft = {};

  pools.forEach((pool, poolIdx) => {
    const rawDim = pool.dimension.toLowerCase().trim();
    const key = dimToKey[rawDim] || rawDim.replace(/\s+/g, "_");

    const chips = domContainer ? [...domContainer.querySelectorAll(`.worlds-term-chip[data-pool="${poolIdx}"]`)] : [];
    const pinned = [];
    const excluded = [];
    const included = [];

    if (chips.length > 0) {
      chips.forEach((chip) => {
        if (chip.classList.contains("worlds-add-term-btn")) return;
        const term = chip.textContent.trim();
        const chipState = Number(chip.dataset.state || 0);
        if (chipState === 2) {
          excluded.push(term);
        } else if (chipState === 1) {
          pinned.push(term);
        } else {
          included.push(term);
        }
      });
    } else {
      included.push(...(pool.terms || []));
    }

    if (mode === "strict") {
      const activePool = [...pinned, ...included];
      if (activePool.length > 0) {
        draft[key] = {
          mode: "replace",
          add: activePool,
          exclude: excluded
        };
      }
    } else if (mode === "guided") {
      draft[key] = {
        mode: "append",
        add: [...pinned],
        exclude: excluded
      };
    }
  });

  return draft;
};

export function initVocabWorlds() {
  const container = $("#vocab-worlds-workspace");
  if (!container) return;

  let catalogCache = null;

  // Local state container for the interactive view, initialized from appState if present
  const state = {
    mode: appState.thematicWorlds?.mode || "guided",
    slider: typeof appState.thematicWorlds?.slider === "number" ? appState.thematicWorlds.slider : 50,
    borrowed: false,
    worlds: [...DEFAULT_WORLDS],
    sections: [...DEFAULT_SECTIONS],
    pools: Array.isArray(appState.thematicWorlds?.pools)
      ? JSON.parse(JSON.stringify(appState.thematicWorlds.pools))
      : JSON.parse(JSON.stringify(DEFAULT_POOLS))
  };

  // Eagerly pre-load catalog so category dropdowns populate immediately
  loadVocabularyCatalog()
    .then((cat) => {
      catalogCache = cat;
      updateView();
    })
    .catch(() => {});

  const promptInput = $("#worlds-prompt-input");
  if (promptInput) {
    if (appState.thematicWorlds?.prompt) {
      promptInput.value = appState.thematicWorlds.prompt;
    } else if (!promptInput.value.trim()) {
      const dirVal = document.querySelector("#video-form [name='direction']")?.value;
      if (dirVal) promptInput.value = dirVal.trim();
    }
  }

  const updateView = () => {
    const isOff = state.mode === "off";

    // Mode segmented buttons
    $$(".worlds-mode-btn").forEach(btn => {
      btn.classList.toggle("on", btn.dataset.mode === state.mode);
    });

    // Mode note
    const noteEl = $("#worlds-mode-note");
    if (noteEl) noteEl.textContent = MODE_DESCRIPTIONS[state.mode] || "";

    // Slider
    const sliderEl = $("#worlds-juxtaposition-slider");
    if (sliderEl) {
      sliderEl.value = String(state.slider);
      sliderEl.disabled = isOff;
    }

    // Clusters
    const clustersEl = $("#worlds-clusters-list");
    if (clustersEl) {
      clustersEl.innerHTML = renderWorldsHtml(state.worlds, isOff);
    }

    // Bars
    const barsContainer = $("#worlds-kappa-bars");
    const multSpan = $("#worlds-slider-multiplier");
    if (barsContainer && multSpan) {
      const { barsHtml, multiplierText } = renderBarsHtml(state.sections, state.slider, state.mode);
      barsContainer.innerHTML = barsHtml;
      multSpan.textContent = multiplierText;
    }

    // Pools
    const poolsContainer = $("#worlds-pools-list");
    if (poolsContainer) {
      poolsContainer.innerHTML = renderPoolsHtml(state.pools, state.borrowed, catalogCache);
    }

    // Footer summary pill
    const summaryStatus = $("#worlds-summary-status");
    if (summaryStatus) {
      if (state.mode === "off") {
        summaryStatus.textContent = "Mode: Off (Uniform visual vocabulary sampling)";
      } else {
        const modeLabel = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
        const activeCount = state.worlds.filter(w => w.active).length;
        const mult = (2 * (state.slider / 100)).toFixed(1);
        summaryStatus.textContent = `Mode: ${modeLabel} · ${activeCount} world(s) active · Juxtaposition x${mult}`;
      }
    }
  };

  // Wire mode switches, locks, chip cycling, and apply/reset actions
  container.addEventListener("click", event => {
    const modeBtn = event.target.closest(".worlds-mode-btn");
    if (modeBtn) {
      state.mode = modeBtn.dataset.mode;
      updateView();
      return;
    }

    const lockBtn = event.target.closest(".worlds-lock-btn");
    if (lockBtn) {
      const idx = Number(lockBtn.dataset.index);
      if (state.worlds[idx]) {
        state.worlds[idx].locked = !state.worlds[idx].locked;
        updateView();
      }
      return;
    }

    const borrowBtn = event.target.closest(".worlds-borrow-btn");
    if (borrowBtn) {
      state.borrowed = true;
      notice("Borrowed 5 complementary wardrobe terms from adjacent Brutalist world.");
      updateView();
      return;
    }

    const termChip = event.target.closest(".worlds-term-chip");
    if (termChip && !termChip.classList.contains("worlds-add-term-btn")) {
      const currentState = Number(termChip.dataset.state || 0);
      const nextState = (currentState + 1) % 3;
      termChip.dataset.state = String(nextState);
      termChip.classList.toggle("pin", nextState === 1);
      termChip.classList.toggle("ex", nextState === 2);
      const labels = ["Included (default)", "Pinned (forced into rotation)", "Excluded (blocked from rotation)"];
      termChip.title = labels[nextState];
      return;
    }

    const addBtn = event.target.closest(".worlds-add-term-btn");
    if (addBtn) {
      const poolIdx = Number(addBtn.dataset.pool);
      const input = prompt(`Enter a custom term to add to the ${state.pools[poolIdx].dimension} pool:`);
      if (input && input.trim()) {
        const cleaned = input.trim();
        state.pools[poolIdx].terms.push(cleaned);
        state.pools[poolIdx].pool += 1;
        updateView();
        notice(`Added "${cleaned}" to ${state.pools[poolIdx].dimension} pool.`);
      }
      return;
    }

    const applyBtn = event.target.closest("#worlds-apply-btn");
    if (applyBtn) {
      const promptText = ($("#worlds-prompt-input")?.value || "").trim();
      const activeWorlds = state.worlds.filter(w => w.active).map(w => w.name);

      if (state.mode === "off") {
        appState.thematicWorlds = null;
        updateVocabCustomBadge();
        scheduleSave();
        notice("Thematic Worlds set to Off. Visual vocabulary reverted to standard sampling.");
        const videoNavBtn = $(".nav[data-panel='video']");
        if (videoNavBtn) videoNavBtn.click();
        return;
      }

      const compiledDraft = compileWorldsToCustomVocab(state.pools, state.mode, $("#worlds-pools-list"));
      appState.currentCustomVocab = compiledDraft;
      appState.currentVocabRandomKey = "";
      appState.thematicWorlds = {
        prompt: promptText,
        mode: state.mode,
        slider: state.slider,
        activeWorlds,
        pools: state.pools
      };

      updateVocabCustomBadge();
      scheduleSave();

      const modeLabel = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
      const mult = (2 * (state.slider / 100)).toFixed(1);
      notice(`🧭 Applied Thematic Worlds (${modeLabel}, juxtaposition x${mult}) to active video.`);

      const videoNavBtn = $(".nav[data-panel='video']");
      if (videoNavBtn) videoNavBtn.click();
      return;
    }

    const resetBtn = event.target.closest("#worlds-reset-btn");
    if (resetBtn) {
      if (!window.confirm("Reset Thematic Worlds back to defaults?")) return;
      state.mode = "guided";
      state.slider = 50;
      state.borrowed = false;
      state.worlds = DEFAULT_WORLDS.map(w => ({ ...w }));
      state.sections = DEFAULT_SECTIONS.map(s => ({ ...s }));
      state.pools = JSON.parse(JSON.stringify(DEFAULT_POOLS));
      updateView();
      notice("Thematic Worlds reset back to defaults.");
      return;
    }
  });

  // Wire checkbox and dropdown changes
  container.addEventListener("change", event => {
    const check = event.target.closest(".worlds-cluster-check");
    if (check) {
      const idx = Number(check.dataset.index);
      if (state.worlds[idx]) {
        state.worlds[idx].active = check.checked;
        updateView();
      }
      return;
    }

    const select = event.target.closest(".worlds-select-term-dropdown");
    if (select && select.value) {
      const poolIdx = Number(select.dataset.pool);
      const chosen = select.value.trim();
      if (chosen && state.pools[poolIdx]) {
        if (!state.pools[poolIdx].terms.includes(chosen)) {
          state.pools[poolIdx].terms.push(chosen);
          state.pools[poolIdx].pool += 1;
          updateView();
          notice(`Added "${chosen}" to ${state.pools[poolIdx].dimension} pool.`);
        }
      }
      return;
    }
  });

  // Wire slider input
  const slider = $("#worlds-juxtaposition-slider");
  if (slider) {
    slider.oninput = () => {
      state.slider = Number(slider.value);
      const { barsHtml, multiplierText } = renderBarsHtml(state.sections, state.slider, state.mode);
      const barsContainer = $("#worlds-kappa-bars");
      const multSpan = $("#worlds-slider-multiplier");
      if (barsContainer) barsContainer.innerHTML = barsHtml;
      if (multSpan) multSpan.textContent = multiplierText;
    };
  }

  // Switch between Keyword Pools (12 Tables) and Thematic Worlds (Classification)
  const navToWorldsBtn = $("#vocab-view-worlds-btn");
  const tabKeywords = $("#tab-vocab-keywords");
  const tabWorlds = $("#tab-vocab-worlds");
  const keywordWorkspace = $("#vocab-category-workspace");
  const worldsWorkspace = $("#vocab-worlds-workspace");

  const showWorldsView = () => {
    if (keywordWorkspace) keywordWorkspace.hidden = true;
    if (worldsWorkspace) worldsWorkspace.hidden = false;
    if (tabKeywords) tabKeywords.classList.remove("active");
    if (tabWorlds) tabWorlds.classList.add("active");
    if (navToWorldsBtn) {
      navToWorldsBtn.textContent = "📋 Keyword Pools (12 Tables)";
      navToWorldsBtn.dataset.tooltip = "Switch back to the 12 keyword category tables";
    }
    const promptEl = $("#worlds-prompt-input");
    if (promptEl && !promptEl.value.trim()) {
      const dirVal = document.querySelector("#video-form [name='direction']")?.value;
      if (dirVal) promptEl.value = dirVal.trim();
    }
    if (!catalogCache) {
      loadVocabularyCatalog()
        .then((cat) => {
          catalogCache = cat;
          updateView();
        })
        .catch(() => {});
    }
    updateView();
  };

  const showKeywordView = () => {
    if (keywordWorkspace) keywordWorkspace.hidden = false;
    if (worldsWorkspace) worldsWorkspace.hidden = true;
    if (tabKeywords) tabKeywords.classList.add("active");
    if (tabWorlds) tabWorlds.classList.remove("active");
    if (navToWorldsBtn) {
      navToWorldsBtn.textContent = "🧭 Thematic Worlds & Classification";
      navToWorldsBtn.dataset.tooltip = "Switch to Thematic Worlds, semantic clustering, and juxtaposition control";
    }
  };

  if (navToWorldsBtn) {
    navToWorldsBtn.onclick = () => {
      if (worldsWorkspace && worldsWorkspace.hidden) {
        showWorldsView();
      } else {
        showKeywordView();
      }
    };
  }

  if (tabKeywords) tabKeywords.onclick = showKeywordView;
  if (tabWorlds) tabWorlds.onclick = showWorldsView;

  // Initialize view
  updateView();
}

