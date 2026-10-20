"""Private OPP library. Protocol metadata stays separate from MMV instrument roles."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

from .actors import clean_image
from .storage import inside, read_json, write_json

MAX_PACKAGE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_SHEET_BYTES = 25 * 1024 * 1024


def prop_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', value):
        raise ValueError('OPP prop ID must use 1–80 lowercase letters, digits, underscores or hyphens')
    return value


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _protocol():
    try:
        from opp import core
    except ImportError:
        raise ValueError('Open Prop Protocol support is not installed') from None
    return core


def protocol_version():
    return _protocol().VERSION


def package_info(path, *, allow_unsigned=False):
    """Bound untrusted ZIP work before asking the pinned OPP verifier to read it."""
    path = Path(path)
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError('OPP package exceeds 128 MB')
    initial_hash = sha256(path)
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > 256 or sum(item.file_size for item in members) > MAX_EXPANDED_BYTES:
                raise ValueError('OPP package has too many files or exceeds expanded size limit')
            names = set()
            for item in members:
                name = item.filename
                if (name in names or item.is_dir() or not name or name.startswith('/') or '\\' in name or ':' in name or
                        any(part in ('', '.', '..') for part in name.split('/')) or
                        stat.S_ISLNK(item.external_attr >> 16)):
                    raise ValueError('OPP package contains duplicate or unsafe paths')
                if item.flag_bits & 1 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ValueError('OPP package uses unsupported ZIP encryption or compression')
                names.add(name)
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > 2 * 1024 * 1024:
                raise ValueError('OPP manifest is missing or too large')
            manifest = json.loads(archive.read('manifest.json'))
            if not isinstance(manifest, dict):
                raise ValueError('OPP manifest must be an object')
            sheets = manifest.get('sheets')
            if not isinstance(sheets, list):
                raise ValueError('OPP sheets must be an array')
            prop = manifest.get('prop') or {}
            if (not isinstance(prop, dict) or not isinstance(prop.get('name'), str) or len(prop['name']) > 160 or
                    not isinstance(prop.get('description', ''), str) or len(prop.get('description', '')) > 2000 or
                    not isinstance(prop.get('license', ''), str) or len(prop.get('license', '')) > 200):
                raise ValueError('OPP prop metadata is invalid or too long')
            if any(not isinstance(sheet, dict) or (sheet.get('file') in names and
                    archive.getinfo(sheet['file']).file_size > MAX_SHEET_BYTES) for sheet in sheets):
                raise ValueError('OPP image sheet exceeds 25 MB or is invalid')
            if any(len(sheet.get('label', '')) > 160 or len(sheet.get('tags', [])) > 32 or
                   any(len(tag) > 100 for tag in sheet.get('tags', [])) for sheet in sheets):
                raise ValueError('OPP sheet labels or tags are too long')
        verification = _protocol().verify_package(str(path), strict=True, require_signature=not allow_unsigned)
        if sha256(path) != initial_hash:
            raise ValueError('OPP package changed during verification')
        if not verification['ok']:
            raise ValueError('OPP verification failed: ' + '; '.join(verification['issues'][:8]))
        return manifest, verification
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid OPP package') from exc


def import_package(store, path, *, allow_unsigned=False, accept_signer=''):
    """Keep the original bundle and cleaned visual sheets; never overwrite a prop."""
    source_hash = sha256(path)
    manifest, verification = package_info(path, allow_unsigned=allow_unsigned)
    if sha256(path) != source_hash:
        raise ValueError('OPP package changed during import')
    signer = (manifest['prop'].get('owner') or {}).get('public_key')
    if verification['signature_valid'] and accept_signer != signer:
        raise ValueError('Review the OPP signer and explicitly accept this signer public key')
    prop = manifest['prop']
    prop_id = prop_identifier(prop['id'])
    verified_hash = source_hash
    target = store.home / 'props' / prop_id
    if target.exists():
        raise ValueError('Prop already exists; imports never overwrite props')
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        present = set(archive.namelist())
        included = [sheet for sheet in manifest['sheets'] if sheet['file'] in present]
        if not any(sheet['kind'] == 'base' for sheet in included):
            raise ValueError('OPP package has no included base sheet')
        with tempfile.TemporaryDirectory(dir=target.parent) as temp:
            stage = Path(temp)
            sheet_records = []
            for index, sheet in enumerate(included):
                output = f'sheet-{index}.png'
                source = archive.read(sheet['file'])
                if hashlib.sha256(source).hexdigest() != sheet['sha256']:
                    raise ValueError('OPP sheet changed during import')
                clean_image(source, stage / output)
                sheet_records.append({key: sheet[key] for key in ('file', 'kind', 'label', 'tags', 'clearance', 'sha256')}
                                     | {'reference': output, 'reference_sha256': sha256(stage / output)})
            shutil.copyfile(path, stage / 'original.opp')
            if sha256(stage / 'original.opp') != verified_hash:
                raise ValueError('OPP package changed during import')
            owner = prop.get('owner') or {}
            record = {'id': prop_id, 'name': prop['name'], 'description': prop.get('description') or '',
                      'license': prop.get('license') or '', 'owner': {key: owner.get(key) for key in ('name', 'did', 'public_key')},
                      'opp_version': manifest['opp_version'], 'bundle_sha256': sha256(stage / 'original.opp'),
                      'signature_valid': verification['signature_valid'], 'signer_accepted': accept_signer == signer if signer else False,
                      'sheets': sheet_records}
            write_json(stage / 'prop.json', record)
            stage.rename(target)
    return public_record(record)


def public_record(record):
    return {key: value for key, value in record.items() if key not in ('bundle_sha256', 'signer_accepted')}


def load(store, prop_id):
    root = store.home / 'props' / prop_identifier(prop_id)
    record = read_json(root / 'prop.json')
    if not record or record.get('id') != prop_id:
        raise ValueError('OPP prop is not imported: ' + prop_id)
    bundle = inside(root, 'original.opp')
    if not bundle.is_file() or sha256(bundle) != record.get('bundle_sha256'):
        raise ValueError('OPP package changed; restore it and preview again')
    return record


def catalog(store):
    root = store.home / 'props'
    return [public_record(record) for path in sorted(root.glob('*/prop.json'))
            if (record := read_json(path)) and isinstance(record, dict) and record.get('id') == path.parent.name]


def select(store, prop_id, use=''):
    """Match free-form use to an included interaction sheet, falling back to a base."""
    if not isinstance(use, str) or len(use) > 200:
        raise ValueError('OPP use must be at most 200 characters')
    record = load(store, prop_id)
    manifest = {'opp_version': record['opp_version'], 'kind': 'opp.prop.manifest',
                'prop': {'id': record['id'], 'name': record['name'], 'owner': record['owner']},
                'sheets': record['sheets'], 'assets': []}
    sheet = _protocol().select_sheet(manifest, use)
    if sheet is None:
        raise ValueError('OPP prop has no selectable sheet')
    root = store.home / 'props' / record['id']
    path = inside(root, sheet['reference'])
    if not path.is_file() or sha256(path) != sheet['reference_sha256']:
        raise ValueError('OPP reference changed; restore it and preview again')
    return {'prop_id': record['id'], 'name': record['name'], 'description': record['description'],
            'license': record['license'], 'sheet_kind': sheet['kind'], 'sheet_label': sheet['label'],
            'sheet_tags': sheet.get('tags', []), 'clearance': sheet['clearance'], 'use': use, 'path': str(path),
            'sha256': sheet['reference_sha256'], 'source_sha256': sheet['sha256'],
            'bundle_path': str(root / 'original.opp'), 'bundle_sha256': record['bundle_sha256']}
