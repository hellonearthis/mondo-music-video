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
let currentCustomVocab = {};
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
    custom_vocabulary: currentCustomVocab,
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
  if (saved.custom_vocabulary && typeof saved.custom_vocabulary === "object") {
    currentCustomVocab = saved.custom_vocabulary;
    updateVocabCustomBadge();
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
    if (!styles.length) {
      const empty = option("", "No styles yet — add one in Styles");
      empty.disabled = true;
      select.replaceChildren(empty);
    }
    if (styles.some(x => x.id === old)) select.value = old;
  });
  $("#style-list").replaceChildren(...styles.map(style => {
    const card = text("article", "", "card", `Style card: ${style.name}`);
    card.append(text("h2", style.name), text("p", style.direction));
    const remove = text("button", "Delete style", "quiet operation-action", `Delete ${style.name} from this machine`);
    remove.type = "button";
    remove.onclick = handle(async () => {
      if (!window.confirm(`Delete style “${style.name}” from this machine? Completed videos are kept.`)) return;
      await api(`/api/styles/${encodeURIComponent(style.id)}`, {method: "DELETE"});
      await loadStyles();
      scheduleSave();
      notice("Style deleted from your local collection.");
    });
    card.append(remove);
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
      await saveDownload(await api(`/api/actors/${encodeURIComponent(actor.id)}/export`, {method: "POST"}), actor.id + ".oap");
    });
    card.append(image, text("h2", actor.name), text("p", actorOverview(actor)), text("p", actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export"), button);
    if (!actor.oap) {
      const cleared = document.createElement("input");
      cleared.type = "checkbox";
      const clearedLabel = text("label", "", "check audition-export", "Only check this if the reference is a cleaned or watermarked take you are willing to share with casting directors");
      clearedLabel.append(cleared, " Reference is cleared for auditions");
      const audition = text("button", "Export audition package", "quiet audition-button", `Export a signed audition package for ${actor.name}; cast-only assets are listed by hash but left out`);
      audition.type = "button";
      audition.onclick = handle(async () => {
        const query = new URLSearchParams({tier: "audition", reference_clearance: cleared.checked ? "audition" : "cast"});
        await saveDownload(await api(`/api/actors/${encodeURIComponent(actor.id)}/export?${query}`, {method: "POST"}), actor.id + "-audition.oap");
        notice(cleared.checked ? "Audition package exported with the audition-cleared reference." : "Audition package exported. The cast-only reference is listed by hash but not included.");
      });
      card.append(clearedLabel, audition);
    }
    const remove = text("button", "Delete actor", "quiet operation-action", `Delete ${actor.name} from this machine`);
    remove.type = "button";
    remove.onclick = handle(async () => {
      if (!window.confirm(`Delete actor “${actor.name}”, their reference image and imported package from this machine? Export first if you want a backup. Completed videos and earlier exports are kept.`)) return;
      await api(`/api/actors/${encodeURIComponent(actor.id)}`, {method: "DELETE"});
      await loadActors();
      scheduleSave();
      notice("Actor deleted from your local cast.");
    });
    card.append(remove);
    return card;
  }));
  if (!actors.length) $("#actor-list").append(text("div", "Your cast starts here. Create an actor or import a full OAP package below.", "empty", "No actors currently in your studio library"));
  const agreementActor = $("#agreement-form").elements.actor_id;
  const chosen = agreementActor.value;
  agreementActor.replaceChildren(...actors.map(actor => option(actor.id, actor.name)));
  if (actors.some(actor => actor.id === chosen)) agreementActor.value = chosen;
}
async function saveDownload(response, filename) {
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function shortDid(did) { return did && did.length > 34 ? did.slice(0, 22) + "…" + did.slice(-8) : did || "none"; }
async function loadAgreements() {
  const agreements = await (await api("/api/agreements")).json();
  $("#agreement-list").replaceChildren(...agreements.map(agreement => {
    const card = text("article", "", "card", `Role agreement ${agreement.id}`);
    if (agreement.damaged) {
      card.append(text("span", "Damaged record", "oap-badge-pill badge-invalid"), text("h3", agreement.id), text("p", agreement.issues.join("; ")));
      return card;
    }
    const status = agreement.complete ? ["Signed by both parties", "badge-valid"]
      : agreement.issues.length && agreement.signed.length ? ["Signature problem", "badge-invalid"]
      : agreement.signed.length ? [`Signed by ${agreement.signed.join(" and ")}; awaiting countersignature`, "badge-unsigned"]
      : ["Unsigned draft", "badge-unsigned"];
    const compensation = agreement.compensation || {};
    card.append(text("span", status[0], "oap-badge-pill " + status[1]), text("h3", agreement.title || agreement.id),
      text("p", `${agreement.character || "Role"} · actor ${agreement.actor_id || "unknown"} · ${compensation.amount} ${compensation.currency}`),
      text("p", `Agent ${shortDid(agreement.agent_did)}${agreement.local_agent ? " (this studio)" : ""}`, "", agreement.agent_did),
      text("p", `Director ${shortDid(agreement.director_did)} (this studio)`, "", agreement.director_did));
    if (agreement.issues.length && agreement.signed.length) card.append(text("p", agreement.issues.join("; ")));
    const actions = text("div", "", "agreement-actions");
    const path = `/api/agreements/${encodeURIComponent(agreement.id)}`;
    const roles = ["director", ...(agreement.local_agent ? ["agent"] : [])].filter(role => !agreement.signed.includes(role));
    for (const role of roles) {
      const sign = text("button", `Sign as ${role}`, "secondary operation-action", `Sign this agreement with this studio's ${role} key`);
      sign.type = "button";
      sign.onclick = handle(async () => {
        if (!window.confirm(`Sign “${agreement.title}” as ${role}? This commits the ${role} to ${compensation.amount} ${compensation.currency} and the casting call terms. Signatures cannot be withdrawn from copies already shared.`)) return;
        await json(`${path}/sign`, {role});
        await loadAgreements();
        notice(`Signed as ${role}.`);
      });
      actions.append(sign);
    }
    const verify = text("button", "Verify", "secondary", "Check both signatures and the exact manifest and casting call bindings");
    verify.type = "button";
    verify.onclick = handle(async () => {
      const result = await (await api(`${path}/verify`)).json();
      notice(result.ok ? `Verified: both signatures are valid. ${result.note}` : `Not complete: ${result.issues.join("; ")}`);
    });
    const download = text("button", "Download bundle", "secondary", "Zip of agreement.json, manifest.json and casting_call.json for the other party");
    download.type = "button";
    download.onclick = handle(async () => saveDownload(await api(`${path}/bundle`, {method: "POST"}), agreement.id + "-agreement.zip"));
    actions.append(verify, download);
    card.append(actions);
    return card;
  }));
  if (!agreements.length) $("#agreement-list").append(text("div", "No role agreements yet. Draft one below.", "empty"));
}

// One theme observer for all score views; loadOutputs disposes views before replacing cards.
const scoreViews = new Set();
new MutationObserver(() => scoreViews.forEach(view => view.draw())).observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
const GRAMMAR_CLASSES = {"Standard": "standard", "Thematic multi-scene": "thematic", "Chaotic multi-scene": "chaotic", "Single-subject fragmentation": "fragmentation"};
function scoreView(output, video) {
  const box = text("details", "", "score-view");
  box.append(text("summary", "Watch the song conduct", "", "Show the beats, energy and planned cuts behind this video"));
  const canvas = document.createElement("canvas");
  canvas.tabIndex = 0;
  canvas.setAttribute("role", "slider");
  canvas.setAttribute("aria-label", "Musical score position. Arrow keys jump between planned cuts; Home and End go to the start and end.");
  canvas.setAttribute("aria-valuemin", "0");
  const caption = text("p", "", "score-caption");
  caption.setAttribute("aria-live", "polite");
  const legend = text("div", "", "score-legend");
  box.append(canvas, caption, legend);
  let score = null, frame = 0, lastCaption = "";
  const x = time => time / Math.max(score.duration || score.song_end, 0.001) * canvas.clientWidth;
  function colors() {
    const style = getComputedStyle(box);
    const value = name => style.getPropertyValue(name).trim();
    return {ink: value("--ink"), muted: value("--muted"), line: value("--line"), accent: value("--score-accent"),
            grammar: Object.fromEntries(Object.values(GRAMMAR_CLASSES).map(key => [key, value("--score-" + key)]))};
  }
  function describe(time) {
    if (time < score.offset) return "Opening ident · the song starts at " + score.offset.toFixed(1) + " s";
    if (time >= score.song_end) return "Closing ident";
    const passage = score.passages.find(item => time >= item.start && time < item.end) || score.passages.at(-1);
    const index = passage.shots.findIndex((shot, i) => time >= shot.start && (time < shot.end || i === passage.shots.length - 1));
    const shot = passage.shots[Math.max(index, 0)];
    const cut = {passage: passage.on_downbeat ? "passage starts on a downbeat" : "passage start",
                 downbeat: "cut on a downbeat", beat: "cut on a beat", split: "long hold split"}[shot.cut];
    return `${passage.section} energy (${Number(passage.energy).toFixed(2)}) → ${passage.grammar}: ${passage.grammar_description} ` +
      `Shot ${Math.max(index, 0) + 1} of ${passage.shots.length}, ${shot.shot_scale}, ${cut}. ` +
      `${passage.shots.length} ${passage.shots.length === 1 ? "shot" : "shots"} across ${passage.beats} beats at ${Math.round(score.tempo_bpm)} BPM.`;
  }
  function draw() {
    if (!score) return;
    const ratio = window.devicePixelRatio || 1, width = canvas.clientWidth, height = canvas.clientHeight;
    if (canvas.width !== Math.round(width * ratio)) { canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio); }
    const ctx = canvas.getContext("2d"), c = colors();
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const band = 22, curveTop = band + 8, curveBottom = height - 20;
    for (const passage of score.passages) {
      ctx.fillStyle = c.grammar[GRAMMAR_CLASSES[passage.grammar]] || c.line;
      ctx.fillRect(x(passage.start), 0, Math.max(1, x(passage.end) - x(passage.start) - 1), band);
      ctx.strokeStyle = c.ink; ctx.globalAlpha = 0.55;
      for (const shot of passage.shots.slice(1)) { ctx.beginPath(); ctx.moveTo(x(shot.start), 0); ctx.lineTo(x(shot.start), curveBottom); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
    ctx.beginPath(); ctx.moveTo(x(score.offset), curveBottom);
    for (const beat of score.beats) ctx.lineTo(x(beat.time), curveBottom - beat.energy * (curveBottom - curveTop));
    ctx.lineTo(x(score.song_end), curveBottom); ctx.closePath();
    ctx.fillStyle = c.accent; ctx.globalAlpha = 0.28; ctx.fill(); ctx.globalAlpha = 1;
    ctx.strokeStyle = c.accent; ctx.lineWidth = 1.5; ctx.stroke(); ctx.lineWidth = 1;
    for (const beat of score.beats) {
      ctx.fillStyle = beat.downbeat ? c.ink : c.muted;
      ctx.fillRect(x(beat.time) - (beat.downbeat ? 1 : 0.5), height - (beat.downbeat ? 16 : 9), beat.downbeat ? 2 : 1, beat.downbeat ? 16 : 9);
    }
    const now = video.currentTime || 0;
    ctx.fillStyle = c.ink; ctx.fillRect(x(now) - 1, 0, 2, height);
    const line = describe(now);
    if (line !== lastCaption) { caption.textContent = line; lastCaption = line; }
    canvas.setAttribute("aria-valuemax", String(end()));
    canvas.setAttribute("aria-valuenow", now.toFixed(1));
    canvas.setAttribute("aria-valuetext", `${now.toFixed(1)} seconds. ${line}`);
  }
  const end = () => score.duration || score.song_end;
  function jump(time) { video.currentTime = Math.min(Math.max(0, time), end()); draw(); }
  function loop() { draw(); if (!video.paused && !video.ended) frame = requestAnimationFrame(loop); }
  function seek(event) {
    if (!score) return;
    const rect = canvas.getBoundingClientRect();
    jump((event.clientX - rect.left) / rect.width * end());
  }
  canvas.addEventListener("keydown", event => {
    if (!score) return;
    const cuts = [0, ...score.passages.flatMap(passage => passage.shots.map(shot => shot.start)), end()];
    const now = video.currentTime || 0;
    const target = {ArrowRight: cuts.find(t => t > now + 0.05), ArrowUp: cuts.find(t => t > now + 0.05),
                    ArrowLeft: cuts.filter(t => t < now - 0.05).at(-1), ArrowDown: cuts.filter(t => t < now - 0.05).at(-1),
                    Home: 0, End: end()}[event.key];
    if (target === undefined && !(event.key in {Home: 1, End: 1})) return;
    event.preventDefault();
    jump(target ?? now);
  });
  canvas.addEventListener("pointerdown", event => { canvas.setPointerCapture(event.pointerId); seek(event); });
  canvas.addEventListener("pointermove", event => { if (canvas.hasPointerCapture(event.pointerId)) seek(event); });
  video.addEventListener("play", () => { cancelAnimationFrame(frame); loop(); });
  ["seeked", "pause", "timeupdate", "loadedmetadata"].forEach(name => video.addEventListener(name, draw));
  const resize = new ResizeObserver(draw);
  resize.observe(canvas);
  const view = {draw, dispose: () => { resize.disconnect(); cancelAnimationFrame(frame); }};
  scoreViews.add(view);
  box.addEventListener("toggle", async () => {
    if (!box.open || score) return draw();
    try {
      score = await (await api(`/api/outputs/${encodeURIComponent(output.file.split("/")[0])}/score`)).json();
      legend.replaceChildren(...[...new Set(score.passages.map(passage => passage.grammar))].map(name => text("span", name, "score-key score-" + (GRAMMAR_CLASSES[name] || "other"))),
        text("span", "energy", "score-key score-energy"), text("span", "beats · downbeats (tall)", "score-key score-beats"), text("span", "planned cuts", "score-key score-cuts"));
      draw();
    } catch (error) {
      box.replaceChildren(text("summary", "Watch the song conduct"), text("p", error.message, "muted"));
    }
  });
  return box;
}
async function loadOutputs() {
  const outputs = await (await api("/api/outputs")).json();
  scoreViews.forEach(view => view.dispose());
  scoreViews.clear();
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

    card.append(video);
    if (output.kind === "video") card.append(scoreView(output, video));
    card.append(text("h2", output.title), text("p", `${output.kind} · ${Number(output.duration).toFixed(1)} seconds`));
    if (output.quality_warnings?.length) {
      const warning = text("div", "", "quality-warning", "Automatic motion and framing check results");
      warning.setAttribute("role", "note");
      warning.append(text("strong", "Quality check: "), output.quality_warnings.join(" · "));
      card.append(warning);
    }
    card.append(download, upscale);
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
  writer_api_profile: "Writer API profile", vision_api_profile: "Vision API profile", video_api_profile: "Video API profile",
  auto_updates: "Automatic updates",
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

  for (const role of ["writer", "vision", "video"]) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "quiet";
    button.textContent = `Save configured ${role} API as a profile`;
    button.onclick = handle(async () => {
      const name = window.prompt(`Profile ID for the saved ${role} settings (lowercase letters, numbers, underscores or hyphens). Save your settings and key first.`);
      if (!name) return;
      await json("/api/api-profiles", {name, role}, "POST");
      await loadSettings();
      notice("API profile saved privately. Select it and save Settings to activate it.");
    });
    fields.push(button);
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
    request.vision_quality_check = Boolean(form.elements.vision_quality_check?.checked);
    request.content = {};
    for (const category of Object.keys(catalog.ratings)) { request.content[category] = request["rating_" + category]; delete request["rating_" + category]; }
    if (currentCustomVocab && Object.keys(currentCustomVocab).length) {
      request.custom_vocabulary = currentCustomVocab;
    }
  }
  if (request.kind === "ident") request.ident_seconds = Number(request.ident_seconds);

  const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector(".action-bar .primary") || form.querySelector("button.primary");
  const originalHtml = submitBtn ? submitBtn.innerHTML : null;
  const originalCursor = document.body.style.cursor;

  let busyText = "Processing preview…";
  let noticeMsg = "Generating preview quote…";
  if (request.kind === "video") {
    busyText = "Analyzing audio & planning…";
    noticeMsg = "Analyzing audio track and planning production cuts… This may take a few moments.";
  } else if (request.kind === "harvest") {
    busyText = "Analyzing references…";
    noticeMsg = "Analyzing reference images for style harvest…";
  } else if (request.kind === "ident") {
    busyText = "Composing ident plan…";
    noticeMsg = "Composing ident animation plan and preview quote…";
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-busy", "true");
    submitBtn.classList.add("processing");
    submitBtn.innerHTML = `${busyText} <span class="spinner" aria-hidden="true"></span>`;
  }
  document.body.style.cursor = "wait";
  notice(noticeMsg);

  try {
    logSession(`Preview requested for kind='${request.kind}' backend='${request.backend}'`);
    currentQuote = await json("/api/quote", request);
    logSession(`Preview ready: quote_id='${currentQuote.id}' estimate=$${Number(currentQuote.estimate_usd).toFixed(2)}`);
    if ($("#notice") && $("#notice").textContent === noticeMsg) {
      notice("");
    }
    showQuote(request, currentQuote);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.removeAttribute("aria-busy");
      submitBtn.classList.remove("processing");
      if (originalHtml !== null) submitBtn.innerHTML = originalHtml;
    }
    document.body.style.cursor = originalCursor;
  }
}

function showQuote(request, quote) {
  currentQuote = quote;
  const summary = $("#quote-summary"); summary.replaceChildren();
  summary.append(text("p", request.kind === "harvest" ? "One visual style harvest." : `${currentQuote.clips} clips · ${currentQuote.seconds.toFixed(1)} seconds of ${request.kind === "ident" ? "ident" : "music"}.`),
                 text("h2", `Estimated provider cost: $${Number(currentQuote.estimate_usd).toFixed(2)}`), text("p", currentQuote.note, "muted"));
  if (request.vision_quality_check) {
    summary.append(text("p", "Vision quality check on: after rendering, your local vision model inspects sampled frames. "
      + "This adds several minutes and restarts ComfyUI; free local passages may be re-rendered once.", "muted"));
  }
  if (currentQuote.analysis && request.kind === "video") {
    const a = currentQuote.analysis;
    summary.append(text("p", `Detected tempo: ${a.tempo_bpm.toFixed(1)} BPM · ${a.beats} beats · ${a.downbeats} downbeats · ${a.sections} sections · ${a.shots} shots · ${a.width} × ${a.height}`));
    for (const passage of currentQuote.segments) {
      summary.append(text("p", `${(passage.song_start_frame / 24).toFixed(2)}s · ${passage.section_label} · ${passage.montage_type.replaceAll("_", " ")} · ${passage.shots.length} shots`));
    }
  }
  $("#consent").checked = false; $("#preview-dialog").showModal();
}

function renderServices(services) {
  if (!services || typeof services !== "object") return;
  const entries = [
    { id: "laya", data: services.laya },
    { id: "writer", data: services.writer },
    { id: "comfy", data: services.comfy },
    { id: "vision", data: services.vision }
  ];
  for (const { id, data } of entries) {
    if (!data) continue;
    const dot = $(`#service-dot-${id}`);
    const badge = $(`#service-badge-${id}`);
    const detail = $(`#service-detail-${id}`);
    const card = $(`#service-card-${id}`);

    const activity = data.activity || (data.available ? "sleeping" : "offline");

    if (dot) {
      dot.className = `service-pulse-dot dot-${activity}`;
    }

    if (badge) {
      badge.className = `service-badge badge-${activity}`;
      if (activity === "processing") {
        badge.textContent = "PROCESSING";
      } else if (activity === "sleeping") {
        badge.textContent = "SLEEPING (READY)";
      } else if (activity === "missing") {
        badge.textContent = "NEEDS SETUP";
      } else {
        badge.textContent = "OFFLINE";
      }
    }

    if (detail) {
      detail.textContent = data.detail || (data.available ? "Ready" : "Offline");
      detail.title = data.detail || "";
    }

    if (card) {
      card.classList.toggle("card-processing", activity === "processing");
      card.classList.toggle("card-missing", activity === "missing");
    }
  }
}

async function refreshServices(force = false) {
  const btn = $("#refresh-services");
  try {
    if (btn) btn.disabled = true;
    const resp = await api(`/api/services/status${force ? "?force=true" : ""}`);
    if (resp.ok) {
      const data = await resp.json();
      renderServices(data);
    }
  } catch (err) {
    console.debug("Failed to fetch service status", err);
  } finally {
    if (btn) btn.disabled = false;
  }
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
  if (status.services) {
    renderServices(status.services);
  }
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
      sseSource.addEventListener("log", event => {
        try {
          const data = JSON.parse(event.data);
          if (!$("#operation-log").hidden && data.message) {
            const logElem = $("#operation-log");
            if (logElem && !logElem.textContent.includes(data.message)) {
              logElem.textContent += "\n" + data.message;
            }
          }
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

async function loadUpdateStatus() {
  try {
    const status = await (await api("/api/update")).json();
    const banner = $("#update-banner");
    if (!status.available && !["updated", "failed", "unavailable"].includes(status.state)) return;
    $("#update-message").textContent = status.message + (status.available && status.available_version && status.available_version !== "unknown" ? ` Available version: ${status.available_version}.` : "");
    const link = $("#update-repository");
    if (status.repository_url) {
      const url = new URL(status.repository_url);
      if (["https:", "http:"].includes(url.protocol)) {
        link.href = url.href;
        link.hidden = false;
      }
    }
    banner.hidden = false;
  } catch { /* Update availability must not block the studio UI. */ }
}

async function initialize() {
  initTooltips();
  setupOapGuide();
  setupLlamaGuide();
  setupVocabGuide();
  loadUpdateStatus();
  const refreshBtn = $("#refresh-services");
  if (refreshBtn) refreshBtn.onclick = () => refreshServices(true);
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
    const agreementLabel = text("label", name.replaceAll("_", " "), "", `Project content rating for ${name.replaceAll("_", " ")}`);
    const agreementSelect = document.createElement("select");
    agreementSelect.name = "content_" + name;
    agreementSelect.append(...levels.map(level => option(level, level)));
    agreementLabel.append(agreementSelect);
    $(".agreement-ratings").append(agreementLabel);
  }
  const [settings] = await Promise.all([loadSettings(), loadActors(), loadStyles(), loadOutputs(), loadAgreements()]);
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
    const btn = $("#resume-production");
    const orig = btn ? btn.innerHTML : null;
    try {
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML = 'Reviewing resume… <span class="spinner" aria-hidden="true"></span>';
      }
      notice("Loading resume preview…");
      const quote = await json("/api/resume/quote", {run_id: currentRun});
      if ($("#notice") && $("#notice").textContent === "Loading resume preview…") notice("");
      showQuote({kind: quote.kind}, quote);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        if (orig !== null) btn.innerHTML = orig;
      }
    }
  });
  $("#start-production").onclick = handle(async () => {
    if (!$("#consent").checked) throw new Error("Accept the preview before starting");
    const btn = $("#start-production");
    const orig = btn ? btn.innerHTML : null;
    try {
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
        btn.innerHTML = 'Starting production… <span class="spinner" aria-hidden="true"></span>';
      }
      sessionLogs.length = 0;
      if ($("#operation-log")) {
        $("#operation-log").textContent = "Starting production…\n";
      }
      logSession(`Starting production for quote '${currentQuote.id}'`);
      const started = await json("/api/start", {quote_id: currentQuote.id, consent: true});
      if (started && started.id) currentRun = started.id;
      $("#preview-dialog").close();
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
        if (orig !== null) btn.innerHTML = orig;
      }
    }
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

    $$("#oap-helper-dialog .oap-tab-btn").forEach(tabBtn => {
      tabBtn.onclick = () => {
        const tabId = tabBtn.dataset.tab;
        $$("#oap-helper-dialog .oap-tab-btn").forEach(b => b.classList.toggle("active", b === tabBtn));
        $$("#oap-helper-dialog .oap-tab-content").forEach(content => {
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

  let vocabDocLoaded = false;
  async function loadVocabGuideMarkdown() {
    if (vocabDocLoaded) return;
    const rawPre = $("#vocab-guide-raw");
    if (!rawPre) return;
    try {
      const resp = await api("/api/vocabulary/guide");
      if (resp.ok) {
        const data = await resp.json();
        rawPre.textContent = data.markdown || "Guide content empty.";
        vocabDocLoaded = true;
      } else {
        rawPre.textContent = "Could not load the vocabulary guide.";
      }
    } catch {
      rawPre.textContent = "Error fetching vocabulary guide from server.";
    }
  }

  function setupVocabGuide() {
    const dialog = $("#vocab-helper-dialog");
    if (!dialog) return;

    $$(".vocab-help-btn").forEach(btn => {
      btn.onclick = () => {
        loadVocabGuideMarkdown();
        dialog.showModal();
      };
    });

    $$(".close-vocab-dialog").forEach(btn => {
      btn.onclick = () => {
        dialog.close();
      };
    });

    $$(".nav-to-vocab-btn").forEach(btn => {
      btn.onclick = () => {
        if (dialog.open) dialog.close();
        const customizerDialog = $("#vocabulary-dialog");
        if (customizerDialog) {
          const openBtn = $("#open-vocab-dialog");
          if (openBtn) openBtn.click();
          else customizerDialog.showModal();
        }
      };
    });

    $$("#vocab-helper-dialog .vocab-tab-btn").forEach(tabBtn => {
      tabBtn.onclick = () => {
        const tabId = tabBtn.dataset.tab;
        $$("#vocab-helper-dialog .vocab-tab-btn").forEach(b => b.classList.toggle("active", b === tabBtn));
        $$("#vocab-helper-dialog .oap-tab-content").forEach(content => {
          const matches = content.id === `tab-${tabId}`;
          content.classList.toggle("active", matches);
          content.hidden = !matches;
        });
        if (tabId === "vocab-doc") {
          loadVocabGuideMarkdown();
        }
      };
    });

    const copyBtn = $("#copy-vocab-doc-btn");
    if (copyBtn) {
      copyBtn.onclick = handle(async () => {
        await loadVocabGuideMarkdown();
        const rawPre = $("#vocab-guide-raw");
        const text = rawPre ? rawPre.textContent : "";
        if (!text || text.startsWith("Error") || text.startsWith("Could not")) {
          throw new Error("No guide document available to copy.");
        }
        if (!await copyToClipboard(text)) throw new Error("Could not copy document to clipboard.");
        notice("Vocabulary Architecture Guide copied to clipboard.");
        const status = $("#vocab-doc-status");
        if (status) {
          status.textContent = "Copied to clipboard!";
          setTimeout(() => { if (status) status.textContent = ""; }, 3000);
        }
      });
    }
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
  $("#agreement-form").onsubmit = handle(async event => {
    const values = Object.fromEntries(new FormData(event.target));
    const body = {content: {}};
    for (const [key, value] of Object.entries(values)) {
      if (key.startsWith("content_")) body.content[key.slice(8)] = value; else body[key] = value;
    }
    await json("/api/agreements", body);
    event.target.elements.agreement_id.value = "";
    await loadAgreements();
    notice("Agreement drafted. Sign as Director, then send the bundle to the Agent to countersign.");
  });
  $("#import-agreement").onclick = handle(async () => {
    const file = $("#agreement-file").files[0]; if (!file) throw new Error("Choose a signed agreement.json first");
    const body = new FormData();
    body.set("filename", await upload(file, "agreement"));
    const result = await (await api("/api/agreements/import", {method: "POST", body})).json();
    $("#agreement-file").value = "";
    await loadAgreements();
    notice(result.complete ? "Countersigned agreement imported; both signatures verify." : "Signatures imported; the agreement is not yet signed by both parties.");
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
    raw.auto_updates = event.target.elements.auto_updates.checked;
    raw.vision_call_estimate = Number(raw.vision_call_estimate);
    raw.writer_call_estimate = Number(raw.writer_call_estimate);
    if (Object.keys(h3_models).length) raw.h3_models = h3_models;
    await json("/api/settings", raw, "PUT");
    await loadSettings();
    await refreshServices(true);
    notice("Settings saved.");
  });
  $("#key-form").onsubmit = handle(async event => { await json("/api/key", Object.fromEntries(new FormData(event.target)), "PUT"); event.target.elements.value.value = ""; await loadSettings(); await refreshServices(true); notice("Key saved locally. The settings API does not return it."); });
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
  await refreshServices();
  setupVocabularyCustomizer();
  setInterval(() => { refreshServices(); }, 8000);
}
initialize().catch(error => notice(error.message));

let vocabDataCache = null;
let vocabActiveCategory = "settings";
let vocabWorkingDraft = {};

function updateVocabCustomBadge() {
  const badge = $("#vocab-custom-badge");
  if (!badge) return;
  const count = Object.keys(currentCustomVocab || {}).length;
  if (count > 0) {
    badge.textContent = `${count} customized`;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

async function loadVocabularyCatalog(force = false) {
  if (!vocabDataCache || force) {
    vocabDataCache = await (await api("/api/vocabulary")).json();
    populateVocabProfileSelects();
  }
  return vocabDataCache;
}

function populateVocabProfileSelects() {
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

function setupVocabularyCustomizer() {
  const dialog = $("#vocabulary-dialog");
  const openBtn = $("#open-vocab-dialog");
  if (!dialog || !openBtn) return;

  loadVocabularyCatalog().catch(() => {});

  openBtn.onclick = handle(async () => {
    await loadVocabularyCatalog();
    vocabWorkingDraft = JSON.parse(JSON.stringify(currentCustomVocab || {}));
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
      currentCustomVocab = JSON.parse(JSON.stringify(vocabWorkingDraft));
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

function updateDeletePresetBtnVisibility() {
  const deleteBtn = $("#vocab-delete-preset-btn");
  const selected = $("#vocab-dialog-preset-select")?.value;
  if (!deleteBtn) return;
  if (selected && selected !== "full" && selected !== "reduced_flashing") {
    deleteBtn.style.display = "inline";
  } else {
    deleteBtn.style.display = "none";
  }
}

function renderVocabTabs() {
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

function selectVocabCategory(cat) {
  saveActiveCategoryCustomText();
  vocabActiveCategory = cat;
  $$(".vocab-tab-btn").forEach(b => b.classList.toggle("active", b.dataset.category === cat));
  renderVocabCategoryContent(cat);
}

function renderVocabCategoryContent(cat) {
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

function filterCheckboxGrid(term) {
  const grid = $("#vocab-checkbox-grid");
  if (!grid) return;
  const q = term.toLowerCase().trim();
  grid.querySelectorAll(".vocab-item-label").forEach(label => {
    const match = !q || label.textContent.toLowerCase().includes(q);
    label.style.display = match ? "flex" : "none";
  });
}

function saveActiveCategoryCustomText() {
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

function updateActiveCategoryCount() {
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

function updateTabBadges() {
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

function cleanWorkingDraft() {
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
