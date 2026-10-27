// Worlds: build, grow, review and use persistent world canon. Text from the server is only ever shown with textContent.

import { $, $$, api, handle, json, notice, option, saveDownload, text, upload } from "./core.js";
import { cloneDraft, withCustomLines, withToggledBuiltinItem } from "./vocab-model.js";
import { loadVocabularyCatalog } from "./vocabulary.js";

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

// One entry per line, blanks dropped: how the editor turns a textarea into a ledger list.
export const linesOf = value => value.split("\n").map(line => line.trim()).filter(Boolean);

// A world's pools are a custom vocabulary: the Visual Vocabulary editor's draft is {table: {mode, add, exclude}}, here
// add = the world's own terms and exclude = terms kept out.
export const poolsToDraft = pools => Object.fromEntries(Object.entries(pools).map(([table, pool]) =>
  [table, { mode: "replace", add: pool.include, exclude: pool.exclude }]));
export const draftToPools = draft => Object.fromEntries(Object.keys(POOL_LABELS).map(table =>
  [table, { include: draft[table]?.add || [], exclude: draft[table]?.exclude || [] }]));

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

const NOTHING_NEW = "Nothing new: the model found nothing in these references that the world does not already hold. " +
  "Dismiss this, then try again with a direction that names what to look for, or with different material.";

function diffView(changes, empty = NOTHING_NEW) {
  const lines = changeLines(changes);
  if (!lines.length) return text("p", empty, "muted");
  return node("ul", "world-diff", lines.map(line => {
    const row = node("li", `world-diff-${line.sign === "+" ? "add" : line.sign === "−" ? "remove" : "change"}`);
    row.append(text("strong", `${line.sign} ${line.field}: `), document.createTextNode(line.item));
    return row;
  }));
}

// --- Editor ---

const field = (label, control) => { const wrap = node("label", "world-edit-field", [text("span", label)]); wrap.append(control); return wrap; };

function textArea(name, items, rows) {
  const area = node("textarea");
  Object.assign(area, { name, rows, value: items.join("\n") });
  return area;
}

function subjectRow(subject, onChange) {
  const designation = node("input", "world-subject-name");
  const canon = node("input", "world-subject-canon");
  designation.value = subject.designation;
  designation.placeholder = "Name";
  designation.setAttribute("aria-label", "Subject name");
  canon.value = subject.canon;
  canon.placeholder = "What is established about them";
  canon.setAttribute("aria-label", "Subject canon");
  const row = node("div", "world-subject-row", [designation, canon]);
  row.append(button("Remove", () => { row.remove(); onChange(); }, "quiet", "Remove this subject from the edit"));
  return row;
}

const readEditor = (form, version, draft) => ({
  name: form.elements.world_name.value.trim(), seed_sentence: form.elements.seed_sentence.value.trim(),
  ...Object.fromEntries(Object.keys(LIST_LABELS).map(key => [key, linesOf(form.elements[key].value)])),
  subjects: [...form.querySelectorAll(".world-subject-row")].map(row => ({
    designation: row.querySelector(".world-subject-name").value.trim(), canon: row.querySelector(".world-subject-canon").value.trim()
  })).filter(subject => subject.designation),
  pools: draftToPools(draft),
  base_version: version
});

// The Visual Vocabulary editor's look and logic, for one world: a tab per table, the standard terms as checkboxes
// (untick to keep one out), and the world's own terms as text.
function poolsEditor(catalog, pools) {
  let draft = cloneDraft(poolsToDraft(pools));
  let active = Object.keys(POOL_LABELS)[0];
  const element = node("details", "world-edit-pools", [text("summary", "Vocabulary pools: places, light, wardrobe and more")]);
  const body = node("div", "world-pool-body");
  const render = () => {
    const standard = catalog.base[active] || [];
    const known = new Set(standard);
    const entry = draft[active] || { add: [], exclude: [] };
    const tabs = node("div", "vocab-tabs-container", Object.entries(POOL_LABELS).map(([table, label]) => {
      const tab = node("button", `vocab-tab-btn${table === active ? " active" : ""}`, [document.createTextNode(label)]);
      tab.type = "button";
      tab.onclick = () => { active = table; render(); };
      return tab;
    }));
    const grid = node("div", "vocab-checkbox-grid", standard.map(term => {
      const box = node("input");
      Object.assign(box, { type: "checkbox", value: term, checked: !entry.exclude.includes(term) });
      box.onchange = () => { draft = withToggledBuiltinItem(draft, active, term, box.checked, "replace"); };
      return node("label", "vocab-item-label", [box, document.createTextNode(term)]);
    }));
    const own = Object.assign(textArea("own", entry.add, 4), { oninput: () => { draft = withCustomLines(draft, active, own.value, "replace"); } });
    const extra = Object.assign(textArea("extra", entry.exclude.filter(term => !known.has(term)), 2), {
      oninput: () => {
        const current = draft[active] || { mode: "replace", add: [], exclude: [] };
        draft = { ...draft, [active]: { ...current, exclude: [...current.exclude.filter(term => known.has(term)), ...linesOf(extra.value)] } };
      }
    });
    body.replaceChildren(tabs,
      text("p", "Untick a standard term to keep it out of this world.", "muted"), grid,
      field("This world's own terms (one per line)", own),
      field("Other terms to keep out (one per line)", extra));
  };
  render();
  element.append(body);
  return { element, read: () => draft };
}

function editorView(ledger, catalog, close) {
  const id = encodeURIComponent(ledger.id);
  const preview = node("div", "world-edit-preview");
  preview.hidden = true;
  const save = button("Save as new version", async () => {
    const saved = await json(`/api/worlds/${id}`, readEditor(form, ledger.version, pools.read()), "PUT");
    notice(`Saved as version ${saved.version}. Earlier versions can still be restored.`);
    await loadWorlds();
    await showDetail(ledger.id);
  }, "primary", "Save these edits as the world's next version");
  const stale = () => { save.disabled = true; preview.hidden = true; };
  save.disabled = true;
  const subjects = node("div", "world-subjects", ledger.subjects.map(subject => subjectRow(subject, stale)));
  const addSubject = button("Add subject", () => { subjects.append(subjectRow({ designation: "", canon: "" }, stale)); stale(); }, "quiet", "Add a person or being to this world");
  const check = button("Preview changes", async () => {
    const result = await json(`/api/worlds/${id}/edit-preview`, readEditor(form, ledger.version, pools.read()));
    preview.replaceChildren(text("h4", "What saving would change"), diffView(result.changes, "No changes yet."));
    preview.hidden = false;
    save.disabled = !result.changes.length;
  }, "secondary", "Review exactly what will change before anything is saved");
  const pools = poolsEditor(catalog, ledger.pools);
  const form = node("form", "world-edit", [
    text("h3", `Edit ${ledger.name} — version ${ledger.version}`),
    text("p", "Edits are saved as a new version; the version you started from stays and can be restored.", "muted"),
    field("Name", Object.assign(node("input"), { name: "world_name", value: ledger.name, maxLength: 160 })),
    field("What governs this world", Object.assign(node("textarea"), { name: "seed_sentence", rows: 2, value: ledger.seed_sentence })),
    ...Object.entries(LIST_LABELS).map(([key, label]) => field(`${label} (one per line)`, textArea(key, ledger[key], 4))),
    text("h4", "Subjects"), subjects, addSubject, pools.element, preview,
    node("div", "buttons world-actions", [check, save, button("Cancel", close, "secondary", "Leave without saving and read the world with its earlier versions")])
  ]);
  form.addEventListener("input", stale);
  form.addEventListener("submit", event => event.preventDefault());
  return form;
}

async function showDetail(id, editing = false) {
  const [ledger, versions] = await Promise.all(
    [`/api/worlds/${id}`, `/api/worlds/${id}/versions`].map(path => api(path).then(response => response.json())));
  const detail = $("#world-detail");
  const rollbacks = () => versions.slice(0, -1).reverse().map(item => button(`Restore v${item.version}`, async () => {
    await json(`/api/worlds/${id}/rollback`, { version: item.version });
    notice(`Restored v${item.version} as a new version.`);
    await loadWorlds();
    await showDetail(id);
  }, "secondary", "Save this earlier version as the newest one"));
  const catalog = await loadVocabularyCatalog();
  const actions = () => node("div", "buttons world-actions", [
    button("Edit", edit, "secondary", "Change this world's canon; saved as a new version"), ...rollbacks(),
    button("Close", () => { detail.hidden = true; }, "secondary", "Close this view")]);
  const view = () => detail.replaceChildren(text("h3", `${ledger.name} — version ${ledger.version}`), actions(), ...ledgerView(ledger), actions());
  const edit = () => detail.replaceChildren(editorView(ledger, catalog, view));
  editing ? edit() : view();
  detail.hidden = false;
  detail.scrollIntoView({ block: "start", behavior: "smooth" });
}

function worldRow(world) {
  const buttons = node("div", "buttons world-actions", [
    button("Open", () => showDetail(world.id), "secondary", "Read this world"),
    button("Edit", () => showDetail(world.id, true), "secondary", "Change this world's canon; saved as a new version"),
    button("Export", async () => saveDownload(await api(`/api/worlds/${world.id}/export`), `${world.id}.world.json`), "secondary", "Save a copy of this world"),
    button("Delete", async () => {
      if (!confirm(`Delete the world "${world.name}" and all of its versions? Your videos are kept.`)) return;
      await api(`/api/worlds/${world.id}`, { method: "DELETE" });
      notice(`Deleted ${world.name}.`);
      await loadWorlds();
    }, "delete-btn", "Delete this world and its versions")
  ]);
  return node("div", "world-row", [
    node("div", "", [text("strong", world.name), text("span", `  v${world.version} · ${world.terms} terms · ${world.sources} sources`, "muted")]),
    buttons
  ]);
}

function proposalRow(proposal) {
  const title = proposal.mode === "create" ? `New world: ${proposal.proposed.name}` : `Growth for ${proposal.world_id}`;
  const accept = button("Accept", async () => {
    await api(`/api/worlds/proposals/${proposal.id}/accept`, { method: "POST" });
    notice("Saved as a new version of the world.");
    await loadWorlds();
  }, "primary", "Save these changes as the world's next version");
  const reject = button(proposal.changes.length ? "Reject" : "Dismiss", async () => {
    await api(`/api/worlds/proposals/${proposal.id}`, { method: "DELETE" });
    await loadWorlds();
  }, "quiet", "Discard this proposal");
  const actions = node("div", "buttons", proposal.changes.length || proposal.mode === "create" ? [accept, reject] : [reject]);
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
  $$(".world-contrast-select").forEach((select) => fillSelect(select, worlds, "None"));
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
