const fileExtensions = file => file.name.toLowerCase().split('.').pop();

function acceptsFile(input, file) {
  if (input.accept === 'audio/*') return ['wav', 'mp3', 'flac', 'ogg', 'm4a', 'aac', 'aiff'].includes(fileExtensions(file));
  if (input.accept === 'image/*' || input.accept === 'image/png,image/jpeg')
    return ['png', 'jpg', 'jpeg', 'webp'].includes(fileExtensions(file)) &&
      (input.accept === 'image/*' || ['png', 'jpg', 'jpeg'].includes(fileExtensions(file)));
  return input.accept.split(',').some(raw => {
    const type = raw.trim().toLowerCase();
    if (type.startsWith('.')) return file.name.toLowerCase().endsWith(type);
    if (type.endsWith('/*')) return file.type.toLowerCase().startsWith(type.slice(0, -1));
    return file.type.toLowerCase() === type;
  });
}

function dropError(input, files) {
  if (!files.length) return 'Drop a file here.';
  if (!input.multiple && files.length !== 1) return 'Drop one file at a time.';
  if (input.multiple && files.length > 9) return 'Choose at most nine reference images.';
  if (files.some(file => !acceptsFile(input, file))) return `Unsupported file type. Choose ${input.accept}.`;
  return '';
}

export function initFileDropTargets() {
  document.querySelectorAll('input[type="file"]').forEach(input => {
    const label = input.closest('label');
    if (!label) return;
    label.classList.add('file-drop-target');
    const hint = document.createElement('small');
    hint.className = 'file-drop-hint';
    hint.textContent = input.multiple ? 'Choose files or drop up to 9 images here' : 'Choose a file or drop it here';
    label.append(hint);
    const error = document.createElement('small');
    error.className = 'file-drop-error';
    error.setAttribute('role', 'alert');
    label.append(error);
    input.addEventListener('change', () => { error.textContent = ''; });
    const clearHover = () => label.classList.remove('file-drop-hover');
    label.addEventListener('dragenter', event => {
      if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return;
      event.preventDefault();
      label.classList.add('file-drop-hover');
    });
    label.addEventListener('dragover', event => {
      if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      label.classList.add('file-drop-hover');
    });
    label.addEventListener('dragleave', event => {
      if (!label.contains(event.relatedTarget)) clearHover();
    });
    label.addEventListener('drop', event => {
      if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return;
      event.preventDefault();
      clearHover();
      if (input.disabled) return;
      const files = [...event.dataTransfer.files];
      const message = dropError(input, files);
      if (message) { error.textContent = message; return; }
      const transfer = new DataTransfer();
      files.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
  document.addEventListener('dragover', event => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault();
  });
  document.addEventListener('drop', event => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault();
  });
}
