// Worlds: build, grow, review and use persistent world canon. Text from the server is only ever shown with textContent.

import { $, $$, api, handle, json, notice, option, saveDownload, text, upload } from "./core.js";

const LIST_LABELS = {
  core_laws: "Core laws", locations: "Locations", practices: "Practices and rituals", objects: "Objects and anomalies",
  factions: "Factions and institutions", ecology_rules: "Ecological rules", moral_ambiguities: "Moral ambiguities",
  open_threads: "Open threads", do_not_contradict: "Never contradict"
};
const POOL_LABELS = {
  settings: "Settings", lighting: "Lighting", mechanisms: "Mechanisms", costume: "Wardrobe",
  practical_effects: "Practical effects", subject_types: "Subjects", tonal_registers: "Tone"
};

// --- Pure helpers ---

export const fieldLabel = field => {
  const [name, kind] = field.split(" ");
  return LIST_LABELS[name] || (POOL_LABELS[name] ? `${POOL_LABELS[name]} (${kind})` : name.replace(/_/g, " "));
};

export const changeLines = changes => changes.flatMap(change => [
  ...change.added.map(item => ({ sign: "+", field: fieldLabel(change.field), item })),
  ...change.removed.map(item => ({ sign: "−", field: fieldLabel(change.field), item })),
  ...change.changed.map(item => ({ sign: "~", field: fieldLabel(change.field), item }))
]);

export const runIdOf = outputFile => String(outputFile).split("/")[0];

export function harvestRequest(form, uploaded) {
  const mode = form.elements.world_mode.value;
  return {
    kind: "world_harvest", world_mode: mode, title: mode === "create" ? form.elements.title.value.trim() : "",
    world_id: mode === "create" ? form.elements.world_new_id.value.trim() : form.elements.world_existing.value,
    direction: form.elements.direction.value, world_images: uploaded.images, world_videos: uploaded.videos,
    world_lore: uploaded.lore, world_runs: $$("#world-runs input:checked").map(box => box.value)
  };
}

const node = (tag, className, children = []) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.append(...children);
  return element;
};

const button = (label, onclick, className = "quiet", tooltip = "") => {
  const element = text("button", label, className, tooltip || undefined);
  element.type = "button";
  element.onclick = handle(onclick);
  return element;
};

// --- Rendering ---

function listBlock(title, items) {
  if (!items.length) return null;
  return node("div", "world-block", [text("h4", title), node("ul", "", items.map(item => text("li", item)))]);
}

function ledgerView(ledger) {
  const subjects = ledger.subjects.map(s => `${s.designation}: ${s.canon}`);
  const pools = Object.entries(POOL_LABELS).flatMap(([table, label]) => {
    const pool = ledger.pools[table];
    return [listBlock(`${label} — included`, pool.include), listBlock(`${label} — kept out`, pool.exclude)];
  });
  return [text("p", ledger.seed_sentence, "muted"), listBlock("Subjects", subjects),
    ...Object.entries(LIST_LABELS).map(([key, label]) => listBlock(label, ledger[key])), ...pools]
    .filter(Boolean);
}

function diffView(changes) {
  const lines = changeLines(changes);
  if (!lines.length) return text("p", "No changes to the world.", "muted");
  return node("ul", "world-diff", lines.map(line => {
    const row = node("li", `world-diff-${line.sign === "+" ? "add" : line.sign === "−" ? "remove" : "change"}`);
    row.append(text("strong", `${line.sign} ${line.field}: `), document.createTextNode(line.item));
    return row;
  }));
}

async function showDetail(id) {
  const [ledger, versions] = await Promise.all(
    [`/api/worlds/${id}`, `/api/worlds/${id}/versions`].map(path => api(path).then(response => response.json())));
  const detail = $("#world-detail");
  const rollbacks = versions.slice(0, -1).reverse().map(item => button(`Restore v${item.version}`, async () => {
    await json(`/api/worlds/${id}/rollback`, { version: item.version });
    notice(`Restored v${item.version} as a new version.`);
    await loadWorlds();
    await showDetail(id);
  }, "quiet", "Save this earlier version as the newest one"));
  detail.replaceChildren(text("h3", `${ledger.name} — version ${ledger.version}`), ...ledgerView(ledger),
    node("div", "buttons", rollbacks), button("Close", () => { detail.hidden = true; }));
  detail.hidden = false;
}

function worldRow(world) {
  const buttons = node("div", "buttons", [
    button("Open", () => showDetail(world.id), "secondary", "Read this world"),
    button("Export", async () => saveDownload(await api(`/api/worlds/${world.id}/export`), `${world.id}.world.json`), "quiet", "Save a copy of this world"),
    button("Delete", async () => {
      if (!confirm(`Delete the world "${world.name}" and all of its versions? Your videos are kept.`)) return;
      await api(`/api/worlds/${world.id}`, { method: "DELETE" });
      notice(`Deleted ${world.name}.`);
      await loadWorlds();
    }, "quiet", "Delete this world and its versions")
  ]);
  return node("div", "world-row", [
    node("div", "", [text("strong", world.name), text("span", `  v${world.version} · ${world.terms} terms · ${world.sources} sources`, "muted")]),
    buttons
  ]);
}

function proposalRow(proposal) {
  const title = proposal.mode === "create" ? `New world: ${proposal.proposed.name}` : `Growth for ${proposal.world_id}`;
  const actions = node("div", "buttons", [
    button("Accept", async () => {
      await api(`/api/worlds/proposals/${proposal.id}/accept`, { method: "POST" });
      notice("Saved as a new version of the world.");
      await loadWorlds();
    }, "primary", "Save these changes as the world's next version"),
    button("Reject", async () => {
      await api(`/api/worlds/proposals/${proposal.id}`, { method: "DELETE" });
      await loadWorlds();
    }, "quiet", "Discard this proposal")
  ]);
  return node("div", "world-proposal", [text("h3", title), diffView(proposal.changes), actions]);
}

// --- Loading ---

function fillSelect(select, worlds, blank) {
  if (!select) return;
  const previous = select.value;
  select.replaceChildren(...(blank ? [option("", blank)] : []), ...worlds.map(w => option(w.id, w.name)));
  if ([...select.options].some(item => item.value === previous)) select.value = previous;
}

export async function loadWorlds() {
  const worlds = await (await api("/api/worlds")).json();
  const list = $("#worlds-list");
  if (!list) return worlds;
  list.replaceChildren(...(worlds.length ? worlds.map(worldRow) : [text("p", "No worlds yet. Build one below.", "muted")]));
  fillSelect($("#world-select"), worlds, "No world");
  fillSelect($("#world-form")?.elements.world_existing, worlds, "");
  const pending = await (await api("/api/worlds/proposals")).json();
  const full = await Promise.all(pending.map(item => api(`/api/worlds/proposals/${item.id}`).then(r => r.json())));
  $("#world-proposals").replaceChildren(...full.map(proposalRow));
  $("#world-proposals-card").hidden = !full.length;
  return worlds;
}

async function loadRuns() {
  const outputs = await (await api("/api/outputs")).json();
  const box = $("#world-runs");
  const runs = outputs.filter(item => item.kind !== "upscale");
  box.replaceChildren(...(runs.length ? runs.map(item => {
    const label = node("label", "inline");
    const input = node("input");
    input.type = "checkbox";
    input.value = runIdOf(item.file);
    label.append(input, document.createTextNode(` ${item.title || input.value}`));
    return label;
  }) : [document.createTextNode("None yet")]));
}

// --- Form ---

const receipt = (input, target, none) => {
  const update = () => { target.textContent = input.files.length ? [...input.files].map(f => f.name).join(", ") : none; };
  input.addEventListener("change", update);
  update();
};

async function uploadAll(files, kind) {
  const ids = [];
  for (const file of files) ids.push(await upload(file, kind));
  return ids;
}

async function previewHarvest(form, pending) {
  const uploaded = {
    images: await uploadAll($("#world-images").files, "reference"),
    videos: await uploadAll($("#world-videos").files, "video"),
    lore: await uploadAll($("#world-lore").files, "lore")
  };
  const quote = await json("/api/quote", harvestRequest(form, uploaded));
  pending.quote = quote;
  const parts = [uploaded.images.length && `${uploaded.images.length} picture(s)`, uploaded.videos.length && `${uploaded.videos.length} video clip(s)`,
    uploaded.lore.length && `${uploaded.lore.length} text file(s)`, $$("#world-runs input:checked").length && `${$$("#world-runs input:checked").length} finished video(s)`].filter(Boolean);
  $("#world-quote-summary").textContent = `Your vision model will read ${parts.join(", ")} and propose a world for you to review. ` +
    (quote.estimate_usd > 0 ? `Estimated cost $${Number(quote.estimate_usd).toFixed(2)}.` : "No charge for local models.");
  $("#world-consent").checked = false;
  $("#world-start").disabled = true;
  $("#world-quote").hidden = false;
}

async function waitForRun() {
  for (let attempt = 0; attempt < 600; attempt++) {
    const status = await (await api("/api/status")).json();
    if (!["running", "cancelling"].includes(status.state)) return status;
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  return null;
}

export function initWorlds() {
  const form = $("#world-form");
  if (!form) return;
  const pending = { quote: null };
  const sync = () => {
    const creating = form.elements.world_mode.value === "create";
    form.querySelectorAll(".world-new").forEach(item => { item.hidden = !creating; });
    form.querySelectorAll(".world-existing").forEach(item => { item.hidden = creating; });
    $("#world-quote").hidden = true;
  };
  form.elements.world_mode.addEventListener("change", sync);
  receipt($("#world-images"), $("#world-images-receipt"), "No pictures");
  receipt($("#world-videos"), $("#world-videos-receipt"), "No video clips");
  receipt($("#world-lore"), $("#world-lore-receipt"), "No text files");
  $("#world-preview").onclick = handle(() => previewHarvest(form, pending));
  $("#world-consent").onchange = event => { $("#world-start").disabled = !event.target.checked; };
  $("#world-clear").onclick = () => { form.reset(); sync(); $$("#world-runs input").forEach(box => { box.checked = false; }); };
  $("#world-start").onclick = handle(async () => {
    if (!pending.quote) throw new Error("Preview first");
    await json("/api/start", { quote_id: pending.quote.id, consent: true });
    pending.quote = null;
    $("#world-quote").hidden = true;
    notice("Reading the world. A proposal will appear for your review when it finishes.");
    const status = await waitForRun();
    await loadWorlds();
    if (status?.state === "failed") notice(status.message || "The world could not be read.");
  });
  sync();
}

export async function openWorldsPanel() {
  await Promise.all([loadWorlds(), loadRuns()]);
}
