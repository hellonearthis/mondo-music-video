// Pre-generation score editor: waveform, detected beats, sections and planned cuts.
// Edits become `score_edits` on the preview request; nothing is generated or charged here.

import { $, api, json, option, state, text } from "./core.js";
import WaveSurfer from "../vendor/wavesurfer/wavesurfer.esm.js";
import RegionsPlugin from "../vendor/wavesurfer/plugins/regions.esm.js";

const LABELS = ["low", "mid", "high", "peak"];
const LABEL_HELP = {
  low: "Quiet: slow, observational passages",
  mid: "Medium energy",
  high: "Energetic: faster cutting",
  peak: "The loudest moments: the most intense montage"
};
const REGION_COLORS = {
  low: "rgba(70, 120, 160, 0.28)",
  mid: "rgba(110, 150, 90, 0.28)",
  high: "rgba(210, 150, 40, 0.30)",
  peak: "rgba(200, 60, 60, 0.32)"
};
const DRIVERS = [
  ["mix", "Whole mix (default)", "Follow the loudness of the full song"],
  ["drums", "Drums", "Energy follows the drum stem"],
  ["bass", "Bass", "Energy follows the bass stem"],
  ["vocals", "Vocals", "Energy follows the voice"],
  ["other", "Other (guitars, keys, everything else)", "Energy follows the remaining instruments"],
  ["guitar", "Guitar (6-stem model)", "Needs the larger 6-stem model"],
  ["piano", "Piano (6-stem model)", "Needs the larger 6-stem model; piano separation is the least reliable"]
];
const SIX_STEM = new Set(["guitar", "piano"]);
const MODELS = {
  htdemucs: { label: "standard 4-stem", size: "about 81 MB" },
  htdemucs_ft: { label: "high-quality 4-stem", size: "about 324 MB" },
  htdemucs_6s: { label: "6-stem", size: "about 53 MB" }
};
const usesQuality = driver => driver !== "mix" && !SIX_STEM.has(driver);
const modelFor = (driver, quality) => SIX_STEM.has(driver) ? "htdemucs_6s" : quality === "high" ? "htdemucs_ft" : "htdemucs";
const peaksCache = new Map();
let active = null;

export function disposeScoreEditor() {
  if (active) active.destroy();
  active = null;
}

export function emptyEdits() {
  return { bar_one_beat: null, beat_nudge_ms: 0, muted_beats: [], sections: [] };
}

function cleanEdits(edits) {
  return {
    bar_one_beat: edits.bar_one_beat,
    beat_nudge_ms: edits.beat_nudge_ms,
    muted_beats: [...edits.muted_beats].sort((a, b) => a - b),
    sections: edits.sections.map(item => ({ start: item.start, label: item.label }))
  };
}

async function loadPeaks(song) {
  if (!peaksCache.has(song)) {
    const response = await fetch("/api/waveform?song=" + encodeURIComponent(song));
    if (!response.ok) throw new Error("The waveform could not be drawn");
    peaksCache.set(song, await response.json());
  }
  return peaksCache.get(song);
}

export async function mountScoreEditor(host, request, quote, { onReplan, onDirty }) {
  disposeScoreEditor();
  host.replaceChildren();
  const detected = quote.detected;
  if (request.kind !== "video" || !detected || !request.song) {
    host.hidden = true;
    return;
  }
  host.hidden = false;

  const applied = cleanEdits({ ...emptyEdits(), ...(request.score_edits || {}) });
  const appliedDriver = request.analysis_driver || "mix";
  let driver = appliedDriver;
  const appliedQuality = request.stem_quality || "standard";
  let quality = appliedQuality;
  let stems = null;
  const edits = cleanEdits(applied);
  const muted = new Set(edits.muted_beats);
  const duration = detected.duration;
  const bpb = detected.beats_per_bar || 4;
  let sections = (edits.sections.length ? edits.sections : detected.sections).map(item => ({ start: item.start, label: item.label }));
  let selected = null;
  let ws = null, regions = null;
  let drawFrame = 0;

  const box = text("details", "", "score-editor-box");
  box.open = true;
  box.append(text("summary", "Edit the song's score before generating", "", "Fix the beat grid and sections, then re-plan. Free: nothing is generated."));
  host.append(box);
  box.append(text("p", "Mondo listened to your song and planned the cuts below. If the tracker guessed wrong, fix it here "
    + "and press Re-plan. This costs nothing; nothing is generated until you start production.", "muted"));

  const stage = document.createElement("div");
  stage.className = "se-wave";
  const strip = document.createElement("canvas");
  strip.className = "se-strip";
  strip.tabIndex = 0;
  strip.setAttribute("role", "application");
  strip.setAttribute("aria-label", "Beat grid. Left and right arrows select a beat, M mutes or unmutes it, B makes it the first beat of a bar, Space plays or pauses.");
  const caption = text("p", "", "score-caption");
  caption.setAttribute("aria-live", "polite");
  const legend = text("div", "", "score-legend");
  for (const [cls, label] of [["score-beats", "beats"], ["score-energy", "energy"], ["score-cuts", "planned cuts"]]) {
    legend.append(text("span", label, "score-key " + cls));
  }
  legend.append(text("span", "tall ticks are the first beat of each bar · crossed ticks are muted", "muted"));

  const bar = text("div", "", "se-toolbar");
  const play = text("button", "Play", "secondary", "Play or pause the song from the cursor");
  play.type = "button";
  const clock = text("span", "0:00 / 0:00", "se-clock");
  const nudge = document.createElement("input");
  nudge.type = "range";
  nudge.min = "-250";
  nudge.max = "250";
  nudge.step = "10";
  nudge.value = String(edits.beat_nudge_ms);
  nudge.setAttribute("aria-label", "Shift the whole beat grid, milliseconds");
  const nudgeLabel = text("span", "", "se-nudge-label");
  const nudgeWrap = text("label", "Shift beats ", "se-nudge", "Slide every beat earlier or later if the grid sits slightly off the music");
  nudgeWrap.append(nudge, nudgeLabel);
  const barOne = text("button", "Bar 1 starts at this beat", "secondary", "Make the selected beat the first beat of a bar; the grid of bars follows from it");
  barOne.type = "button";
  const muteBtn = text("button", "Mute / unmute beat", "secondary", "A muted beat is not used for cuts, but still counts in the bar");
  muteBtn.type = "button";
  const resetBtn = text("button", "Reset edits", "quiet", "Go back to the detected beats and sections");
  resetBtn.type = "button";
  const replanBtn = text("button", "Re-plan with edits", "primary", "Rebuild the cuts and cost estimate from your edits (free)");
  replanBtn.type = "button";
  bar.append(play, clock, nudgeWrap, barOne, muteBtn, resetBtn, replanBtn);
  const status = text("p", "", "se-status");
  status.setAttribute("aria-live", "polite");

  const driverRow = text("div", "", "se-driver");
  const driverSelect = document.createElement("select");
  driverSelect.setAttribute("aria-label", "Which part of the song drives the video's energy");
  DRIVERS.forEach(([value, label, help]) => driverSelect.append(option(value, label, help)));
  driverSelect.value = driver;
  const qualitySelect = document.createElement("select");
  qualitySelect.setAttribute("aria-label", "Stem separation quality");
  qualitySelect.append(option("standard", "Standard (default)", "The standard model: fast, good for most songs"),
    option("high", "High (slower, cleaner on some songs)", "The fine-tuned model: about 2 to 3 times slower, sometimes leaks less of other instruments"));
  qualitySelect.value = quality;
  const qualityLabel = text("label", "Stem quality ", "se-driver-label", "High uses a fine-tuned model that is slower and, on some songs, picks up fewer stray sounds in a stem.");
  qualityLabel.append(qualitySelect);
  const driverLabel = text("label", "Follow this part of the song ", "se-driver-label",
    "The video's energy, and so its cutting speed and montage style, follows the part you pick. The beat grid still comes from the whole song.");
  driverLabel.append(driverSelect);
  const driverNote = text("p", "", "muted se-driver-note");
  const driverSetup = text("div", "", "se-driver-setup");
  driverRow.append(driverLabel, qualityLabel, driverNote, driverSetup);

  const lipOn = request.mouth_mode === "lip_sync";
  const captionsOn = ["sidecar", "burned"].includes(request.captions?.mode);
  const linesOn = lipOn || captionsOn;           // the lyric lines serve lip sync and captions; the singer and passage parts are lip sync only
  let lines = (request.lyric_lines || []).map(item => ({ start: item.start, end: item.end, text: item.text, ...(item.timing ? { timing: item.timing } : {}), ...(item.section ? { section: item.section } : {}) }));
  let singers = [...(request.singers || [])];
  const appliedLines = JSON.stringify(lines), appliedSingers = JSON.stringify(singers);
  const lipBox = text("div", "", "se-lip");
  lipBox.hidden = !linesOn;
  const singerSelect = document.createElement("select");
  singerSelect.setAttribute("aria-label", "Main singer");
  const singerLabel = text("label", "Main singer ", "se-driver-label",
    "The actor who sings the lyric lines. Left on 'choose for me', the program picks one with your seed.");
  singerLabel.append(singerSelect);
  singerLabel.hidden = !lipOn;
  const voiceNote = text("p", "", "muted se-lip-note");
  const lineList = text("div", "", "se-lines");
  const lineBar = text("div", "", "se-section-bar");
  const addLine = text("button", "Add line at cursor", "secondary", "Add a lyric line starting where the playback cursor is");
  addLine.type = "button";
  lineBar.append(addLine, text("span", "Give each sung line its start, end and words." + (lipOn ? " Passages with at least about three quarters of a second of singing will sing; the others stay sealed." : " Press Re-plan to caption these lines."), "muted"));
  const lipSummary = text("div", "", "se-lip-summary");
  const detectBar = text("div", "", "se-section-bar");
  const speechSelect = document.createElement("select");
  speechSelect.setAttribute("aria-label", "Speech model for lyrics detection");
  const detectBtn = text("button", "Detect lyrics", "secondary", "Listen to the song (the vocals, if the stems add-on is ready) and fill in the lines. Free, and you can edit every line.");
  detectBtn.type = "button";
  detectBar.append(detectBtn, speechSelect);
  const detectNote = text("p", "", "muted se-lip-note");
  const speechSetup = text("div", "", "se-lip-setup");
  const pasteBox = document.createElement("textarea");
  pasteBox.rows = 4;
  pasteBox.placeholder = "Or paste the lyrics here, one line per row, and time them against the song";
  pasteBox.setAttribute("aria-label", "Pasted lyrics");
  const pasteBtn = text("button", "Time pasted lyrics", "secondary", "Match your words to the song to find when each line is sung (run Detect lyrics first)");
  pasteBtn.type = "button";
  lipBox.append(text("h3", lipOn ? "Lyrics and singing" : "Lyrics for captions"), singerLabel, voiceNote, detectBar, detectNote, speechSetup, pasteBox, pasteBtn,
    lineList, lineBar, lipSummary);

  const sectionHead = text("h3", "Sections");
  sectionHead.title = "Sections decide the montage style. Drag a section's edge on the waveform to move it.";
  const sectionList = text("div", "", "se-sections");
  const sectionBar = text("div", "", "se-section-bar");
  const splitBtn = text("button", "Split section at cursor", "secondary", "Start a new section where the cursor is");
  splitBtn.type = "button";
  sectionBar.append(splitBtn, text("span", "Drag a section's edge on the waveform to move it.", "muted"));

  box.append(stage, strip, caption, legend, bar, status, driverRow, lipBox, sectionHead, sectionList, sectionBar);

  const x = time => time / Math.max(duration, 0.001) * strip.clientWidth;
  const beatTime = index => detected.beats[index].time + edits.beat_nudge_ms / 1000;
  const isDownbeat = index => edits.bar_one_beat === null
    ? detected.beats[index].downbeat : index % bpb === edits.bar_one_beat % bpb;
  const same = (a, b) => JSON.stringify(cleanEdits(a)) === JSON.stringify(cleanEdits(b));
  const fmt = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

  function collectEdits() {
    edits.muted_beats = [...muted];
    const untouched = JSON.stringify(sections) === JSON.stringify(detected.sections.map(s => ({ start: s.start, label: s.label })));
    edits.sections = untouched ? [] : sections.map(item => ({ start: item.start, label: item.label }));
    return cleanEdits(edits);
  }

  const linesValid = () => lines.every(item => Number.isFinite(item.start) && Number.isFinite(item.end)
    && item.start >= 0 && item.end > item.start && item.text.trim().length > 0);

  function sectionsValid() {
    return sections.every((item, i) => (i === 0 ? item.start === 0 : item.start > sections[i - 1].start + 0.999)
      && (sections[i + 1] ? sections[i + 1].start : duration) - item.start >= 0.999);
  }

  function refreshStatus() {
    const current = collectEdits();
    const lipDirty = linesOn && (JSON.stringify(lines) !== appliedLines || JSON.stringify(singers) !== appliedSingers);
    const dirty = !same(current, applied) || driver !== appliedDriver || (usesQuality(driver) && quality !== appliedQuality) || lipDirty;
    const valid = sectionsValid() && (!linesOn || linesValid());
    barOne.disabled = selected === null;
    muteBtn.disabled = selected === null;
    replanBtn.disabled = !dirty || !valid;
    replanBtn.classList.toggle("attention", dirty && valid);
    status.textContent = !valid ? (linesOn && !linesValid() ? "Each lyric line needs words and an end after its start." : "Each section must be at least 1 second long.")
      : dirty ? "You have edits that are not planned yet. Press Re-plan to update the cuts and the cost before you start."
        : "The plan matches what you see.";
    nudgeLabel.textContent = ` ${edits.beat_nudge_ms > 0 ? "+" : ""}${edits.beat_nudge_ms} ms`;
    onDirty(dirty);
    schedule();
  }

  function describe() {
    if (selected === null) return `${Math.round(detected.tempo_bpm)} BPM, ${bpb} beats to a bar. Click a beat to select it.`;
    const time = beatTime(selected);
    const bar = Math.floor(selected / bpb) + 1;
    return `Beat ${selected + 1} at ${time.toFixed(2)} s${isDownbeat(selected) ? " · first beat of a bar" : ""}`
      + `${muted.has(selected) ? " · muted" : ""}. About bar ${bar}.`;
  }

  function colors() {
    const style = getComputedStyle(box);
    const value = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return { ink: value("--ink", "#222"), muted: value("--muted", "#777"), line: value("--line", "#ccc"),
      accent: value("--score-accent", "#c2711d"), paper: value("--paper", "#f1f3ec") };
  }

  function draw() {
    drawFrame = 0;
    const ratio = window.devicePixelRatio || 1;
    const width = strip.clientWidth, height = strip.clientHeight;
    if (!width) return;
    strip.width = Math.round(width * ratio);
    strip.height = Math.round(height * ratio);
    const ctx = strip.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const c = colors();
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = c.paper;
    ctx.fillRect(0, 0, width, height);
    const top = 6, bottom = height - 16;
    // Energy of the planned (edited) score.
    ctx.strokeStyle = c.accent;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    quote.score.beats.forEach((beat, i) => {
      const y = bottom - beat.energy * (bottom - top - 10);
      i ? ctx.lineTo(x(beat.time), y) : ctx.moveTo(x(beat.time), y);
    });
    ctx.stroke();
    // Planned cuts and passage boundaries.
    for (const passage of quote.score.passages) {
      ctx.fillStyle = c.ink;
      ctx.fillRect(x(passage.start) - 1, bottom + 2, 2, 12);
      for (const shot of passage.shots.slice(1)) ctx.fillRect(x(shot.start), bottom + 6, 1, 8);
    }
    // Beats from the detected grid, shifted by the nudge.
    detected.beats.forEach((beat, i) => {
      const px = x(beatTime(i));
      const strong = isDownbeat(i);
      ctx.strokeStyle = i === selected ? c.accent : muted.has(i) ? c.muted : c.ink;
      ctx.lineWidth = i === selected ? 3 : strong ? 2 : 1;
      const y0 = strong ? top : top + 10;
      ctx.globalAlpha = muted.has(i) ? 0.55 : 1;
      ctx.beginPath();
      ctx.moveTo(px, y0);
      ctx.lineTo(px, bottom);
      ctx.stroke();
      if (muted.has(i)) {
        ctx.beginPath();
        ctx.moveTo(px - 3, y0 + 4);
        ctx.lineTo(px + 3, y0 + 10);
        ctx.moveTo(px + 3, y0 + 4);
        ctx.lineTo(px - 3, y0 + 10);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });
    // Playhead.
    if (ws) {
      ctx.fillStyle = c.accent;
      ctx.fillRect(x(ws.getCurrentTime()) - 1, 0, 2, height);
    }
    strip.setAttribute("aria-valuetext", describe());
    caption.textContent = describe();
  }

  function schedule() {
    if (!drawFrame) drawFrame = requestAnimationFrame(draw);
  }

  function select(index) {
    selected = index;
    if (index !== null && ws) ws.setTime(Math.max(0, Math.min(duration, beatTime(index))));
    refreshStatus();
  }

  function nearestBeat(px) {
    let best = null, bestDistance = 10;
    detected.beats.forEach((beat, i) => {
      const distance = Math.abs(x(beatTime(i)) - px);
      if (distance < bestDistance) { best = i; bestDistance = distance; }
    });
    return best;
  }

  function renderSections() {
    sectionList.replaceChildren();
    sections.forEach((item, i) => {
      const end = sections[i + 1] ? sections[i + 1].start : duration;
      const row = text("div", "", "se-section-row");
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Energy label for the section starting at ${item.start.toFixed(1)} seconds`);
      LABELS.forEach(label => select.append(option(label, label, LABEL_HELP[label])));
      select.value = item.label;
      select.onchange = () => {
        item.label = select.value;
        paintRegions();
        refreshStatus();
      };
      row.append(text("span", `${fmt(item.start)}–${fmt(end)}`, "se-section-time"), select);
      if (i > 0) {
        const merge = text("button", "Merge with previous", "quiet", "Remove the boundary before this section");
        merge.type = "button";
        merge.onclick = () => {
          sections.splice(i, 1);
          rebuildRegions();
          refreshStatus();
        };
        row.append(merge);
      }
      sectionList.append(row);
    });
  }

  function paintRegions() {
    if (!regions) return;
    regions.getRegions().forEach(region => {
      const item = sections[Number(region.id.slice(1))];
      if (item) region.setOptions({ color: REGION_COLORS[item.label], content: item.label });
    });
  }

  function rebuildRegions() {
    renderSections();
    if (!regions) return;
    regions.clearRegions();
    sections.forEach((item, i) => {
      regions.addRegion({
        id: "s" + i, start: item.start, end: sections[i + 1] ? sections[i + 1].start : duration,
        color: REGION_COLORS[item.label], content: item.label, drag: false, resize: i > 0 || sections.length > 1,
        minLength: 1
      });
    });
  }

  // Sections start on a bar: a boundary just after a downbeat would leave a sliver the planner skips.
  function snapToDownbeat(time) {
    let best = time, distance = 1.0;
    detected.beats.forEach((beat, i) => {
      if (!isDownbeat(i)) return;
      const gap = Math.abs(beatTime(i) - time);
      if (gap < distance) { best = beatTime(i); distance = gap; }
    });
    return Math.round(best * 100) / 100;
  }

  function onRegionUpdated(region) {
    const index = Number(region.id.slice(1));
    const item = sections[index];
    if (!item) return;
    const start = index === 0 ? 0 : snapToDownbeat(region.start);
    if (index > 0 && Math.abs(region.start - start) > 1e-6) region.setOptions({ start });
    item.start = start;
    if (index > 0) {
      const previous = regions.getRegions().find(r => r.id === "s" + (index - 1));
      if (previous && Math.abs(previous.end - start) > 1e-6) previous.setOptions({ end: start });
    }
    const next = regions.getRegions().find(r => r.id === "s" + (index + 1));
    if (next && Math.abs(next.start - region.end) > 1e-6) {
      sections[index + 1].start = Math.round(region.end * 100) / 100;
      next.setOptions({ start: region.end });
    }
    renderSections();
    refreshStatus();
  }

  strip.addEventListener("click", event => {
    const rect = strip.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const hit = nearestBeat(px);
    if (hit !== null) select(hit);
    else if (ws) { ws.setTime(Math.max(0, Math.min(duration, px / rect.width * duration))); schedule(); }
  });
  strip.addEventListener("keydown", event => {
    const key = event.key.toLowerCase();
    if (key === "arrowright" || key === "arrowleft") {
      const step = key === "arrowright" ? 1 : -1;
      select(selected === null ? 0 : Math.max(0, Math.min(detected.beats.length - 1, selected + step)));
    } else if (key === "m" && selected !== null) {
      muteBtn.click();
    } else if (key === "b" && selected !== null) {
      barOne.click();
    } else if (key === " ") {
      play.click();
    } else return;
    event.preventDefault();
  });
  play.onclick = () => ws && ws.playPause();
  nudge.oninput = () => {
    edits.beat_nudge_ms = Number(nudge.value);
    refreshStatus();
  };
  barOne.onclick = () => {
    if (selected === null) return;
    edits.bar_one_beat = selected;
    refreshStatus();
  };
  muteBtn.onclick = () => {
    if (selected === null) return;
    muted.has(selected) ? muted.delete(selected) : muted.add(selected);
    refreshStatus();
  };
  resetBtn.onclick = () => {
    Object.assign(edits, emptyEdits());
    muted.clear();
    nudge.value = "0";
    sections = detected.sections.map(s => ({ start: s.start, label: s.label }));
    driver = "mix";
    driverSelect.value = "mix";
    quality = "standard";
    qualitySelect.value = "standard";
    lines = JSON.parse(appliedLines);
    singers = JSON.parse(appliedSingers);
    renderLip();
    rebuildRegions();
    refreshStatus();
  };
  driverSelect.onchange = () => {
    driver = driverSelect.value;
    renderDriver();
    refreshStatus();
  };
  qualitySelect.onchange = () => {
    quality = qualitySelect.value;
    renderDriver();
    refreshStatus();
  };
  splitBtn.onclick = () => {
    const at = snapToDownbeat(ws ? ws.getCurrentTime() : 0);
    const index = sections.findIndex((item, i) => at > item.start + 1 && at < (sections[i + 1] ? sections[i + 1].start : duration) - 1);
    if (index < 0) { status.textContent = "Place the cursor at least a second inside a section to split it."; return; }
    sections.splice(index + 1, 0, { start: at, label: sections[index].label });
    rebuildRegions();
    refreshStatus();
  };
  replanBtn.onclick = async () => {
    replanBtn.disabled = true;
    replanBtn.setAttribute("aria-busy", "true");
    status.textContent = "Planning…";
    try {
      await onReplan(collectEdits(), driver, usesQuality(driver) ? quality : "standard",
        linesOn ? { lyric_lines: lines.map(item => ({ start: item.start, end: item.end, text: item.text.trim(), timing: item.timing || "manual", ...(item.section ? { section: item.section } : {}) })), ...(lipOn ? { singers } : {}) } : null);
    } catch (error) {
      status.textContent = error.message;
      replanBtn.removeAttribute("aria-busy");
      refreshStatus();
    }
  };
  function modelReady(name) {
    return Boolean(stems && stems.installed && stems.models[name] && stems.models[name].ready);
  }

  function renderDriver() {
    driverSetup.replaceChildren();
    for (const entry of driverSelect.options) {
      entry.disabled = entry.value !== "mix" && !modelReady(modelFor(entry.value, quality)) && entry.value !== driver;
    }
    qualityLabel.hidden = !usesQuality(driver);
    qualitySelect.value = quality;
    for (const item of qualitySelect.options) item.disabled = item.value === "high" && !modelReady("htdemucs_ft") && quality !== "high";
    if (!stems) {
      driverNote.textContent = "Checking whether instrument analysis is available…";
      return;
    }
    if (!stems.installed) {
      driverNote.textContent = "Following one instrument needs an optional add-on (Demucs, free, MIT-licensed) that "
        + "separates the song into drums, bass, vocals and the rest. Nothing has been installed or downloaded. "
        + `To enable it, run "${stems.install_command}" in this app's environment, then reopen this preview.`;
      return;
    }
    const need = driver === "mix" ? [] : [modelFor(driver, quality)];
    const missing = Object.keys(MODELS).filter(name => !modelReady(name));
    driverNote.textContent = driver === "mix"
      ? "Following the whole mix, as before. Pick an instrument to drive the video from that part instead. "
        + "The first time for a song, separating it can take several minutes; it is saved afterwards."
      : `Following ${driver}. Press Re-plan to apply it; the first time for a song can take several minutes.`;
    if (stems.recommendation) {
      driverNote.textContent += " For this computer: " + stems.recommendation.notes[0];
    }
    for (const name of missing) {
      const wanted = need.includes(name);
      const row = text("div", "", "se-setup-row");
      const consent = document.createElement("input");
      consent.type = "checkbox";
      const approve = text("label", "", "check");
      approve.append(consent, ` I approve a one-time download of the ${MODELS[name].label} model (${MODELS[name].size}, from the Demucs project).`);
      const go = text("button", `Set up ${MODELS[name].label} model`, wanted ? "primary" : "secondary");
      go.type = "button";
      go.disabled = true;
      consent.onchange = () => { go.disabled = !consent.checked; };
      go.onclick = async () => {
        go.disabled = true;
        go.setAttribute("aria-busy", "true");
        status.textContent = "Downloading the stem model… this can take a few minutes.";
        try {
          await json("/api/stems/prepare", { model: name, consent: true });
          for (let wait = 0; wait < 1200; wait += 1) {
            await new Promise(resolve => setTimeout(resolve, 2000));
            const job = await (await api("/api/status")).json();
            if (job.state !== "running") {
              if (job.state === "failed") throw new Error(job.message);
              break;
            }
          }
          stems = await (await api("/api/stems")).json();
          renderDriver();
          status.textContent = "The stem model is ready.";
        } catch (error) {
          status.textContent = error.message;
          go.disabled = false;
          go.removeAttribute("aria-busy");
        }
      };
      row.append(approve, go);
      driverSetup.append(row);
    }
  }

  api("/api/stems").then(response => response.json()).then(value => { stems = value; renderDriver(); })
    .catch(() => { stems = { installed: false, install_command: "pip install demucs", models: {} }; renderDriver(); });
  renderDriver();

  const confirmed = item => { if (item.timing === "interpolated" || item.timing === "uncertain") item.timing = "manual"; };

  // Advisory only: a clear voice/singer gender mismatch gets a note and a one-click best match, never a block.
  function renderVoice(plan) {
    const info = quote.voice, voiceKind = info && info.voice, genders = (info && info.genders) || {};
    const singer = singers[0] || plan.singer;
    voiceNote.replaceChildren();
    if (!voiceKind || !genders[singer] || genders[singer] === voiceKind) return;
    const match = (request.actors || []).find(id => genders[id] === voiceKind);
    voiceNote.append(`The vocals sound ${voiceKind}, but ${plan.actors[singer] || singer} reads as ${genders[singer]}. You can keep this choice. `);
    if (!match) return;
    const useMatch = text("button", `Use ${plan.actors[match] || match}`, "secondary", "Make the best-matching actor the main singer");
    useMatch.type = "button";
    useMatch.onclick = () => { singers = [match]; singerSelect.value = match; refreshStatus(); renderVoice(plan); };
    voiceNote.append(useMatch);
  }

  function renderLip() {
    if (!linesOn) return;
    const plan = quote.lipsync || { actors: {}, passages: {} };
    singerSelect.replaceChildren(option("", "Choose for me (seeded)", "Pick one of the cast with the production seed"),
      ...(request.actors || []).map(id => option(id, plan.actors[id] || id)));
    singerSelect.value = singers[0] || "";
    if (lipOn) renderVoice(plan);
    lineList.replaceChildren();
    lines.forEach((item, i) => {
      const row = text("div", "", "se-line-row");
      const field = (label, key, step) => {
        const input = document.createElement("input");
        input.type = "number";
        input.step = step;
        input.min = "0";
        input.value = String(item[key]);
        input.setAttribute("aria-label", `Lyric line ${i + 1} ${label} (seconds)`);
        input.onchange = () => { item[key] = Number(input.value); confirmed(item); refreshStatus(); };
        return input;
      };
      const words = document.createElement("input");
      words.type = "text";
      words.value = item.text;
      words.placeholder = "The words sung on this line";
      words.maxLength = 300;
      words.setAttribute("aria-label", `Lyric line ${i + 1} words`);
      words.oninput = () => { item.text = words.value; refreshStatus(); };
      words.onchange = () => { confirmed(item); renderLip(); };
      if (item.timing === "interpolated" || item.timing === "uncertain") {
        const confirm = text("button", "Confirm timing", "secondary",
          "These times were guessed. Check them against the waveform; until you confirm or edit them this line is not used for singing.");
        confirm.type = "button";
        confirm.onclick = () => { item.timing = "manual"; renderLip(); refreshStatus(); };
        row.append(confirm);
      }
      const remove = text("button", "Remove", "quiet", "Remove this lyric line");
      remove.type = "button";
      remove.onclick = () => { lines.splice(i, 1); renderLip(); refreshStatus(); };
      if (item.section) {
        row.classList.add("tagged");
        row.prepend(text("span", item.section, "se-tag", "Section marker from the pasted lyrics"));
      }
      row.append(field("start", "start", "0.1"), field("end", "end", "0.1"), words, remove);
      lineList.append(row);
    });
    lipSummary.replaceChildren();
    const guessed = lines.filter(item => item.timing === "interpolated" || item.timing === "uncertain").length;
    if (guessed) {
      lipSummary.append(text("p", `${guessed} lyric line(s) have guessed timing. They are not used for singing until you confirm or edit them.`, "se-warn"));
    }
    const passages = quote.score ? quote.score.passages : [];
    if (!lines.length) {
      lipSummary.append(text("p", lipOn ? "No lyric lines yet, so every passage stays sealed. Add the sung lines above, then press Re-plan." : "No lyric lines yet, so there is nothing to caption. Detect or paste the lyrics above, then press Re-plan.", "muted"));
    }
    if (lipOn) passages.forEach(passage => {
      const entry = plan.passages[`seg${String(passage.index).padStart(3, "0")}`];
      if (!entry) return;
      const who = entry.singing ? `${plan.actors[entry.actor_id] || entry.actor_id} sings (${entry.reason})` : `sealed (${entry.reason})`;
      lipSummary.append(text("p", `${fmt(passage.start)}–${fmt(passage.end)} · ${who}`, entry.singing ? "se-sings" : "muted"));
    });
  }
  let speech = null;
  const SPEECH = { tiny: "tiny", base: "base", small: "small", medium: "medium", "large-v3": "large-v3 (most accurate)" };
  function renderSpeech() {
    if (!linesOn) return;
    speechSetup.replaceChildren();
    if (!speech) { detectNote.textContent = "Checking whether lyrics detection is available…"; return; }
    const keep = speechSelect.value;
    speechSelect.replaceChildren(...Object.entries(speech.models).map(([name, info]) =>
      option(name, `${SPEECH[name]}${info.cached ? " · on this computer" : ` · ${info.download} to download`}`)));
    speechSelect.value = keep && speech.models[keep] ? keep : (Object.keys(speech.models).filter(n => speech.models[n].cached).pop() || "large-v3");
    const chosen = speechSelect.value;
    detectBtn.disabled = !speech.available || !speech.models[chosen].cached;
    pasteBtn.disabled = detectBtn.disabled;
    if (!speech.available) {
      detectNote.textContent = `Automatic lyrics detection is an optional add-on (Whisper, MIT) and is not installed. Install it with "${speech.install_command}" `
        + "(or point MMV_LYRICS_PYTHON at a Python that already has it). You can still type or paste the lines and set their times.";
    } else if (!speech.models[chosen].cached) {
      detectNote.textContent = `The ${chosen} speech model is not on this computer yet (${speech.models[chosen].download}). Nothing downloads without your approval.`;
      const consent = document.createElement("input");
      consent.type = "checkbox";
      const approve = text("label", "", "check");
      approve.append(consent, ` I approve a one-time download of the ${chosen} speech model (${speech.models[chosen].download}, from OpenAI's Whisper release).`);
      const go = text("button", `Set up ${chosen} model`, "primary");
      go.type = "button";
      go.disabled = true;
      consent.onchange = () => { go.disabled = !consent.checked; };
      go.onclick = async () => {
        go.disabled = true;
        status.textContent = "Downloading the speech model…";
        try {
          await json("/api/lyrics/prepare", { model: chosen, consent: true });
          await pollJob();
          speech = await (await api("/api/lyrics")).json();
          renderSpeech();
          status.textContent = "The speech model is ready.";
        } catch (error) { status.textContent = error.message; go.disabled = false; }
      };
      const row = text("div", "", "se-setup-row");
      row.append(approve, go);
      speechSetup.append(row);
    } else {
      detectNote.textContent = "Detection listens to the vocals when the stems add-on is ready (much more accurate), otherwise to the whole mix. Every detected line can be edited.";
    }
  }
  async function pollJob() {
    for (let wait = 0; wait < 1800; wait += 1) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const job = await (await api("/api/status")).json();
      if (job.state !== "running") {
        if (job.state === "failed") throw new Error(job.message);
        return job;
      }
    }
    throw new Error("This is taking too long; check the studio log");
  }
  speechSelect.onchange = renderSpeech;
  detectBtn.onclick = async () => {
    detectBtn.disabled = true;
    detectBtn.setAttribute("aria-busy", "true");
    status.textContent = "Listening to the song… this can take a minute.";
    try {
      await json("/api/lyrics/detect", { song: request.song, model: speechSelect.value, beats_per_bar: request.beats_per_bar || 4 });
      const job = await pollJob();
      const found = job.result.lines.map(item => ({ start: item.start, end: item.end, text: item.text, timing: "matched" }));
      if (!found.length) throw new Error("No words were heard. Is this song instrumental? You can still add lines by hand.");
      lines = found;
      renderLip();
      refreshStatus();
      status.textContent = `Detected ${found.length} lines from the ${job.result.source}. Check them, then press Re-plan.`;
    } catch (error) { status.textContent = error.message; }
    detectBtn.removeAttribute("aria-busy");
    renderSpeech();
  };
  pasteBtn.onclick = async () => {
    status.textContent = "Timing your lyrics against the song…";
    try {
      const result = await json("/api/lyrics/align", { song: request.song, model: speechSelect.value, beats_per_bar: request.beats_per_bar || 4, text: pasteBox.value });
      lines = result.lines.map(item => ({ start: item.start, end: item.end, text: item.text, timing: item.timing, section: item.section || null }));
      renderLip();
      refreshStatus();
      const guessed = lines.filter(item => item.timing === "interpolated" || item.timing === "uncertain").length;
      status.textContent = guessed ? `${guessed} line(s) could not be matched well and have guessed times; confirm or edit them.` : "Your lyrics are timed. Check them, then press Re-plan.";
    } catch (error) { status.textContent = error.message; }
  };
  api("/api/lyrics").then(response => response.json()).then(value => { speech = value; renderSpeech(); })
    .catch(() => { speech = { available: false, install_command: "pip install openai-whisper", models: { "large-v3": { cached: false, download: "about 3.1 GB" } } }; renderSpeech(); });
  renderSpeech();
  singerSelect.onchange = () => { singers = singerSelect.value ? [singerSelect.value] : []; refreshStatus(); };
  addLine.onclick = () => {
    const at = Math.round((ws ? ws.getCurrentTime() : 0) * 10) / 10;
    lines.push({ start: at, end: Math.min(duration, Math.round((at + 3) * 10) / 10), text: "" });
    lines.sort((a, b) => a.start - b.start);
    renderLip();
    refreshStatus();
    const rows = lineList.querySelectorAll('input[type="text"]');
    const idx = lines.findIndex(item => item.start === at && item.text === "");
    if (rows[idx]) rows[idx].focus();
  };
  renderLip();

  const resize = new ResizeObserver(schedule);
  resize.observe(strip);

  active = {
    destroy() {
      resize.disconnect();
      cancelAnimationFrame(drawFrame);
      if (ws) ws.destroy();
      ws = null;
      onDirty(false);
    }
  };

  renderSections();
  refreshStatus();
  try {
    const peaks = await loadPeaks(request.song);
    const style = getComputedStyle(box);
    ws = WaveSurfer.create({
      container: stage, height: 96, url: "/api/uploads/song/" + encodeURIComponent(request.song),
      peaks: [peaks.peaks], duration: peaks.duration, normalize: true,
      waveColor: style.getPropertyValue("--muted").trim() || "#8a9a8f",
      progressColor: style.getPropertyValue("--score-accent").trim() || "#c2711d",
      cursorColor: style.getPropertyValue("--ink").trim() || "#222", barWidth: 0, interact: true
    });
    regions = ws.registerPlugin(RegionsPlugin.create());
    ws.on("timeupdate", time => { clock.textContent = `${fmt(time)} / ${fmt(duration)}`; schedule(); });
    ws.on("play", () => { play.textContent = "Pause"; });
    ws.on("pause", () => { play.textContent = "Play"; });
    ws.on("seeking", schedule);
    regions.on("region-updated", onRegionUpdated);
    ws.on("ready", rebuildRegions);
    ws.on("decode", rebuildRegions);
    clock.textContent = `0:00 / ${fmt(duration)}`;
  } catch (error) {
    stage.append(text("p", error.message + ". You can still edit the beats below.", "muted"));
  }
}
