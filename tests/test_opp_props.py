"""OPP import and instrument selection with synthetic packages and temporary data."""
import json
import zipfile
from pathlib import Path

import pytest
opp = pytest.importorskip("opp.core")

from mmv import instrument_assets, instruments, props
from mmv.storage import Storage
from tests.test_public_app import picture


def legacy_instrument(home, kind, data=None):
    """Write a pre-OPP instrument sheet the way earlier releases stored it."""
    root = Path(home) / 'instruments' / kind
    root.mkdir(parents=True)
    (root / 'reference.png').write_bytes(data or picture())
    (root / 'instrument.json').write_text(json.dumps({
        'kind': 'mmv.instrument', 'version': 1, 'id': kind, 'name': kind.title(), 'description': 'Legacy ' + kind,
        'reference': 'reference.png', 'sha256': instrument_assets.sha256(root / 'reference.png'),
        'license': 'test', 'provenance': 'synthetic'}), encoding='utf-8')


def package(tmp_path, *, signed=False, version='0.2.0', stem=False):
    source = tmp_path / 'source'
    (source / 'references/master').mkdir(parents=True)
    (source / 'references/master/base.png').write_bytes(picture())
    (source / 'references/master/playing.png').write_bytes(picture())
    identity = opp.generate_identity() if signed else {'did': None, 'public_key': None, '_private': None}
    manifest = {'opp_version': version, 'kind': 'opp.prop.manifest',
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
    if stem:
        (source / 'references/master/stem.wav').write_bytes(b'RIFF')
        manifest['assets'] = [{'file': 'references/master/stem.wav', 'role': 'audio-stem', 'clearance': 'master',
                               'sha256': None}]
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


def test_v02_is_the_installed_protocol_and_v01_bundles_still_import(tmp_path):
    assert props.protocol_version() == '0.2.0'
    store = Storage(tmp_path / 'home')
    legacy = package(tmp_path / 'legacy', signed=True, version='0.1.0')
    key = props.package_info(legacy)[0]['prop']['owner']['public_key']
    assert props.import_package(store, legacy, accept_signer=key)['opp_version'] == '0.1.0'
    assert props.select(store, 'blue-guitar', 'strumming strings')['sheet_kind'] == 'interaction'


def test_v02_generic_assets_are_recorded_but_unknown_minor_is_rejected(tmp_path):
    store = Storage(tmp_path / 'home')
    current = package(tmp_path / 'current', signed=True, stem=True)
    key = props.package_info(current)[0]['prop']['owner']['public_key']
    record = props.import_package(store, current, accept_signer=key)
    assert record['opp_version'] == '0.2.0'
    assert record['assets'] == [{'file': 'references/master/stem.wav', 'role': 'audio-stem', 'clearance': 'master',
                                 'sha256': record['assets'][0]['sha256'], 'included': True}]
    assert not list((store.home / 'props/blue-guitar').glob('*.wav'))
    future = tmp_path / 'future.opp'
    with zipfile.ZipFile(current) as source, zipfile.ZipFile(future, 'w') as target:
        for name in source.namelist():
            data = source.read(name)
            if name == 'manifest.json':
                data = data.replace(b'"0.2.0"', b'"0.3.0"')
            target.writestr(name, data)
    with pytest.raises(ValueError, match='verification failed'):
        props.package_info(future)


def test_inspection_reports_tier_and_omitted_master_files(tmp_path):
    source = tmp_path / 'source'
    (source / 'references/public').mkdir(parents=True)
    (source / 'references/master').mkdir(parents=True)
    (source / 'references/public/base.png').write_bytes(picture())
    (source / 'references/master/hi.png').write_bytes(picture())
    identity = opp.generate_identity()
    sheet = lambda name, kind, clearance: {'file': name, 'kind': kind, 'label': kind, 'tags': [],
                                           'prompt_modifier': None, 'clearance': clearance, 'sha256': None}
    manifest = {'opp_version': '0.2.0', 'kind': 'opp.prop.manifest',
                'prop': {'id': 'lamp', 'name': 'Lamp', 'owner': {'name': 'T', 'did': identity['did'],
                                                                 'public_key': identity['public_key']}},
                'sheets': [sheet('references/public/base.png', 'base', 'public'),
                           sheet('references/master/hi.png', 'interaction', 'master')],
                'assets': [], 'signature': {'algorithm': 'ed25519', 'value': None, 'signed_at': None}}
    (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    preview = tmp_path / 'lamp.opp'
    opp.package(source, preview, tier='preview', sign_key=identity['_private'])
    report = props.inspection(preview)
    assert report['tier'] == 'preview' and report['omitted'] == ['references/master/hi.png']
    assert report['included'] == ['references/public/base.png']
    full = package(tmp_path / 'full', signed=True)
    assert props.inspection(full)['tier'] == 'full' and not props.inspection(full)['omitted']


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


def test_bundled_starter_props_install_once_and_back_the_default_roles(tmp_path):
    store = Storage(tmp_path / 'home')
    props.install_starter_props(store)
    assert {record['id'] for record in props.catalog(store)} == {'mmv-guitar', 'mmv-keyboards'}
    guitar = instrument_assets.locate(store, 'guitar')
    assert guitar['prop_id'] == 'mmv-guitar' and guitar['clearance'] == 'public'
    instruments.verify_assets({'assets': {'guitar': guitar}})
    before = (store.home / 'props/mmv-guitar/original.opp').read_bytes()
    props.install_starter_props(store)
    assert (store.home / 'props/mmv-guitar/original.opp').read_bytes() == before
    with pytest.raises(ValueError, match='No drums prop'):
        instrument_assets.locate(store, 'drums')
    assert {item['id']: item['available'] for item in instrument_assets.catalog(store)} == {
        'drums': False, 'bass': False, 'guitar': True, 'keyboards': True}
    (store.home / 'props/mmv-guitar/sheet-0.png').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        instruments.verify_assets({'assets': {'guitar': guitar}})


def test_earlier_local_instrument_sheets_become_props(tmp_path):
    store = Storage(tmp_path / 'home')
    legacy_instrument(store.home, 'bass')
    legacy_instrument(store.home, 'guitar')
    props.install_starter_props(store)
    assert instrument_assets.locate(store, 'bass')['prop_id'] == 'mmv-local-bass'
    assert instrument_assets.locate(store, 'guitar')['prop_id'] == 'mmv-local-guitar'
    assert instrument_assets.locate(store, 'keyboards')['prop_id'] == 'mmv-keyboards'
    assert (store.home / 'instruments/bass/reference.png').is_file()
