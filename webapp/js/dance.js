// Saved actor-id overrides stay with their actor when the cast selection changes.
function partControl(index) {
  const label = document.createElement('label');
  label.append(`Cast actor ${index + 1} part `);
  const select = document.createElement('select');
  select.name = `dance_part_${index}`;
  select.append(...['auto', 'beat', 'drums', 'bass', 'vocals'].map(part =>
    new Option(part === 'beat' ? 'Overall beat' : part[0].toUpperCase() + part.slice(1), part)));
  label.append(select);
  return label;
}

export function syncDanceControls(form, changed = null) {
  const controls = form.querySelector('.dance-parts');
  if (!controls) return;
  if (!controls.querySelector('select')) controls.append(...Array.from({length: 9}, (_, index) => partControl(index)));
  const saved = form.elements.dance_parts_json;
  let parts;
  try { parts = JSON.parse(saved.value || '{}'); } catch { parts = {}; }
  if (changed?.dataset.danceActor) parts[changed.dataset.danceActor] = changed.value;
  saved.value = JSON.stringify(parts);
  controls.hidden = form.elements.dance_mode.value !== 'independent';
  const actors = [...form.querySelector('.actor-select').selectedOptions];
  controls.querySelectorAll('select').forEach((select, index) => {
    const actor = actors[index];
    const label = select.parentElement;
    label.hidden = !actor;
    label.firstChild.textContent = actor ? `${actor.textContent} part ` : `Cast actor ${index + 1} part `;
    select.setAttribute('aria-label', actor ? `${actor.textContent} part` : `Cast actor ${index + 1} part`);
    select.dataset.danceActor = actor?.value || '';
    select.value = parts[actor?.value] || 'auto';
  });
}

export function dancePartsFromForm(form, request) {
  const parts = JSON.parse(form.elements.dance_parts_json.value || '{}');
  request.dance_parts = Object.fromEntries(request.actors
    .filter(actor => request.dance_mode === 'independent' && parts[actor] && parts[actor] !== 'auto')
    .map(actor => [actor, parts[actor]]));
  delete request.dance_parts_json;
  for (const key of Object.keys(request)) if (key.startsWith('dance_part_')) delete request[key];
}
