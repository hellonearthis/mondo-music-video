// The big red button: pick a song, fill the blanks with a random plan, and open the usual preview for consent.

import { $, api, handle, notice, state } from "./core.js";
import { updateVocabCustomBadge } from "./vocabulary.js";
import { clearStoryboard } from "./storyboard.js";
import { resolutionSelect, scheduleSave, updateSongPreview } from "./project.js";

const fillIfEmpty = (field, value) => { if (field && !field.value.trim()) field.value = value; };
const setSelect = (field, value) => {
  if (!field || field.value === value) return;
  field.value = value;
  field.dispatchEvent(new Event("change", { bubbles: true }));
};
const stem = name => name.replace(/\.[^.]+$/, "");

const pendingUpload = form => new Promise(resolve => {
  const check = () => (state.formFiles.get(form)?.pending ? setTimeout(check, 100) : resolve(state.formFiles.get(form)));
  check();
});

// Nothing the person already chose is overwritten; instruments and subliminal flashes are always left off.
export function applyPlan(form, plan, songName = "") {
  fillIfEmpty(form.elements.title, stem(songName));
  if (!form.elements.direction.value.trim()) {
    form.elements.direction.value = plan.direction;
    if ([...form.elements.style_id.options].some(item => item.value === plan.style_id)) form.elements.style_id.value = plan.style_id;
  }
  const select = form.querySelector(".actor-select");
  if (![...select.selectedOptions].some(item => item.value)) {
    [...select.options].forEach(item => { item.selected = plan.actors.includes(item.value); });
    setSelect(form.elements.dance_mode, plan.dance_mode);
  }
  setSelect(form.elements.instrument_mode, "off");
  setSelect(form.elements.subliminal_mode, "off");
}

async function run(form) {
  const files = await pendingUpload(form);
  if (!files?.song) throw new Error("The song did not finish uploading; choose it again.");
  applyPlan(form, await (await api("/api/quick-start")).json(), files.songName || "");
  form.requestSubmit();
}

const HIDDEN_DEFAULTS = { instrument_assignments_json: "{}", dance_parts_json: "{}", subliminal_image: "" };

// Back to a blank panel; the renderer and resolution come from Settings, so they are kept.
export function resetVideoPanel(form) {
  const files = state.formFiles.get(form);
  if (files?.pending || form.dataset.storyboardPending || form.dataset.subliminalPending)
    throw new Error("Wait for the uploads to finish before clearing the panel.");
  const { backend, resolution } = form.elements;
  const keep = { backend: backend?.value, resolution: resolution?.value };
  if (files?.songObjectUrl) URL.revokeObjectURL(files.songObjectUrl);
  state.formFiles.set(form, { references: [], pending: 0 });
  form.reset();
  Object.entries(HIDDEN_DEFAULTS).forEach(([name, value]) => { if (form.elements[name]) form.elements[name].value = value; });
  if (keep.backend) { backend.value = keep.backend; resolutionSelect(form); }
  if (keep.resolution) resolution.value = keep.resolution;
  form.querySelector(".song-receipt").textContent = "Please load in your music.";
  form.querySelector(".song-input").required = true;
  updateSongPreview(form, "");
  form.querySelector(".refs-receipt").textContent = "No additional images";
  clearStoryboard(form);
  state.currentCustomVocab = {};
  state.currentVocabRandomKey = "";
  updateVocabCustomBadge();
  form.dispatchEvent(new Event("change", { bubbles: true }));
  scheduleSave();
}

export function initQuickStart() {
  const form = $("#video-form");
  const dialog = $("#quick-start-dialog");
  const input = $("#quick-start-song");
  if (!form || !dialog || !input) return;
  $("#quick-start").onclick = handle(async () => {
    if (state.formFiles.get(form)?.song || state.formFiles.get(form)?.pending) return run(form);
    input.value = "";
    dialog.showModal();
  });
  const fresh = $("#start-fresh-dialog");
  $("#start-fresh").onclick = () => fresh.showModal();
  $("#start-fresh-cancel").onclick = () => fresh.close();
  $("#start-fresh-confirm").onclick = handle(async () => {
    fresh.close();
    resetVideoPanel(form);
    notice("The Music Video panel is cleared.");
  });
  input.addEventListener("change", handle(async () => {
    const file = input.files[0];
    if (!file) return;
    const main = form.querySelector(".song-input");
    const transfer = new DataTransfer();
    transfer.items.add(file);
    main.files = transfer.files;
    main.dispatchEvent(new Event("change", { bubbles: true }));
    dialog.close();
    notice("Uploading your song…");
    try { await run(form); } finally { notice(""); }
  }));
}
