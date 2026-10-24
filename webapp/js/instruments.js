import { $, api, handle, notice, text, upload } from './core.js';

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
  const propFields = form.querySelector('.instrument-props');
  if (propFields) {
    const assigned = new Set(Object.values(assignments));
    propFields.hidden = !enabled || !assigned.size;
    propFields.querySelectorAll('[data-prop-kind]').forEach(row => {
      row.hidden = !enabled || !assigned.has(row.dataset.propKind);
    });
  }
}

export function instrumentsFromForm(form, request) {
  const assignments = JSON.parse(form.elements.instrument_assignments_json.value || '{}');
  request.instrument_assignments = Object.fromEntries(request.actors
    .filter(actor => request.instrument_mode === 'perform' && assignments[actor])
    .map(actor => [actor, assignments[actor]]));
  request.instrument_references = Boolean(form.elements.instrument_references.checked);
  request.instrument_props = {};
  request.instrument_prop_uses = {};
  for (const kind of kinds) {
    const prop = form.elements[`instrument_prop_${kind}`]?.value;
    const use = form.elements[`instrument_use_${kind}`]?.value.trim();
    if (request.instrument_mode === 'perform' && Object.values(request.instrument_assignments).includes(kind) && prop) {
      request.instrument_props[kind] = prop;
      if (use) request.instrument_prop_uses[kind] = use;
    }
    delete request[`instrument_prop_${kind}`];
    delete request[`instrument_use_${kind}`];
  }
  delete request.instrument_assignments_json;
  for (const key of Object.keys(request)) if (key.startsWith('instrument_actor_')) delete request[key];
}

export async function loadProps() {
  const records = await (await api('/api/props')).json();
  const list = $('#opp-library');
  if (list) list.replaceChildren(...records.map(record => {
    const card = document.createElement('article');
    card.className = 'card';
    card.append(text('h3', record.name), text('p', `${record.id} · ${record.sheets.length} sheet(s) · ${(record.assets || []).length} asset(s) · ${record.license || 'License unspecified'}`));
    const image = document.createElement('img');
    image.src = `/api/props/${encodeURIComponent(record.id)}/reference`;
    image.alt = `${record.name} base reference`;
    image.loading = 'lazy';
    image.style.cssText = 'max-width:100%;max-height:260px;object-fit:contain';
    card.append(image);
    return card;
  }));
  for (const kind of kinds) {
    const select = $('#video-form')?.elements[`instrument_prop_${kind}`];
    if (!select) continue;
    const previous = select.value;
    select.replaceChildren(new Option('Default prop', ''), ...records.map(record => new Option(`${record.name} (${record.id})`, record.id)));
    select.value = previous;
  }
}

export function initInstrumentLibrary() {
  const oppForm = $('#opp-import-form');
  let inspected = null;
  let signerKey = '';
  const clearInspection = () => {
    inspected = null;
    signerKey = '';
    oppForm.hidden = true;
    $('#opp-report').hidden = true;
    $('#opp-report').textContent = '';
    $('#opp-signer').hidden = true;
    $('#opp-signer').textContent = '';
    oppForm.elements.accept_signer.checked = false;
  };
  $('#opp-file').addEventListener('change', clearInspection);
  $('#opp-allow-unsigned').addEventListener('change', clearInspection);
  $('#inspect-opp').onclick = handle(async () => {
    const file = $('#opp-file').files[0];
    if (!file) throw new Error('Choose an OPP package first');
    clearInspection();
    inspected = await upload(file, 'opp');
    const allowUnsigned = $('#opp-allow-unsigned').checked;
    const report = await (await api(`/api/opp/inspect/${encodeURIComponent(inspected)}?allow_unsigned=${allowUnsigned}`)).json();
    signerKey = report.verification.signature_valid ? report.manifest.prop.owner.public_key : '';
    if (signerKey) {
      $('#opp-signer').textContent = `Verified signer: ${report.manifest.prop.owner.name || 'Unnamed'} · ${signerKey}`;
      $('#opp-signer').hidden = false;
    }
    const summary = {prop: report.manifest.prop, tier: report.tier, omitted_files: report.omitted,
      sheets: report.manifest.sheets, assets: report.manifest.assets || [], verification: report.verification};
    $('#opp-report').textContent = JSON.stringify(summary, null, 2);
    $('#opp-report').hidden = false;
    oppForm.hidden = false;
    oppForm.elements.accept_signer.parentElement.hidden = !report.verification.signature_valid;
  });
  oppForm.onsubmit = handle(async event => {
    event.preventDefault();
    if (!inspected) throw new Error('Inspect an OPP package first');
    const body = new FormData();
    body.set('filename', inspected);
    body.set('allow_unsigned', String($('#opp-allow-unsigned').checked));
    body.set('accept_signer', oppForm.elements.accept_signer.checked ? signerKey : '');
    await api('/api/opp/import', {method: 'POST', body});
    clearInspection();
    await loadProps();
    notice('OPP prop imported into this studio.');
  });
  return loadProps().catch(error => notice(error.message));
}
