"use strict";
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
let catalog, currentQuote, currentOap, lastState, currentRun, upscaleSource;
const formFiles = new WeakMap();

function notice(message) {
  $("#notice").textContent = message; $("#notice").hidden = !message;
  $$(".dialog-error").forEach(node => { node.textContent = message; node.hidden = !message; });
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail); } catch {}
    throw new Error(message);
  }
  return response;
}
async function json(path, body, method = "POST") {
  return (await api(path, {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})).json();
}
function handle(fn) { return async event => { event?.preventDefault(); try { notice(""); await fn(event); } catch (error) { notice(error.message); } }; }
function option(value, label) { const node = document.createElement("option"); node.value = value; node.textContent = label; return node; }
function text(tag, value, className) { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; }
function panel(name) {
  $$(".panel").forEach(node => node.hidden = node.id !== "panel-" + name);
  $$(".nav[data-panel]").forEach(node => { node.classList.toggle("active", node.dataset.panel === name); node.setAttribute("aria-current", node.dataset.panel === name ? "page" : "false"); });
}
async function upload(file, kind) {
  const body = new FormData(); body.append("file", file);
  return (await (await api("/api/upload/" + kind, {method: "POST", body})).json()).file;
}

function resolutionSelect(form) {
  const backend = form.querySelector(".backend-select").value;
  const select = form.querySelector(".resolution-select");
  const old = select.value;
  select.replaceChildren(...catalog.backends[backend].resolutions.map(value => option(value, value)));
  if ([...select.options].some(item => item.value === old)) select.value = old;
}

async function loadStyles() {
  const styles = await (await api("/api/styles")).json();
  $$(".style-select").forEach(select => { const old = select.value; select.replaceChildren(...styles.map(style => option(style.id, style.name))); if (styles.some(x => x.id === old)) select.value = old; });
  $("#style-list").replaceChildren(...styles.map(style => { const card = text("article", "", "card"); card.append(text("h2", style.name), text("p", style.direction)); return card; }));
}
async function loadActors() {
  const actors = await (await api("/api/actors")).json();
  $$(".actor-select").forEach(select => { const old = [...select.selectedOptions].map(x => x.value); select.replaceChildren(...actors.map(actor => { const node = option(actor.id, actor.name); node.selected = old.includes(actor.id); return node; })); });
  $("#actor-list").replaceChildren(...actors.map(actor => {
    const card = text("article", "", "card"), image = document.createElement("img");
    image.src = `/api/actors/${encodeURIComponent(actor.id)}/reference`; image.alt = actor.name + " reference"; image.loading = "lazy";
    const button = text("button", "Export OAP package", "secondary");
    button.onclick = handle(async () => {
      const response = await api(`/api/actors/${encodeURIComponent(actor.id)}/export`, {method: "POST"});
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = actor.id + ".oap"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
    });
    card.append(image, text("h2", actor.name), text("p", actor.description), text("p", actor.oap ? "OAP imported · original package preserved" : "OAP ready · signed on export"), button);
    return card;
  }));
  if (!actors.length) $("#actor-list").append(text("div", "Your cast starts here. Create an actor or import a full OAP package below.", "empty"));
}
async function loadOutputs() {
  const outputs = await (await api("/api/outputs")).json();
  $("#output-list").replaceChildren(...outputs.map(output => {
    const card = text("article", "", "card"), video = document.createElement("video");
    video.src = "/api/media/" + output.file; video.controls = true; video.preload = "metadata";
    const download = text("a", "Download", "download"); download.href = "/api/media/" + output.file + "?download=true";
    const upscale = text("button", "Topaz upscale ↗", "quiet"); upscale.onclick = () => { upscaleSource = output.file; $("#upscale-dialog").showModal(); };
    card.append(video, text("h2", output.title), text("p", `${output.kind} · ${Number(output.duration).toFixed(1)} seconds`), download, upscale); return card;
  }));
  if (!outputs.length) $("#output-list").append(text("div", "Your finished videos and idents will appear here.", "empty"));
  $$(".ident-select").forEach(select => { const old = select.value; select.replaceChildren(option("", "None"), ...outputs.filter(output => output.kind === "ident").map(output => option(output.file, output.title))); if ([...select.options].some(item => item.value === old)) select.value = old; });
}

const settingLabels = {
  backend: "Default renderer", comfy_url: "ComfyUI service URL", comfy_input: "ComfyUI input folder (shared local path)",
  workflow_path: "H3 API workflow JSON path", workflow_map_path: "Workflow binding map JSON path",
  vision_url: "Vision service URL (OpenAI-compatible /v1)", vision_model: "Vision model name", vision_key_env: "Vision credential name",
  vision_call_estimate: "Vision estimate per call, USD (0 for local)", topaz_executable: "Installed Topaz FFmpeg executable path", topaz_models: "Installed Topaz models folder"
};
async function loadSettings() {
  const data = await (await api("/api/settings")).json();
  $("#settings-fields").replaceChildren(...Object.entries(data.settings).map(([name, value]) => {
    const label = text("label", settingLabels[name] || name);
    let input;
    if (name === "backend") { input = document.createElement("select"); input.append(...Object.entries(catalog.backends).map(([key, card]) => option(key, card.name))); }
    else { input = document.createElement("input"); input.type = name === "vision_call_estimate" ? "number" : "text"; if (input.type === "number") { input.min = "0"; input.max = "100"; input.step = "0.001"; } }
    input.name = name; input.value = value; if (name === "vision_key_env") input.readOnly = true; label.append(input); return label;
  }));
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
    request.segment_seconds = Number(request.segment_seconds);
    request.bpm = request.bpm ? Number(request.bpm) : null;
    request.content = {};
    for (const category of Object.keys(catalog.ratings)) { request.content[category] = request["rating_" + category]; delete request["rating_" + category]; }
  }
  if (request.kind === "ident") request.ident_seconds = Number(request.ident_seconds);
  currentQuote = await json("/api/quote", request);
  const summary = $("#quote-summary"); summary.replaceChildren();
  summary.append(text("p", request.kind === "harvest" ? "One visual style harvest." : `${currentQuote.clips} clips · ${currentQuote.seconds.toFixed(1)} seconds of ${request.kind === "ident" ? "ident" : "music"}.`),
                 text("h2", `Estimated provider cost: $${Number(currentQuote.estimate_usd).toFixed(2)}`), text("p", currentQuote.note, "muted"));
  $("#consent").checked = false; $("#preview-dialog").showModal();
}

async function poll() {
  try {
    const status = await (await api("/api/status")).json();
    currentRun = status.id;
    const busy = ["running", "cancelling"].includes(status.state);
    $("#status-title").textContent = status.state === "idle" ? "READY WHEN YOU ARE" : status.state.toUpperCase();
    $("#status-message").textContent = status.message || "One idea. One production at a time.";
    $("#progress").value = status.progress || 0;
    $("#cancel").hidden = !busy; $("#show-log").hidden = !status.id;
    $$(".operation-action").forEach(button => button.disabled = busy);
    if (lastState && lastState !== status.state && !busy) { await Promise.all([loadActors(), loadStyles(), loadOutputs()]); }
    lastState = status.state;
    if (!$("#operation-log").hidden && currentRun) $("#operation-log").textContent = (await (await api("/api/log/" + currentRun)).json()).log;
  } catch (error) { $("#status-message").textContent = "Connection unavailable. The server may have stopped."; }
  setTimeout(poll, 2000);
}

async function initialize() {
  catalog = await (await api("/api/catalog")).json();
  const version = await (await api("/api/version")).json();
  $("#version").textContent = version.version; $("#oap-version").textContent = catalog.oap_version;
  $$(".backend-select").forEach(select => { select.append(...Object.entries(catalog.backends).map(([key, card]) => option(key, card.name))); select.onchange = () => resolutionSelect(select.closest("form")); });
  for (const [name, levels] of Object.entries(catalog.ratings)) {
    const label = text("label", name.replaceAll("_", " ")), select = document.createElement("select"); select.name = "rating_" + name; select.append(...levels.map(level => option(level, level))); label.append(select); $(".ratings").append(label);
  }
  const [settings] = await Promise.all([loadSettings(), loadActors(), loadStyles(), loadOutputs()]);
  $$(".backend-select").forEach(select => { select.value = settings.backend; resolutionSelect(select.closest("form")); });
  $$(".nav[data-panel]").forEach(button => button.onclick = () => panel(button.dataset.panel));
  const teasers = {"Short films": "From screenplay to screen, with the full studio's film production tools.", "Micro Drama": "A home for episodic stories and serial drama in the full studio.", "Hodge TV": "Channel-surf broadcasts and programme variety in the full studio.", "The cutting room": "Editing and production refinement in the full studio.", "The Vault": "A library of archival footage in the full studio."};
  $$(".teaser").forEach(button => button.onclick = () => { $("#teaser-title").textContent = button.dataset.feature; $("#teaser-description").textContent = teasers[button.dataset.feature]; panel("teaser"); });
  $("#back-to-video").onclick = () => panel("video");
  $$(".production-form").forEach(form => {
    formFiles.set(form, {references: [], pending: 0});
    form.onsubmit = handle(() => preview(form));
    const song = form.querySelector(".song-input");
    if (song) song.onchange = handle(async () => {
      const selected = song.files[0]; if (!selected) return;
      const state = formFiles.get(form); state.song = undefined; state.pending++;
      song.disabled = true; form.querySelector(".song-receipt").textContent = "Uploading " + selected.name + "…";
      try { state.song = await upload(selected, "song"); form.querySelector(".song-receipt").textContent = "Uploaded: " + selected.name; }
      catch (error) { form.querySelector(".song-receipt").textContent = "Upload failed; select the song again."; throw error; }
      finally { state.pending--; song.disabled = false; }
    });
    form.querySelector(".refs-input").onchange = handle(async event => {
      const files = [...event.target.files];
      if (files.length > 9) throw new Error("Choose at most nine reference images");
      const state = formFiles.get(form); state.references = []; state.pending++;
      event.target.disabled = true; form.querySelector(".clear-refs").disabled = true;
      form.querySelector(".refs-receipt").textContent = "Uploading reference images…";
      try {
        for (const file of files) state.references.push(await upload(file, "reference"));
        form.querySelector(".refs-receipt").textContent = files.map(file => file.name).join(" · ") || "No reference images";
      } catch (error) { state.references = []; form.querySelector(".refs-receipt").textContent = "Upload failed; select references again."; throw error; }
      finally { state.pending--; event.target.disabled = false; form.querySelector(".clear-refs").disabled = false; }
    });
    form.querySelector(".clear-refs").onclick = () => { formFiles.get(form).references = []; form.querySelector(".refs-input").value = ""; form.querySelector(".refs-receipt").textContent = "No reference images"; };
  });
  $("#start-production").onclick = handle(async () => {
    if (!$("#consent").checked) throw new Error("Accept the preview before starting");
    await json("/api/start", {quote_id: currentQuote.id, consent: true}); $("#preview-dialog").close();
  });
  $("#cancel").onclick = handle(() => api("/api/cancel", {method: "POST"}));
  $("#show-log").onclick = handle(async () => { $("#operation-log").hidden = !$("#operation-log").hidden; if (currentRun) $("#operation-log").textContent = (await (await api("/api/log/" + currentRun)).json()).log; });
  $("#actor-form").onsubmit = handle(async event => { await api("/api/actors", {method: "POST", body: new FormData(event.target)}); event.target.reset(); await loadActors(); });
  $("#style-form").onsubmit = handle(async event => { await json("/api/styles", Object.fromEntries(new FormData(event.target))); event.target.reset(); await loadStyles(); });
  $("#inspect-oap").onclick = handle(async () => {
    const file = $("#oap-file").files[0]; if (!file) throw new Error("Choose an OAP package first");
    currentOap = await upload(file, "oap");
    const report = await (await api(`/api/oap/inspect/${currentOap}?allow_unsigned=${$("#allow-unsigned").checked}`)).json();
    $("#oap-report").textContent = JSON.stringify(report, null, 2); $("#oap-report").hidden = false; $("#oap-import-form").hidden = false;
  });
  $("#oap-import-form").onsubmit = handle(async event => {
    const body = new FormData(event.target); body.set("filename", currentOap); body.set("allow_unsigned", String($("#allow-unsigned").checked)); body.set("accept_unknown", String(event.target.elements.accept_unknown.checked));
    await api("/api/oap/import", {method: "POST", body}); event.target.hidden = true; $("#oap-report").hidden = true; await loadActors();
  });
  $("#settings-form").onsubmit = handle(async event => { const body = Object.fromEntries(new FormData(event.target)); body.vision_call_estimate = Number(body.vision_call_estimate); await json("/api/settings", body, "PUT"); notice("Settings saved."); });
  $("#key-form").onsubmit = handle(async event => { await json("/api/key", Object.fromEntries(new FormData(event.target)), "PUT"); event.target.elements.value.value = ""; await loadSettings(); notice("Key saved locally. The settings API does not return it."); });
  $("#upscale-form").onsubmit = handle(async event => { const body = Object.fromEntries(new FormData(event.target)); body.scale = Number(body.scale); await json("/api/upscale", {...body, source: upscaleSource}); $("#upscale-dialog").close(); });
  poll();
}
initialize().catch(error => notice(error.message));
