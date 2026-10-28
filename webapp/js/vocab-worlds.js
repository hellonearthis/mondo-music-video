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

export const THEMATIC_WORLDS_LIBRARY = [
  {
    name: "Bureaucratic / Carceral",
    keywords: [
      "clerk", "archive", "office", "government", "paperwork", "dossier", "cubicle", "desk",
      "stamp", "lanyard", "prison", "carceral", "cell", "fluorescent", "warden",
      "institutional", "records", "annex", "ledger", "typewriter", "linoleum", "official",
      "tribunal", "audit", "shift", "night-shift", "document", "filing", "cabinet", "pen", "stairwell"
    ],
    pools: {
      Settings: ["evidence locker", "sodium-lit stairwell", "records annex", "flooded basement", "linoleum corridor", "interrogation room", "card-catalogue annex"],
      Lighting: ["flickering fluorescent tube", "single desk lamp", "amber exit signs", "cold green cathode hum", "overhead strip glare"],
      Mechanisms: ["pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending", "manual typewriter carriage", "rotary dial spin"],
      Costume: ["grey wool cardigan", "laminated lanyard", "rumpled polyester tie", "oversized metal badge", "stiff cotton clerk coat"],
      "Practical Effects": ["drifting paper dust", "steam from a vent", "yellowing water stain", "buzzing ballast flicker", "coffee ring on parchment"]
    }
  },
  {
    name: "Brutalist Concrete",
    keywords: [
      "brutalist", "concrete", "monolith", "bunker", "aggregate", "gray", "grey", "shear wall",
      "geometric", "slab", "underpass", "pillar", "cold", "overpass", "fortress", "foundation",
      "viaduct", "gravel", "cement", "raw", "monolithic", "architecture", "monumental"
    ],
    pools: {
      Settings: ["monolithic atrium", "shear concrete underpass", "subterranean bunker", "recessed pedestrian tunnel", "brutalist civic plaza"],
      Lighting: ["stark raking sidelight", "deep geometric shadow", "cold halogen wash", "single slit aperture sunbeam"],
      Mechanisms: ["hydraulic blast door", "counterweight pulley", "heavy steel turnstile", "concrete core drill", "cable-stayed winch"],
      Costume: ["heavy charcoal trench", "rough wool greatcoat", "steel-toe boots", "utilitarian boiler suit", "dark canvas parka"],
      "Practical Effects": ["chalky concrete dust", "dripping condensation", "cold breath mist", "wind whipping fine gravel"]
    }
  },
  {
    name: "Industrial Decay",
    keywords: [
      "industrial", "decay", "factory", "rust", "abandoned", "iron", "boiler", "furnace",
      "scrap", "grease", "foundry", "smokestack", "pipe", "turbine", "corrugated", "toxic",
      "derelict", "mill", "smelting", "assembly", "soot", "machinery", "metal", "welding"
    ],
    pools: {
      Settings: ["abandoned assembly floor", "rusted catwalk", "inactive blast furnace", "scrap yard crane bay", "dripping steam conduit"],
      Lighting: ["flickering sodium vapor", "welding flash reflection", "amber hazard strobe", "dull rusted twilight"],
      Mechanisms: ["cracked flywheel spinning", "pneumatic piston hiss", "rusty chain hoist", "loose drive belt flapping"],
      Costume: ["grease-stained canvas overalls", "battered leather apron", "pitted welding goggles", "frayed cloth gloves"],
      "Practical Effects": ["curling iron filings", "oily puddle rainbow", "soot fallout", "high-pressure steam leak"]
    }
  },
  {
    name: "Maritime / Salt",
    keywords: [
      "maritime", "salt", "ocean", "sea", "wharf", "harbor", "brine", "trawler", "dock",
      "pier", "foghorn", "slicker", "fish", "tide", "boat", "ship", "wave", "coast",
      "coastal", "buoy", "barnacle", "hull", "seaweed", "gulls", "lighthouse", "water", "anchor"
    ],
    pools: {
      Settings: ["fog-choked timber pier", "rusted trawler deck", "fish cannery slipway", "salt-crusted watchtower", "low-tide mudflat"],
      Lighting: ["revolving lighthouse beam", "grey overcast sea mist", "lantern reflecting in wet planks", "sickly yellow deck floodlight"],
      Mechanisms: ["winch drum groaning", "rusty capstan turning", "foghorn bellows breathing", "bilge pump chugging"],
      Costume: ["yellow rubber slicker", "salt-stiffened denim", "heavy knit fisherman sweater", "sou'wester oilskin hat"],
      "Practical Effects": ["cold sea spray", "thick sea fog rolling", "dripping brine", "scattered wet fish scales"]
    }
  },
  {
    name: "Cyberpunk / High-Tech",
    keywords: [
      "cyberpunk", "cyber", "tech", "high-tech", "neon", "fiber", "optic", "server", "terminal",
      "circuit", "hacker", "glitch", "holographic", "data", "synthetic", "diode", "wire",
      "screen", "motherboard", "digital", "network", "drone", "interface", "virtual", "matrix", "code"
    ],
    pools: {
      Settings: ["crowded server bank", "neon-lit rainy alleyway", "subterranean cyber clinic", "cramped terminal booth", "optic cabling conduit"],
      Lighting: ["saturated magenta neon", "pulsing cyan diode glow", "scanning laser grid", "stuttering CRT monitor flicker"],
      Mechanisms: ["robotic actuator arm", "cooling fan spin-up", "optic cable rack patching", "motorized iris camera lens"],
      Costume: ["transparent vinyl coat", "modular techwear harness", "reflective visor", "fingerless grounding gloves"],
      "Practical Effects": ["circuit board smoke", "holographic glitch artifact", "fiber optic sparks", "pooling oily neon reflection"]
    }
  },
  {
    name: "Nocturnal Noir",
    keywords: [
      "noir", "detective", "night", "nocturnal", "rain", "wet", "asphalt", "trenchcoat",
      "alley", "venetian", "blinds", "shadow", "cigarette", "smoke", "jazz", "crime",
      "mystery", "streetlamp", "diner", "femme", "fatale", "fedora", "midnight", "whiskey"
    ],
    pools: {
      Settings: ["rain-slicked back alley", "venetian-blinded private office", "empty 2am diner", "fire escape landing", "telephone booth under streetlight"],
      Lighting: ["slanted venetian blind shadow", "single sodium streetlight", "glowing cigarette tip", "wet pavement neon bounce"],
      Mechanisms: ["rotary phone cradle click", "revolver cylinder spin", "ceiling fan turning slowly", "coin clinking in jukebox"],
      Costume: ["damp gabardine trenchcoat", "tilted felt fedora", "loosened silk tie", "leather shoulder holster"],
      "Practical Effects": ["curling cigarette smoke", "rain pouring off metal awning", "wet tire hiss", "windshield wiper drag"]
    }
  },
  {
    name: "Pastoral Nature",
    keywords: [
      "nature", "pastoral", "overgrowth", "forest", "woods", "moss", "meadow", "trees",
      "leaves", "pollen", "roots", "soil", "canopy", "flora", "garden", "organic",
      "wild", "fungal", "mushrooms", "thicket", "lichen", "grove", "sunbeam", "creek", "river", "botanical"
    ],
    pools: {
      Settings: ["moss-carpeted forest clearing", "ruined stone chapel overgrown with ivy", "sun-dappled creek bed", "ancient hollow oak grove"],
      Lighting: ["dappled canopy sunlight", "amber golden-hour slant", "glowing bioluminescent moss", "soft morning mist"],
      Mechanisms: ["creaking tree bough", "timber water wheel turning", "seed pod bursting", "deep root cracking stone"],
      Costume: ["hand-spun linen tunic", "dirt-stained hem", "woven willow crown", "unbleached cotton smock"],
      "Practical Effects": ["floating airborne pollen", "falling dried leaves", "rising soil dew", "spore cloud drifting"]
    }
  },
  {
    name: "Baroque / Theatrical",
    keywords: [
      "baroque", "theatrical", "theater", "theatre", "velvet", "curtain", "gold", "gilded",
      "masquerade", "chandelier", "opera", "stage", "footlights", "proscenium", "drama",
      "costume", "regal", "palace", "candle", "candelabra", "brocade", "orchestra", "mask"
    ],
    pools: {
      Settings: ["decaying opera house balcony", "gilded mirror gallery", "empty orchestra pit", "dusty backstage dressing room"],
      Lighting: ["gas footlights flickering", "multi-tiered crystal chandelier", "single amber spotlight cone", "flickering beeswax candles"],
      Mechanisms: ["counterweighted stage rope", "velvet grand drape rising", "trapdoor latch releasing", "mechanical music box cylinder"],
      Costume: ["heavy crimson velvet cape", "tarnished filigree mask", "gold brocade waistcoat", "ruffled lace collar"],
      "Practical Effects": ["billowing stage rosin dust", "drifting red rose petals", "melting wax drip", "floating theatrical haze"]
    }
  },
  {
    name: "Clinical / Medical",
    keywords: [
      "medical", "clinical", "hospital", "sterile", "surgical", "tile", "doctor", "nurse",
      "clinic", "syringe", "stainless", "examination", "patient", "antiseptic",
      "laboratory", "pharma", "specimen", "diagnosis", "white", "gloves", "quarantine", "scalpel"
    ],
    pools: {
      Settings: ["glazed white tile operating theater", "silent quarantine corridor", "specimen preservation vault", "sterile recovery ward"],
      Lighting: ["harsh shadowless surgical ring light", "pale blue inspection beam", "cold white fluorescent glare"],
      Mechanisms: ["centrifuge spinning", "pneumatic syringe valve", "stainless gurney caster rolling", "ECG tape feeding"],
      Costume: ["pale mint surgical scrubs", "translucent examination gloves", "starch-white lab coat", "disposable paper mask"],
      "Practical Effects": ["condensation inside oxygen tent", "dripping saline chamber", "antiseptic mist spray", "frost on cryogenic vial"]
    }
  },
  {
    name: "Cosmic / Void",
    keywords: [
      "cosmic", "void", "space", "star", "stars", "starfield", "obsidian", "gravity",
      "zero-g", "vacuum", "celestial", "nebula", "observatory", "radio", "dish", "meteor",
      "dust", "satellite", "astronaut", "orbit", "planetary", "black hole", "galaxy", "deep space"
    ],
    pools: {
      Settings: ["deep space observation cupola", "radio telescope dish rim", "obsidian asteroid crater", "pressurized airlock chamber"],
      Lighting: ["distant blue starlight pinpricks", "earth-rise specular rim light", "cold solar flare glare", "monochrome instrument backlight"],
      Mechanisms: ["airlock decompression cycle", "reaction control thruster puff", "gyroscope spinning in gimbal", "solar array unrolling"],
      Costume: ["multilayer EVA spacesuit", "gold-tinted reflective helmet visor", "pressurized tether umbilical", "quilted thermal liner"],
      "Practical Effects": ["floating weightless droplets", "solar wind particle trails", "micro-meteorite impact sparkle", "ice crystals venting"]
    }
  }
];

const PROMPT_STOPWORDS = new Set([
  "the", "and", "that", "this", "with", "from", "for", "through", "into", "over",
  "under", "about", "your", "they", "them", "their", "have", "been", "were",
  "will", "would", "could", "should", "some", "what", "when", "where", "which"
]);

const normalizeRawScore = (rawScore, maxRaw, idx) => {
  if (maxRaw <= 0) {
    return Math.max(0.20, Number((0.75 - idx * 0.12).toFixed(2)));
  }
  const ratio = rawScore / maxRaw;
  if (ratio > 0.8) return 0.80 + (ratio - 0.8) * 0.75;
  if (ratio > 0.4) return 0.55 + (ratio - 0.4) * 0.625;
  if (ratio > 0) return 0.30 + ratio * 0.625;
  return Math.max(0.15, 0.28 - idx * 0.03);
};

const computeWorldRawScore = (world, rawText, meaningfulTokens) => {
  const worldKeywords = (world.keywords || []).map(k => k.toLowerCase());
  const worldNameLower = world.name.toLowerCase();

  // 1. Prompt string contains whole keywords/phrases
  const keywordMatchScore = worldKeywords.reduce(
    (sum, kw) => sum + (rawText.includes(kw) ? ((kw.includes(" ") || kw.includes("-")) ? 4.5 : 3.0) : 0),
    0
  );

  // 2. Token overlap and prefix matching
  const tokenMatchScore = meaningfulTokens.reduce((sum, tok) => {
    const nameBonus = worldNameLower.includes(tok) ? 2.5 : 0;
    const exactMatch = worldKeywords.some(kw => kw === tok);
    const prefixMatch = !exactMatch && tok.length >= 4 && worldKeywords.some(kw => kw.startsWith(tok) || tok.startsWith(kw));
    const kwBonus = exactMatch ? 2.0 : prefixMatch ? 1.0 : 0;
    return sum + nameBonus + kwBonus;
  }, 0);

  // 3. Signature pools check
  const poolMatchScore = Object.values(world.pools || {})
    .flat()
    .reduce((sum, term) => sum + (rawText.includes(term.toLowerCase()) ? 2.0 : 0), 0);

  return keywordMatchScore + tokenMatchScore + poolMatchScore;
};

export const scorePromptAgainstWorlds = (promptText, currentWorlds = [], library = THEMATIC_WORLDS_LIBRARY) => {
  const rawText = String(promptText || "").toLowerCase().trim();
  if (!rawText) {
    return library.slice(0, 4).map((w, i) => {
      const existing = currentWorlds.find(cw => cw.name === w.name);
      return {
        name: w.name,
        score: existing ? existing.score : Number((0.75 - i * 0.15).toFixed(2)),
        active: existing ? existing.active : i < 2,
        locked: existing ? existing.locked : false
      };
    });
  }

  const meaningfulTokens = rawText
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter(t => t.length > 2 && !PROMPT_STOPWORDS.has(t));

  const scored = library
    .map(world => ({
      world,
      rawScore: computeWorldRawScore(world, rawText, meaningfulTokens)
    }))
    .toSorted((a, b) => b.rawScore - a.rawScore);

  const maxRaw = Math.max(...scored.map(s => s.rawScore), 0);

  const ranked = scored.map((item, idx) => {
    const normalizedScore = normalizeRawScore(item.rawScore, maxRaw, idx);
    const finalScore = Number(Math.min(0.98, Math.max(0.12, normalizedScore)).toFixed(2));
    const existing = currentWorlds.find(cw => cw.name === item.world.name);

    return {
      name: item.world.name,
      score: finalScore,
      active: existing?.locked ? existing.active : idx < 2,
      locked: existing ? existing.locked : false
    };
  });

  const selectedFromRanked = ranked.reduce((acc, item) => (
    acc.length < 4 || item.locked
      ? [...acc, { name: item.name, score: item.score, active: item.active, locked: item.locked }]
      : acc
  ), []);

  const addedNames = new Set(selectedFromRanked.map(item => item.name));
  const lockedWorlds = currentWorlds.filter(w => w.locked);
  const missingLocked = lockedWorlds
    .filter(locked => !addedNames.has(locked.name))
    .map(locked => ({
      name: locked.name,
      score: locked.score || 0.50,
      active: locked.active,
      locked: true
    }));

  return [...selectedFromRanked, ...missingLocked]
    .toSorted((a, b) => b.score - a.score)
    .slice(0, Math.max(4, lockedWorlds.length));
};

const POOL_DIMENSIONS = [
  { name: "Settings", defaultNeed: 9 },
  { name: "Lighting", defaultNeed: 6 },
  { name: "Mechanisms", defaultNeed: 10 },
  { name: "Costume", defaultNeed: 6 },
  { name: "Practical Effects", defaultNeed: 5 }
];

const uniqueCaseInsensitive = (terms) =>
  terms.reduce(
    (acc, term) => (
      acc.some(existing => existing.toLowerCase() === term.toLowerCase())
        ? acc
        : [...acc, term]
    ),
    []
  );

export const compilePoolsFromActiveWorlds = (activeWorldNames = [], currentPools = [], library = THEMATIC_WORLDS_LIBRARY) => {
  const activeSet = new Set(activeWorldNames);
  const activeWorlds = library.filter(w => activeSet.has(w.name));

  if (activeWorlds.length === 0) {
    return (currentPools.length ? currentPools : DEFAULT_POOLS).map(p => ({
      ...p,
      terms: [...p.terms],
      chipStates: p.chipStates ? { ...p.chipStates } : {}
    }));
  }

  return POOL_DIMENSIONS.map(dim => {
    const existingPool = currentPools.find(p => p.dimension.toLowerCase() === dim.name.toLowerCase());
    const existingTerms = existingPool ? existingPool.terms : [];
    const existingChipStates = existingPool?.chipStates ? { ...existingPool.chipStates } : {};
    const need = existingPool ? existingPool.need : dim.defaultNeed;

    const worldTerms = activeWorlds
      .flatMap(world => world.pools?.[dim.name] || [])
      .reduce((acc, term) => (acc.includes(term) ? acc : [...acc, term]), []);

    const mergedTerms = uniqueCaseInsensitive([...worldTerms, ...existingTerms]);

    return {
      dimension: dim.name,
      pool: mergedTerms.length,
      need,
      terms: mergedTerms,
      baseTermCount: worldTerms.length,
      chipStates: existingChipStates
    };
  });
};

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
    baseTermCount: 4,
    terms: ["evidence locker", "sodium-lit stairwell", "records annex", "flooded basement"]
  },
  {
    dimension: "Lighting",
    pool: 11,
    need: 6,
    baseTermCount: 3,
    terms: ["flickering fluorescent tube", "single desk lamp", "amber exit signs"]
  },
  {
    dimension: "Mechanisms",
    pool: 17,
    need: 10,
    baseTermCount: 3,
    terms: ["pneumatic tube dispatch", "card-catalogue drawers sliding", "stamp descending"]
  },
  {
    dimension: "Costume",
    pool: 4,
    need: 6,
    baseTermCount: 2,
    terms: ["grey wool cardigan", "laminated lanyard"]
  },
  {
    dimension: "Practical Effects",
    pool: 9,
    need: 5,
    baseTermCount: 2,
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

export const computePoolCounts = (pool, borrowed = false) => {
  const terms = pool.terms || [];
  const chipStates = pool.chipStates || {};
  const excludedCount = terms.reduce(
    (acc, term) => acc + (Number(chipStates[term] || 0) === 2 ? 1 : 0),
    0
  );
  const pinnedCount = terms.reduce(
    (acc, term) => acc + (Number(chipStates[term] || 0) === 1 ? 1 : 0),
    0
  );
  const activeTermCount = Math.max(0, terms.length - excludedCount);
  const isCostume = pool.dimension === "Costume";
  const baseCount = typeof pool.pool === "number" ? Math.max(pool.pool, terms.length) : terms.length;
  const currentPoolCount = Math.max(
    0,
    ((isCostume && borrowed) ? Math.max(9, baseCount) : baseCount) - excludedCount
  );
  const need = Number(pool.need || 0);
  const baseTermCount = typeof pool.baseTermCount === "number"
    ? pool.baseTermCount
    : terms.length;
  const selectedTowardsNeed = terms.reduce((acc, term, idx) => {
    const state = Number(chipStates[term] || 0);
    if (state === 2) return acc;
    if (state === 1 || idx >= baseTermCount) return acc + 1;
    return acc;
  }, 0);
  const remainingNeeded = Math.max(0, need - selectedTowardsNeed);
  return {
    currentPoolCount,
    activeTermCount,
    pinnedCount,
    selectedTowardsNeed,
    excludedCount,
    need,
    remainingNeeded,
    isLow: currentPoolCount < need && remainingNeeded > 0
  };
};

export const formatPoolStatusText = (pool, borrowed = false) => {
  const { currentPoolCount, selectedTowardsNeed, need, remainingNeeded } = computePoolCounts(pool, borrowed);
  const isCostume = pool.dimension === "Costume";
  const borrowedNote = (isCostume && borrowed) ? " (borrowed from Brutalist concrete)" : "";
  if (selectedTowardsNeed > 0) {
    if (remainingNeeded === 0) {
      return `${currentPoolCount} in pool, 0 needed${borrowedNote}`;
    }
    return `${currentPoolCount} in pool, about ${remainingNeeded} needed${borrowedNote}`;
  }
  return `${currentPoolCount} in pool, about ${need} needed${borrowedNote}`;
};

export const renderPoolsHtml = (pools, borrowed, catalog = null) => {
  return pools.map((p, poolIdx) => {
    const { isLow } = computePoolCounts(p, borrowed);
    const lowClass = isLow ? " pool-low" : "";
    const statusText = formatPoolStatusText(p, borrowed);
    const borrowBtn = isLow
      ? `<button type="button" class="quiet worlds-borrow-btn" data-pool="${poolIdx}" data-tooltip="Temporarily borrow terms from the nearest semantic world">Borrow from nearest world</button>`
      : "";

    const chips = p.terms.map((term, termIdx) => {
      const chipState = Number(p.chipStates?.[term] || 0);
      const stateClass = chipState === 1 ? " pin" : chipState === 2 ? " ex" : "";
      return `<button type="button" class="worlds-term-chip${stateClass}" data-pool="${poolIdx}" data-term="${termIdx}" data-state="${chipState}">${escapeHtml(term)}</button>`;
    }).join("");

    const catKey = dimensionToCategoryKey(p.dimension);
    const catalogItems = catalog?.base?.[catKey] || [];
    const existingTermsSet = new Set(p.terms.map(t => t.toLowerCase().trim()));
    const candidateTerms = catalogItems
      .filter(item => !existingTermsSet.has(item.toLowerCase().trim()))
      .toSorted((a, b) => a.localeCompare(b));

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
          <span class="sub${lowClass}" data-pool-status="${poolIdx}">${statusText}</span>
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

const partitionPoolTerms = (pool, poolIdx, domContainer) => {
  const chips = domContainer
    ? [...domContainer.querySelectorAll(`.worlds-term-chip[data-pool="${poolIdx}"]`)]
        .filter(chip => !chip.classList.contains("worlds-add-term-btn"))
    : [];

  const entries = chips.length > 0
    ? chips.map(chip => ({
        term: chip.textContent.trim(),
        chipState: Number(chip.dataset.state || 0)
      }))
    : (pool.terms || []).map(term => ({
        term,
        chipState: Number(pool.chipStates?.[term] || 0)
      }));

  return entries.reduce(
    (acc, { term, chipState }) => {
      if (chipState === 2) return { ...acc, excluded: [...acc.excluded, term] };
      if (chipState === 1) return { ...acc, pinned: [...acc.pinned, term] };
      return { ...acc, included: [...acc.included, term] };
    },
    { pinned: [], excluded: [], included: [] }
  );
};

export const compileWorldsToCustomVocab = (pools, mode, domContainer = null) => {
  if (mode === "off") return {};

  return pools.reduce((draft, pool, poolIdx) => {
    const key = dimensionToCategoryKey(pool.dimension);
    const { pinned, excluded, included } = partitionPoolTerms(pool, poolIdx, domContainer);

    if (mode === "strict") {
      const activePool = [...pinned, ...included];
      return activePool.length > 0
        ? { ...draft, [key]: { mode: "replace", add: activePool, exclude: excluded } }
        : draft;
    }

    if (mode === "guided") {
      return {
        ...draft,
        [key]: { mode: "append", add: [...pinned], exclude: excluded }
      };
    }

    return draft;
  }, {});
};

export const toggleWorldLock = (worlds, index) =>
  worlds.map((world, idx) => (idx === index ? { ...world, locked: !world.locked } : world));

export const setWorldActive = (worlds, index, active) =>
  worlds.map((world, idx) => (idx === index ? { ...world, active: Boolean(active) } : world));

export const setPoolChipState = (pools, poolIdx, term, nextState) =>
  pools.map((pool, idx) => {
    if (idx !== poolIdx) return pool;
    const currentChipStates = { ...(pool.chipStates || {}) };
    if (nextState === 0) {
      const { [term]: _, ...remainingStates } = currentChipStates;
      return { ...pool, chipStates: remainingStates };
    }
    return { ...pool, chipStates: { ...currentChipStates, [term]: nextState } };
  });

export const addTermToPool = (pools, poolIdx, rawTerm) => {
  const cleaned = String(rawTerm || "").trim();
  if (!cleaned) return pools;
  return pools.map((pool, idx) => {
    if (idx !== poolIdx || pool.terms.includes(cleaned)) return pool;
    return {
      ...pool,
      terms: [...pool.terms, cleaned],
      pool: (typeof pool.pool === "number" ? pool.pool : pool.terms.length) + 1
    };
  });
};

const clonePools = (pools) =>
  pools.map(pool => ({
    ...pool,
    terms: [...(pool.terms || [])],
    chipStates: pool.chipStates ? { ...pool.chipStates } : {}
  }));

export function initVocabWorlds() {
  const container = $("#vocab-worlds-workspace");
  if (!container) return;

  let catalogCache = null;

  // Local state container for the interactive view, initialized from appState if present
  const state = {
    mode: appState.thematicWorlds?.mode || "guided",
    slider: typeof appState.thematicWorlds?.slider === "number" ? appState.thematicWorlds.slider : 50,
    borrowed: false,
    worlds: DEFAULT_WORLDS.map(w => ({ ...w })),
    sections: DEFAULT_SECTIONS.map(s => ({ ...s })),
    pools: clonePools(
      Array.isArray(appState.thematicWorlds?.pools) ? appState.thematicWorlds.pools : DEFAULT_POOLS
    )
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
    promptInput.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        const btn = $("#worlds-process-prompt-btn");
        if (btn) btn.click();
      }
    });
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
    const processBtn = event.target.closest("#worlds-process-prompt-btn");
    if (processBtn) {
      const promptEl = $("#worlds-prompt-input");
      const text = (promptEl?.value || "").trim();
      if (!text) {
        notice("Please enter a song premise or thematic direction to analyze.");
        if (promptEl) promptEl.focus();
        return;
      }

      const scoredWorlds = scorePromptAgainstWorlds(text, state.worlds, THEMATIC_WORLDS_LIBRARY);
      state.worlds = scoredWorlds;

      const activeNames = scoredWorlds.filter(w => w.active).map(w => w.name);
      state.pools = compilePoolsFromActiveWorlds(activeNames, state.pools, THEMATIC_WORLDS_LIBRARY);

      updateView();

      const topWorld = scoredWorlds[0];
      const secondWorld = scoredWorlds[1];
      if (topWorld && secondWorld) {
        notice(`⚡ Analyzed prompt: Matched "${topWorld.name}" (${topWorld.score.toFixed(2)}) & "${secondWorld.name}" (${secondWorld.score.toFixed(2)}).`);
      } else if (topWorld) {
        notice(`⚡ Analyzed prompt: Matched "${topWorld.name}" (${topWorld.score.toFixed(2)}).`);
      }
      return;
    }

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
        state.worlds = toggleWorldLock(state.worlds, idx);
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
      const poolIdx = Number(termChip.dataset.pool);
      const term = termChip.textContent.trim();
      const targetPool = state.pools[poolIdx];
      if (targetPool && term) {
        state.pools = setPoolChipState(state.pools, poolIdx, term, nextState);
        const updatedPool = state.pools[poolIdx];
        const statusEl = container.querySelector(`[data-pool-status="${poolIdx}"]`);
        if (statusEl && updatedPool) {
          const { isLow } = computePoolCounts(updatedPool, state.borrowed);
          statusEl.textContent = formatPoolStatusText(updatedPool, state.borrowed);
          statusEl.classList.toggle("pool-low", isLow);
        }
      }
      return;
    }

    const addBtn = event.target.closest(".worlds-add-term-btn");
    if (addBtn) {
      const poolIdx = Number(addBtn.dataset.pool);
      const targetPool = state.pools[poolIdx];
      const input = targetPool ? prompt(`Enter a custom term to add to the ${targetPool.dimension} pool:`) : "";
      if (input && input.trim() && targetPool) {
        const cleaned = input.trim();
        state.pools = addTermToPool(state.pools, poolIdx, cleaned);
        updateView();
        notice(`Added "${cleaned}" to ${targetPool.dimension} pool.`);
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
      state.pools = clonePools(DEFAULT_POOLS);
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
        state.worlds = setWorldActive(state.worlds, idx, check.checked);
        const activeNames = state.worlds.filter(w => w.active).map(w => w.name);
        state.pools = compilePoolsFromActiveWorlds(activeNames, state.pools, THEMATIC_WORLDS_LIBRARY);
        updateView();
      }
      return;
    }

    const select = event.target.closest(".worlds-select-term-dropdown");
    if (select && select.value) {
      const poolIdx = Number(select.dataset.pool);
      const chosen = select.value.trim();
      const targetPool = state.pools[poolIdx];
      if (chosen && targetPool && !targetPool.terms.includes(chosen)) {
        state.pools = addTermToPool(state.pools, poolIdx, chosen);
        updateView();
        notice(`Added "${chosen}" to ${targetPool.dimension} pool.`);
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

