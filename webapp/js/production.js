// Production quote/preview, operation controls, live AI service dock, SSE stream, and update status.

import { $, $$, api, copyToClipboard, handle, json, logSession, notice, state, text, updateLogDisplay, upload } from "./core.js";
import { disposeScoreEditor, mountScoreEditor } from "./score_editor.js";
import { loadActors, loadStyles } from "./library.js";
import { loadOutputs } from "./outputs.js";
import { scheduleSave, updateSongPreview } from "./project.js";

let sseSource = null;
let sseConnected = false;
export const isSseConnected = () => sseConnected;
export const getSseSource = () => sseSource;
let statusTimer = null;
let lastStreamEvent = 0;

// The form has flat subliminal_* fields; the request carries them as one nested object.
export function subliminalFromForm(request) {
  const mode = request.subliminal_mode || "off";
  const times = String(request.subliminal_times || "").split(/[\s,;]+/).filter(Boolean).map(Number);
  if (times.some(value => !Number.isFinite(value) || value < 0)) throw new Error("Flash times are seconds, like 12.5, 40, 55.2");
  if (mode === "image" && !request.subliminal_image) throw new Error("Choose the picture to flash");
  request.subliminal = {
    mode, image: request.subliminal_image || "", text: request.subliminal_text || "",
    frames: Number(request.subliminal_frames) || 2, placement: request.subliminal_placement || "manual", times,
    count: Number(request.subliminal_count) || 3
  };
  for (const key of Object.keys(request)) if (key.startsWith("subliminal_")) delete request[key];
  return request.subliminal;
}

// Only the most recently chosen file may set the flash picture: slower, older uploads must never overwrite it.
export function latestSelection() {
  let current = 0;
  return { begin: () => ++current, isCurrent: token => token === current };
}

export function initSubliminalControls() {
  const form = $("#video-form");
  const mode = form?.elements.subliminal_mode;
  if (!mode) return;
  const fields = form.querySelector(".subliminal-fields");
  const sync = () => {
    fields.hidden = mode.value === "off";
    form.querySelectorAll('[data-sub="text"]').forEach(node => { node.hidden = mode.value !== "text"; });
    form.querySelectorAll('[data-sub="image"]').forEach(node => { node.hidden = mode.value !== "image"; });
    const downbeats = form.elements.subliminal_placement.value === "downbeats";
    form.querySelectorAll('[data-sub="manual"]').forEach(node => { node.hidden = downbeats; });
    form.querySelectorAll('[data-sub="downbeats"]').forEach(node => { node.hidden = !downbeats; });
  };
  mode.addEventListener("change", sync);
  form.elements.subliminal_placement.addEventListener("change", sync);
  const selection = latestSelection();
  form.elements.subliminal_file.addEventListener("change", handle(async () => {
    const file = form.elements.subliminal_file.files[0];
    const mine = selection.begin();
    form.elements.subliminal_image.value = "";                    // the previous picture is no longer selected
    if (!file) { delete form.dataset.subliminalPending; scheduleSave(); return; }
    form.dataset.subliminalPending = "1";
    try {
      const id = await upload(file, "reference");
      if (selection.isCurrent(mine)) form.elements.subliminal_image.value = id;
    } finally {
      if (selection.isCurrent(mine)) delete form.dataset.subliminalPending;
    }
    scheduleSave();
  }));
  sync();
}

export async function preview(form) {
  if (form.dataset.subliminalPending) throw new Error("Wait for the flash picture to finish uploading");
  const data = Object.fromEntries(new FormData(form));
  const files = state.formFiles.get(form) || { references: [] };
  if (files.pending) throw new Error("Wait for the selected files to finish uploading");
  const request = { kind: form.dataset.kind, ...data, references: files.references };
  request.compact_prompts = Boolean(form.elements.compact_prompts?.checked);
  if (request.kind === "video") {
    if (!files.song) throw new Error("Upload your song first");
    request.song = files.song;
    request.actors = [...form.querySelector(".actor-select").selectedOptions].map(item => item.value);
    for (const name of ["megapixels", "beats_per_bar", "bars_per_phrase", "seed", "on_screen"]) {
      request[name] = Number(request[name]);
    }
    subliminalFromForm(request);
    request.mouth_mode = request.mouth_mode || "sealed";
    request.silent_mouths = request.mouth_mode !== "natural";   // older agents read this flag
    request.reuse_prompts = form.elements.reuse_prompts ? form.elements.reuse_prompts.checked : true;
    request.vision_quality_check = Boolean(form.elements.vision_quality_check?.checked);
    request.content = {};
    for (const category of Object.keys(state.catalog.ratings)) {
      request.content[category] = request["rating_" + category];
      delete request["rating_" + category];
    }
    if (state.currentCustomVocab && Object.keys(state.currentCustomVocab).length) {
      request.custom_vocabulary = state.currentCustomVocab;
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
    state.lastRequest = request;
    state.currentQuote = await json("/api/quote", request);
    logSession(`Preview ready: quote_id='${state.currentQuote.id}' estimate=$${Number(state.currentQuote.estimate_usd).toFixed(2)}`);
    if ($("#notice") && $("#notice").textContent === noticeMsg) {
      notice("");
    }
    showQuote(request, state.currentQuote);
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

export function showQuote(request, quote) {
  state.currentQuote = quote;
  const summary = $("#quote-summary");
  summary.replaceChildren();
  summary.append(
    text("p", request.kind === "harvest" ? "One visual style harvest." : `${quote.clips} clips · ${quote.seconds.toFixed(1)} seconds of ${request.kind === "ident" ? "ident" : "music"}.`),
    text("h2", `Estimated provider cost: $${Number(quote.estimate_usd).toFixed(2)}`),
    text("p", quote.note, "muted")
  );
  if (quote.subliminal) {
    summary.append(text("p", `Subliminal flashes: ${quote.subliminal.times.length} × ${quote.subliminal.frames} frame(s) at ${quote.subliminal.times.join(", ")} s. ${quote.subliminal.notice}`, "muted"));
  }
  if (request.clip_quality && request.clip_quality !== "standard") {
    summary.append(text("p", `Studio-quality raw clips (${request.clip_quality === "prores" ? "ProRes 4444" : "FFV1 lossless"}): each passage clip is saved near-lossless for editing. `
      + "Expect much larger files and a little more time; the final video is still encoded from them.", "muted"));
  }
  if (request.vision_quality_check) {
    summary.append(text("p", "Vision quality check on: after rendering, your local vision model inspects sampled frames. "
      + "This adds several minutes and restarts ComfyUI; free local passages may be re-rendered once.", "muted"));
  }
  if (quote.analysis && request.kind === "video") {
    const a = quote.analysis;
    summary.append(text("p", `Detected tempo: ${a.tempo_bpm.toFixed(1)} BPM · ${a.beats} beats · ${a.downbeats} downbeats · ${a.sections} sections · ${a.shots} shots · ${a.width} × ${a.height}`));
    for (const passage of quote.segments) {
      summary.append(text("p", `${(passage.song_start_frame / 24).toFixed(2)}s · ${passage.section_label} · ${passage.montage_type.replaceAll("_", " ")} · ${passage.shots.length} shots`));
    }
  }
  $("#consent").checked = false;
  const dialog = $("#preview-dialog");
  if (!dialog.dataset.scoreEditorBound) {
    dialog.dataset.scoreEditorBound = "1";
    dialog.addEventListener("close", disposeScoreEditor);
  }
  dialog.showModal();
  mountScoreEditor($("#score-editor"), request, quote, {
    onReplan: async (edits, driver, quality, lip) => {
      const next = { ...request, score_edits: edits, analysis_driver: driver || "mix", stem_quality: quality || "standard", ...(lip || {}) };
      state.lastRequest = next;
      const replanned = await json("/api/quote", next);
      logSession(`Re-planned with score edits: quote_id='${replanned.id}'`);
      showQuote(next, replanned);
    },
    onDirty: dirty => {
      const start = $("#start-production");
      if (start) {
        start.disabled = dirty;
        start.title = dirty ? "Re-plan first: your score edits are not in the plan yet" : "";
      }
    }
  }).catch(error => notice(error.message));
}

export function renderServices(services) {
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

export async function refreshServices(force = false) {
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

export async function applyStatus(status) {
  if (!status || !status.state) return;
  state.currentRun = status.id;
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
  if (state.lastState && state.lastState !== status.state && !busy) {
    await Promise.all([loadActors(), loadStyles(), loadOutputs()]);
  }
  state.lastState = status.state;
}

export function setupEventStream() {
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

export async function fallbackPoll() {
  clearTimeout(statusTimer);
  const busy = ["running", "cancelling"].includes(state.lastState);
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

// A fork that changed the protected prompting scheme sees a persistent warning (see docs/PROMPT_SCHEME_PROTECTION.md).
export async function loadSchemeNotice() {
  try {
    const status = await (await api("/api/integrity")).json();
    const banner = $("#scheme-notice");
    if (banner && status.notice) {
      banner.textContent = status.notice;
      banner.hidden = false;
    }
  } catch { /* The notice must not block the studio UI. */ }
}

export async function loadUpdateStatus() {
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

export function initProductionForms() {
  $$(".production-form").forEach(form => {
    state.formFiles.set(form, { references: [], pending: 0 });
    form.onsubmit = handle(() => preview(form));
    const song = form.querySelector(".song-input");
    if (song) {
      song.onchange = handle(async () => {
        const selected = song.files[0];
        if (!selected) return;
        const fState = state.formFiles.get(form);
        if (fState.songObjectUrl) {
          updateSongPreview(form, "");
          URL.revokeObjectURL(fState.songObjectUrl);
          fState.songObjectUrl = undefined;
        }
        fState.songObjectUrl = URL.createObjectURL(selected);
        updateSongPreview(form, fState.songObjectUrl);
        fState.song = undefined;
        fState.songName = undefined;
        fState.pending++;
        song.disabled = true;
        form.querySelector(".song-receipt").textContent = "Uploading " + selected.name + "…";
        try {
          fState.song = await upload(selected, "song");
          fState.songName = selected.name;
          form.querySelector(".song-receipt").textContent = "Uploaded: " + selected.name;
          song.required = false;
          scheduleSave();
        } catch (error) {
          if (fState.songObjectUrl) {
            URL.revokeObjectURL(fState.songObjectUrl);
            fState.songObjectUrl = undefined;
          }
          updateSongPreview(form, "");
          form.querySelector(".song-receipt").textContent = "Upload failed; select the song again.";
          throw error;
        } finally {
          fState.pending--;
          song.disabled = false;
        }
      });
    }
    form.querySelector(".refs-input").onchange = handle(async event => {
      const files = [...event.target.files];
      if (files.length > 9) throw new Error("Choose at most nine reference images");
      const fState = state.formFiles.get(form);
      fState.references = [];
      fState.referenceNames = [];
      fState.pending++;
      event.target.disabled = true;
      form.querySelector(".clear-refs").disabled = true;
      form.querySelector(".refs-receipt").textContent = "Uploading reference images…";
      try {
        for (const file of files) {
          fState.references.push(await upload(file, "reference"));
          fState.referenceNames.push(file.name);
        }
        form.querySelector(".refs-receipt").textContent = files.map(file => file.name).join(" · ") || "No reference images";
        if (form.dataset.kind === "harvest") event.target.required = false;
        scheduleSave();
      } catch (error) {
        fState.references = [];
        fState.referenceNames = [];
        form.querySelector(".refs-receipt").textContent = "Upload failed; select references again.";
        throw error;
      } finally {
        fState.pending--;
        event.target.disabled = false;
        form.querySelector(".clear-refs").disabled = false;
      }
    });
    form.querySelector(".clear-refs").onclick = () => {
      const fState = state.formFiles.get(form);
      fState.references = [];
      fState.referenceNames = [];
      form.querySelector(".refs-input").value = "";
      form.querySelector(".refs-receipt").textContent = "No reference images";
      if (form.dataset.kind === "harvest") form.querySelector(".refs-input").required = true;
      scheduleSave();
    };
  });
}

export function initOperationControls() {
  const refreshBtn = $("#refresh-services");
  if (refreshBtn) refreshBtn.onclick = () => refreshServices(true);

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
      const quote = await json("/api/resume/quote", { run_id: state.currentRun });
      if ($("#notice") && $("#notice").textContent === "Loading resume preview…") notice("");
      showQuote({ kind: quote.kind }, quote);
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
      state.sessionLogs.length = 0;
      if ($("#operation-log")) {
        $("#operation-log").textContent = "Starting production…\n";
      }
      logSession(`Starting production for quote '${state.currentQuote.id}'`);
      const started = await json("/api/start", { quote_id: state.currentQuote.id, consent: true });
      if (started && started.id) state.currentRun = started.id;
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
    return api("/api/cancel", { method: "POST" });
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
    state.sessionLogs.length = 0;
    await api("/api/log/clear", { method: "POST" });
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
      const res = await (await api("/api/cache/clear", { method: "POST" })).json();
      notice(`Prompt cache cleared (${res.count || 0} files removed).`);
      setTimeout(() => { if ($("#notice").textContent.startsWith("Prompt cache cleared")) notice(""); }, 3000);
    });
  }
}

