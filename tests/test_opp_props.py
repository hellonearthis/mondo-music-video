"""OPP import and instrument selection with synthetic packages and temporary data."""
import json
import zipfile
from pathlib import Path

import pytest
from opp import core as opp

from mmv import instrument_assets, instruments, props
from mmv.storage import Storage
from tests.test_public_app import picture


def package(tmp_path, *, signed=False):
    source = tmp_path / 'source'
    (source / 'references/master').mkdir(parents=True)
    (source / 'references/master/base.png').write_bytes(picture())
    (source / 'references/master/playing.png').write_bytes(picture())
    identity = opp.generate_identity() if signed else {'did': None, 'public_key': None, '_private': None}
    manifest = {'opp_version': '0.1.0', 'kind': 'opp.prop.manifest',
                'prop': {'id': 'blue-guitar', 'name': 'Blue Guitar', 'description': 'Blue six-string guitar',
                         'license': 'test only', 'owner': {'name': 'Test', 'did': identity['did'],
                                                          'public_key': identity['public_key']}},
                'sheets': [
                    {'file': 'references/master/base.png', 'kind': 'base', 'label': 'Overview', 'tags': [],
                     'prompt_modifier': None, 'clearance': 'master', 'sha256': None},
                    {'file': 'references/master/playing.png', 'kind': 'interaction', 'label': 'Strumming strings',
                     'tags': ['playing guitar', 'strumming strings'], 'prompt_modifier': 'Hands on strings',
                     'clearance': 'master', 'sha256': None}],
                'assets': [], 'signature': {'algorithm': 'ed25519', 'value': None, 'signed_at': None}}
    (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    output = tmp_path / 'blue-guitar.opp'
    opp.package(source, output, sign_key=identity['_private'])
    return output


def test_signed_import_selects_interaction_and_preserves_original(tmp_path):
    source = package(tmp_path, signed=True)
    store = Storage(tmp_path / 'home')
    manifest, verification = props.package_info(source)
    assert manifest['prop']['id'] == 'blue-guitar' and verification['signature_valid']
    with pytest.raises(ValueError, match='accept this signer'):
        props.import_package(store, source)
    record = props.import_package(store, source, accept_signer=manifest['prop']['owner']['public_key'])
    assert record['id'] == 'blue-guitar' and record['signature_valid']
    assert (store.home / 'props/blue-guitar/original.opp').read_bytes() == source.read_bytes()
    assert len(props.catalog(store)) == 1
    base = props.select(store, 'blue-guitar', 'unmatched')
    playing = props.select(store, 'blue-guitar', 'strumming strings')
    assert base['sheet_kind'] == 'base' and playing['sheet_kind'] == 'interaction'
    asset = instrument_assets.locate(store, 'guitar', prop_id='blue-guitar', use='strumming strings')
    assert asset['sha256'] == playing['sha256'] and asset['prop_id'] == 'blue-guitar'
    with pytest.raises(ValueError, match='never overwrite'):
        props.import_package(store, source, accept_signer=manifest['prop']['owner']['public_key'])
    assert props.select(store, 'blue-guitar')['sheet_kind'] == 'base'
    (store.home / 'props/blue-guitar/original.opp').write_bytes(b'changed')
    with pytest.raises(ValueError, match='package changed'):
        props.select(store, 'blue-guitar')


def test_unsigned_requires_explicit_choice_and_archive_limits(tmp_path):
    source = package(tmp_path)
    with pytest.raises(ValueError, match='verification failed'):
        props.package_info(source)
    store = Storage(tmp_path / 'home')
    assert not props.import_package(store, source, allow_unsigned=True)['signature_valid']
    unsafe = tmp_path / 'unsafe.opp'
    with zipfile.ZipFile(unsafe, 'w') as archive:
        archive.writestr('../escape', b'bad')
        archive.writestr('manifest.json', b'{}')
    with pytest.raises(ValueError, match='unsafe paths'):
        props.package_info(unsafe)


def test_prop_options_are_free_form_but_roles_are_bounded():
    request = {'instrument_mode': 'perform', 'kind': 'video', 'actors': ['alice'],
               'instrument_assignments': {'alice': 'guitar'},
               'instrument_props': {'guitar': 'blue-guitar'},
               'instrument_prop_uses': {'guitar': 'rapid palm-muted chords'}}
    assert instruments.prop_options(request, instruments.clean(request)) == (
        {'guitar': 'blue-guitar'}, {'guitar': 'rapid palm-muted chords'})
    for change in ({'instrument_props': {'bass': 'blue-guitar'}},
                   {'instrument_prop_uses': {'guitar': 'x' * 201}},
                   {'instrument_props': {'guitar': '../escape'}}):
        with pytest.raises(ValueError):
            instruments.prop_options({**request, **change}, instruments.clean(request))
