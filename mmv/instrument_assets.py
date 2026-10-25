"""Instrument roles. Reference sheets are Open Prop Protocol props; this module only maps roles to props."""
from __future__ import annotations

import hashlib
from pathlib import Path

KINDS = ('drums', 'bass', 'guitar', 'keyboards')
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
    """Resolve a role to a prop sheet: the named prop, else the role's default prop."""
    valid_kind(kind)
    from . import props
    props.install_starter_props(store)
    selected = props.select(store, prop_id or props.default_prop_id(store, kind), use)
    return {**selected, 'id': kind, 'kind': 'opp.instrument.reference', 'version': 1,
            'reference': Path(selected['path']).name}


def catalog(store):
    """Read-only view of each role and the prop it uses by default."""
    result = []
    for kind in KINDS:
        name, description = DESIGNS[kind]
        try:
            record = locate(store, kind)
            result.append({'id': kind, 'name': name, 'description': description, 'available': True,
                           'prop_id': record['prop_id'], 'license': record['license']})
        except ValueError as exc:
            result.append({'id': kind, 'name': name, 'description': description, 'available': False, 'note': str(exc)})
    return result
