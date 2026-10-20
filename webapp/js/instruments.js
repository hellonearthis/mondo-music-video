import { $, api, handle, notice, text } from './core.js';

const kinds = ['drums', 'bass', 'guitar', 'keyboards'];

export function syncInstrumentControls(form, changed = null) {
  const controls = form.querySelector('.instrument-assignments');
  if (!controls) return;
  if (!controls.querySelector('select')) {
    for (let index = 0; index < 9; index++) {
      const label = document.createElement('label');
      label.append(`Cast actor ${index + 1} instrument `);
      const select = document.createElement('select');
      select.name = `instrument_actor_${index}`;
      select.append(new Option('No instrument', ''), ...kinds.map(kind => new Option(kind[0].toUpperCase() + kind.slice(1), kind)));
      label.append(select);
      controls.append(label);
    }
  }
  const saved = form.elements.instrument_assignments_json;
  let assignments;
  try { assignments = JSON.parse(saved.value || '{}'); } catch { assignments = {}; }
  if (changed?.dataset.instrumentActor) assignments[changed.dataset.instrumentActor] = changed.value;
  saved.value = JSON.stringify(assignments);
  const enabled = form.elements.instrument_mode.value === 'perform';
  controls.hidden = !enabled;
  const actors = [...form.querySelector('.actor-select').selectedOptions];
  controls.querySelectorAll('select').forEach((select, index) => {
    const actor = actors[index];
    select.parentElement.hidden = !actor;
    const label = actor ? `${actor.textContent} instrument` : `Cast actor ${index + 1} instrument`;
    select.parentElement.firstChild.textContent = label + ' ';
    select.setAttribute('aria-label', label);
    select.dataset.instrumentActor = actor?.value || '';
    select.value = assignments[actor?.value] || '';
  });
}

export function instrumentsFromForm(form, request) {
  const assignments = JSON.parse(form.elements.instrument_assignments_json.value || '{}');
  request.instrument_assignments = Object.fromEntries(request.actors
    .filter(actor => request.instrument_mode === 'perform' && assignments[actor])
    .map(actor => [actor, assignments[actor]]));
  request.instrument_references = Boolean(form.elements.instrument_references.checked);
  delete request.instrument_assignments_json;
  for (const key of Object.keys(request)) if (key.startsWith('instrument_actor_')) delete request[key];
}

export async function loadInstruments() {
  const list = $('#instrument-library');
  if (!list) return;
  const records = await (await api('/api/instruments')).json();
  list.replaceChildren(...records.map(record => {
    const card = document.createElement('article');
    card.className = 'card';
    card.append(text('h3', record.name), text('p', record.available ? `${record.width} × ${record.height} · ${record.license}` : 'Reference sheet not installed'));
    if (record.available) {
      const image = document.createElement('img');
      image.src = `/api/instruments/${encodeURIComponent(record.id)}/reference`;
      image.alt = `${record.name} reference sheet`;
      image.loading = 'lazy';
      image.style.cssText = 'max-width:100%;max-height:260px;object-fit:contain';
      card.append(image);
    } else if (record.note) card.append(text('p', record.note, 'muted'));
    return card;
  }));
}

export function initInstrumentLibrary() {
  const form = $('#instrument-import-form');
  if (!form) return;
  form.onsubmit = handle(async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const data = new FormData(form);
      const kind = data.get('instrument_id');
      data.delete('instrument_id');
      await api(`/api/instruments/${encodeURIComponent(kind)}`, {method: 'POST', body: data});
      form.reset();
      await loadInstruments();
      notice('Instrument reference imported into this studio.');
    } finally { button.disabled = false; }
  });
  loadInstruments().catch(error => notice(error.message));
}
