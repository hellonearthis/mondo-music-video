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
  const driverLabel = text("label", "Follow this part of the song ", "se-driver-label",
    "The video's energy, and so its cutting speed and montage style, follows the part you pick. The beat grid still comes from the whole song.");
  driverLabel.append(driverSelect);
  const driverNote = text("p", "", "muted se-driver-note");
  const driverSetup = text("div", "", "se-driver-setup");
  driverRow.append(driverLabel, driverNote, driverSetup);

  const sectionHead = text("h3", "Sections");
  sectionHead.title = "Sections decide the montage style. Drag a section's edge on the waveform to move it.";
  const sectionList = text("div", "", "se-sections");
  const sectionBar = text("div", "", "se-section-bar");
  const splitBtn = text("button", "Split section at cursor", "secondary", "Start a new section where the cursor is");
  splitBtn.type = "button";
  sectionBar.append(splitBtn, text("span", "Drag a section's edge on the waveform to move it.", "muted"));

  box.append(stage, strip, caption, legend, bar, status, driverRow, sectionHead, sectionList, sectionBar);

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

  function sectionsValid() {
    return sections.every((item, i) => (i === 0 ? item.start === 0 : item.start > sections[i - 1].start + 0.999)
      && (sections[i + 1] ? sections[i + 1].start : duration) - item.start >= 0.999);
  }

  function refreshStatus() {
    const current = collectEdits();
    const dirty = !same(current, applied) || driver !== appliedDriver;
    const valid = sectionsValid();
    barOne.disabled = selected === null;
    muteBtn.disabled = selected === null;
    replanBtn.disabled = !dirty || !valid;
    replanBtn.classList.toggle("attention", dirty && valid);
    status.textContent = !valid ? "Each section must be at least 1 second long."
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
    rebuildRegions();
    refreshStatus();
  };
  driverSelect.onchange = () => {
    driver = driverSelect.value;
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
      await onReplan(collectEdits(), driver);
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
    for (const option of driverSelect.options) {
      option.disabled = option.value !== "mix" && !modelReady(SIX_STEM.has(option.value) ? "htdemucs_6s" : "htdemucs")
        && option.value !== driver;
    }
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
    const need = driver === "mix" ? [] : [SIX_STEM.has(driver) ? "htdemucs_6s" : "htdemucs"];
    const missing = ["htdemucs", "htdemucs_6s"].filter(name => !modelReady(name));
    driverNote.textContent = driver === "mix"
      ? "Following the whole mix, as before. Pick an instrument to drive the video from that part instead. "
        + "The first time for a song, separating it can take several minutes; it is saved afterwards."
      : `Following ${driver}. Press Re-plan to apply it; the first time for a song can take several minutes.`;
    for (const name of missing) {
      const wanted = need.includes(name);
      const row = text("div", "", "se-setup-row");
      const consent = document.createElement("input");
      consent.type = "checkbox";
      const approve = text("label", "", "check");
      approve.append(consent, ` I approve a one-time download of the ${name === "htdemucs" ? "4-stem" : "6-stem"} model (a few hundred MB at most, from the Demucs project).`);
      const go = text("button", `Set up ${name === "htdemucs" ? "4-stem" : "6-stem"} model`, wanted ? "primary" : "secondary");
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
