"""Instrument props, separate from OAP actors. Local imports never imply public clearance."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from PIL import Image

from .actors import clean_image
from .storage import inside, read_json, write_json

KINDS = ('drums', 'bass', 'guitar', 'keyboards')
BUNDLED = Path(__file__).parent / 'assets' / 'instruments'
DESIGNS = {
    'drums': ('Acoustic drums', 'Deep teal five-piece acoustic drum kit, chrome hardware, white batter heads, hi-hat, crash and ride cymbals, stool, pedals and wooden sticks.'),
    'bass': ('Electric bass', 'Amber ash four-string electric bass, dark fretboard, two black pickup units, two knobs, chrome bridge, two tuners per headstock side and black strap.'),
    'guitar': ('Electric guitar', 'Cherry-red six-string electric guitar, cream pickguard, two humbuckers, fixed chrome bridge, two knobs, rounded headstock with chrome tuners and black strap.'),
    'keyboards': ('Stage keyboards', 'Charcoal electronic stage keyboard, a row of rotary knobs, centered blank display, two left-side wheels, black X stand and one sustain pedal.'),
}


def valid_kind(value):
    if value not in KINDS:
        raise ValueError('Choose drums, bass, guitar or keyboards')
    return value


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def locate(store, kind, *, prop_id=None, use=''):
    valid_kind(kind)
    if prop_id:
        from . import props
        selected = props.select(store, prop_id, use)
        return {**selected, 'id': kind, 'kind': 'opp.instrument.reference',
                'version': 1, 'reference': Path(selected['path']).name}
    local = store.home / 'instruments' / kind
    root = local if (local / 'instrument.json').is_file() else BUNDLED / kind
    record = read_json(root / 'instrument.json')
    if not record:
        raise ValueError(f'{kind} reference sheet is missing; import it or turn consistent instrument references off')
    path = inside(root, record.get('reference', 'reference.png'))
    if record.get('kind') != 'mmv.instrument' or record.get('id') != kind or record.get('version') != 1:
        raise ValueError(f'Invalid {kind} instrument metadata')
    if not path.is_file() or sha256(path) != record.get('sha256'):
        raise ValueError(f'{kind} reference checksum mismatch; restore the original instrument sheet')
    return {**record, 'path': str(path)}


def catalog(store):
    result = []
    for kind in KINDS:
        name, description = DESIGNS[kind]
        try:
            record = locate(store, kind)
            result.append({**{k: v for k, v in record.items() if k != 'path'}, 'available': True})
        except ValueError as exc:
            result.append({'id': kind, 'name': name, 'description': description, 'available': False, 'note': str(exc)})
    return result


def import_sheet(store, kind, data, *, license, provenance):
    """Preserve original bytes alongside a clean PNG; never overwrite an existing local sheet."""
    valid_kind(kind)
    if not isinstance(license, str) or not license.strip() or len(license) > 160:
        raise ValueError('Supply the instrument image license (at most 160 characters)')
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 2000:
        raise ValueError('Supply instrument image provenance (at most 2000 characters)')
    target = store.home / 'instruments' / kind
    if target.exists():
        raise ValueError('Instrument already exists; imports never overwrite instruments')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage = Path(temp)
        clean_image(data, stage / 'reference.png')
        (stage / 'original.image').write_bytes(data)
        with Image.open(stage / 'reference.png') as image:
            width, height = image.size
        name, description = DESIGNS[kind]
        record = {'kind': 'mmv.instrument', 'version': 1, 'id': kind, 'name': name, 'description': description,
                  'reference': 'reference.png', 'sha256': sha256(stage / 'reference.png'),
                  'original_sha256': sha256(stage / 'original.image'), 'width': width, 'height': height,
                  'license': license.strip(), 'provenance': provenance.strip()}
        write_json(stage / 'instrument.json', record)
        stage.rename(target)
    return record
