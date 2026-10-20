import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from mmv import package_export as exporter
from mmv.storage import Storage

FFMPEG = shutil.which('ffmpeg')
SECRET = 'sk-abcdefghijklmnopqrstuvwx'


def test_instrument_import_provenance_and_paths_stay_out_of_demo_receipts(tmp_path):
    source = tmp_path / 'prepared.json'
    source.write_text(json.dumps({'instruments': {'notice': 'old internal validation note', 'assets': {'guitar': {
        'path': '/private/family/record.png', 'provenance': 'private origin notes', 'license': 'test', 'sha256': 'hash'}}}}))
    pack = exporter.Package(tmp_path / 'out')
    target = pack.put(source, 'prepared.json')
    exported = target.read_text()
    assert 'family' not in exported and 'private origin notes' not in exported
    assert 'old internal validation note' not in exported
    assert json.loads(exported)['instruments']['assets']['guitar']['sha256'] == 'hash'
    assert 'private origin notes' in source.read_text()


def media(path, kind):
    path.parent.mkdir(parents=True, exist_ok=True)
    if FFMPEG and kind == 'mp4':
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=64x64:d=1:r=12', str(path)], check=True)
    elif FFMPEG and kind == 'wav':
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '1', str(path)], check=True)
    else:
        path.write_bytes(b'fake ' + kind.encode())


def build_run(tmp_path, actors=('animal_pig', 'henchman_1')):
    data = tmp_path / 'data'
    run = data / 'runs' / 'run1'
    (data / 'uploads').mkdir(parents=True)
    media(data / 'uploads' / 'song.wav', 'wav')
    for a in actors:
        (data / 'actors' / a).mkdir(parents=True)
        (data / 'actors' / a / 'reference.png').write_bytes(b'png-' + a.encode())
    write = lambda name, obj: (run / name).parent.mkdir(parents=True, exist_ok=True) or (run / name).write_text(json.dumps(obj))
    write('request.json', {'title': 'Demo', 'song': 'song.wav', 'backend': 'comfy_sdk_h3', 'resolution': '768p', 'aspect': '16:9',
                           'seed': 7, 'megapixels': 0.3, 'actors': list(actors), 'vision_quality_check': True,
                           'analysis_driver': 'drums', 'api_key': SECRET, 'vision_key_env': 'MMV_VISION_API_KEY'})
    write('plan.json', {'fps': 24, 'width': 736, 'height': 416, 'tempo_bpm': 100, 'total_frames': 96, 'segments': [
        {'index': 0, 'song_start_frame': 0, 'musical_frames': 48, 'montage_type': 'standard', 'shots': [{}]},
        {'index': 1, 'song_start_frame': 48, 'musical_frames': 48, 'montage_type': 'type1', 'shots': [{}, {}]}]})
    write('casting.json', {'roster': [{'actor_id': a, 'display_name': a.upper(), 'sheet_path': str(data / 'actors' / a / 'reference.png')}
                                      for a in actors],
                           'segments': {'seg000': {'cast': [{'actor_id': actors[0], 'display_name': actors[0].upper()}]},
                                        'seg001': {'cast': [{'actor_id': actors[1], 'display_name': actors[1].upper()}]}}})
    write('prepared.json', {'lipsync': {'singer': actors[0], 'passages': {'seg000': {'singing': True, 'actor_id': actors[0]},
                                                                          'seg001': {'singing': False}}},
                            'note': 'saved in /home/someone/work/x', 'header': 'Authorization: Bearer abcdefghijklmnop1234'})
    write('renders.json', {'seg000': {'request_id': 'r-0'}})
    write('operation.json', {'started': 1000.0, 'finished': 1125.0})
    write('output.json', {'duration': 4.0})
    write('prompts.json', {'seg000': 'first prompt', 'seg001': 'second prompt'})
    write('writer_jobs/seg000.json', {'job': 1})
    write('api-profiles.json', {'x': 1})
    write('settings.json', {'x': 1})
    (run / 'writer_system.md').write_text('system')
    (run / 'operation.log').write_text('Starting\nComplete\n')
    media(run / 'music-video.mp4', 'mp4')
    for sid in ('seg000', 'seg001'):
        media(run / 'renders' / sid / 'video.mp4', 'mp4')
        media(run / 'renders' / sid / 'audio.wav', 'wav')
        write(f'renders/{sid}/result.json', {'request_id': sid})
        media(run / 'assembly' / 'work' / f'{sid}.mp4', 'mp4')
    return data, run


def test_layout_readme_manifest_and_safety(tmp_path):
    data, run = build_run(tmp_path)
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    for folder in ('01_final', '02_raw_clips', '03_audio', '04_prompts', '05_receipts'):
        assert (out / folder).is_dir()
    assert (out / '01_final/music-video.mp4').is_file() and (out / '03_audio/Demo_song.wav').is_file()
    assert (out / '02_raw_clips/seg001_2.00-4.00s_raw.mp4').is_file()
    assert (out / '04_prompts/seg000_0.00-2.00s_prompt.txt').read_text() == 'first prompt'
    assert (out / '05_receipts/renders/seg000/result.json').is_file()
    assert not any(p.is_symlink() for p in out.rglob('*'))
    readme = (out / 'README.md').read_text()
    assert '| 0 | 0.00-2.00 | 1 | standard | ANIMAL_PIG | ANIMAL_PIG |' in readme
    assert '| 1 | 2.00-4.00 | 2 | type1 | HENCHMAN_1 | - |' in readme
    assert '2 min 5 s' in readme and 'instrument driver: drums' in readme and 'PRIVATE_ACTORS_WARNING' not in readme
    assert 'api-profiles.json' not in str(sorted(p.name for p in out.rglob('*')))
    assert not (out / '05_receipts/settings.json').exists()
    if FFMPEG:
        assert (out / '06_stills/seg000_0.00-2.00s_mid.png').is_file()
    manifest = json.loads((out / 'MANIFEST.json').read_text())['files']
    assert 'README.md' in manifest and 'MANIFEST.json' not in manifest
    for name, info in manifest.items():
        data_bytes = (out / name).read_bytes()
        assert hashlib.sha256(data_bytes).hexdigest() == info['sha256'] and len(data_bytes) == info['bytes']
    assert {p.relative_to(out).as_posix() for p in out.rglob('*') if p.is_file()} - {'MANIFEST.json'} == set(manifest)
    # public actors' references are copied
    assert (out / '07_actor_references/animal_pig.png').read_bytes() == b'png-animal_pig'


@pytest.mark.skipif(not FFMPEG, reason='needs ffmpeg')
def test_renderer_flac_named_wav_becomes_a_real_pcm_wav_and_the_media_guide_and_edl_are_written(tmp_path):
    data, run = build_run(tmp_path)
    # the renderer's audio.wav is FLAC data under a .wav name
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=32000:cl=stereo', '-t', '1', '-c:a', 'flac', '-f', 'flac',
                    str(run / 'renders/seg000/audio.wav')], check=True)
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    _, audio = exporter.probe(out / '02_raw_clips/seg000_0.00-2.00s_raw_audio.wav')
    assert audio['codec_name'] == 'pcm_s24le' and audio['sample_rate'] == '48000'
    readme = (out / 'README.md').read_text()
    assert '## Media format (for your editor)' in readme and 'H264' in readme
    assert 'constant' in readme and 'true PCM WAV' in readme
    edl = (out / '08_timeline/Demo.edl').read_text()
    assert edl.startswith('TITLE: Demo\nFCM: NON-DROP FRAME')
    assert '001  AX       V     C        00:00:00:00 00:00:02:00 01:00:00:00 01:00:02:00' in edl
    assert '002  AX       V     C        00:00:00:00 00:00:02:00 01:00:02:00 01:00:04:00' in edl
    assert '003  AX       AA    C        00:00:00:00 00:00:04:00 01:00:00:00 01:00:04:00' in edl
    assert '* FROM CLIP NAME: seg001_2.00-4.00s_trimmed_for_edit.mp4' in edl and '* FROM CLIP NAME: Demo_song.wav' in edl
    assert 'm = ' not in edl
    names = {p.name for p in (out / '02_raw_clips').iterdir()}
    assert 'seg001_2.00-4.00s_trimmed_for_edit.mp4' in names           # the EDL only names files that exist


@pytest.mark.skipif(not FFMPEG, reason='needs ffmpeg')
def test_studio_clips_keep_their_extension_get_exact_length_copies_and_the_edl_points_at_them(tmp_path):
    data, run = build_run(tmp_path)
    for sid in ('seg000', 'seg001'):
        (run / 'renders' / sid / 'video.mp4').unlink()
        made = subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=s=64x64:r=24:d=3', '-c:v', 'prores_ks',
                               '-profile:v', '4444', '-pix_fmt', 'yuv444p10le', str(run / 'renders' / sid / 'video.mov')])
        if made.returncode:
            pytest.skip('this ffmpeg has no prores_ks encoder')
    receipts = {sid: {'video': str(run / 'renders' / sid / 'video.mov'), 'request_id': sid} for sid in ('seg000', 'seg001')}
    (run / 'renders.json').write_text(json.dumps(receipts))
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    raw = out / '02_raw_clips/seg000_0.00-2.00s_raw.mov'
    assert raw.is_file() and exporter.probe(raw)[0]['codec_name'] == 'prores'
    trimmed = out / '02_raw_clips/seg000_0.00-2.00s_studio_trimmed.mov'
    video, _ = exporter.probe(trimmed)
    assert video['codec_name'] == 'prores' and video['nb_frames'] == '48'              # 2.0 s at 24 fps, not re-encoded
    edl = (out / '08_timeline/Demo.edl').read_text()
    assert '* FROM CLIP NAME: seg000_0.00-2.00s_studio_trimmed.mov' in edl and 'trimmed_for_edit' not in edl
    readme = (out / 'README.md').read_text()
    assert 'studio-quality raw clips' in readme and 'Studio trimmed clip' in readme
    assert 'studio clips are ProRes or FFV1' in readme and 'All video is H.264' not in readme and 'keep the video model' in readme


def test_timecodes_follow_the_frame_rate():
    assert exporter.timecode(0, 24) == '01:00:00:00'
    assert exporter.timecode(24 * 61 + 5, 24) == '01:01:01:05'
    assert exporter.timecode(25, 24, 0) == '00:00:01:01'


def test_secrets_redacted_and_paths_stripped(tmp_path):
    data, run = build_run(tmp_path)
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    request = (out / '05_receipts/request.json').read_text()
    assert SECRET not in request and '[redacted]' in request and 'MMV_VISION_API_KEY' in request
    prepared = (out / '05_receipts/prepared.json').read_text()
    assert 'abcdefghijklmnop1234' not in prepared and '/home/someone' not in prepared and '~/work/x' in prepared
    readme = (out / 'README.md').read_text()
    assert 'request.json`: 1 secret' in readme
    text, count = exporter.sanitize('token = "0123456789abcdef0123456789abcdef0123"\nsk-ABCDEFGHIJKLMNOPQRST')
    assert count == 2 and '0123456789abcdef' not in text and 'sk-ABC' not in text
    assert exporter.sanitize('plain song text, nothing here')[1] == 0


def test_private_actor_refusal_and_allowlist(tmp_path):
    data, run = build_run(tmp_path, actors=('animal_pig', 'studio_star'))
    out = tmp_path / 'out'
    with pytest.raises(ValueError) as error:
        exporter.export(run, out, log=lambda *_: None)
    assert 'studio_star' in str(error.value) and str(error.value).startswith('PRIVATE_ACTORS') and not out.exists()
    exporter.export(run, out, allow_private=True, log=lambda *_: None)
    assert 'PRIVATE_ACTORS_WARNING' in (out / 'README.md').read_text()
    assert (out / '07_actor_references/animal_pig.png').is_file()
    assert not list(out.rglob('studio_star*')) and not any(p.read_bytes() == b'png-studio_star' for p in out.rglob('*.png'))
    assert exporter.PUBLIC_ACTORS == ('animal_pig', 'robobabe1', 'henchman_1', 'human_female_casual_01')


def test_refuses_inside_the_run_and_never_overwrites(tmp_path):
    data, run = build_run(tmp_path)
    with pytest.raises(ValueError, match='inside the production'):
        exporter.export(run, run / 'package', log=lambda *_: None)
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'mine.txt').write_text('keep')
    with pytest.raises(ValueError, match='overwrite'):
        exporter.export(run, out, log=lambda *_: None)
    assert [p.name for p in out.iterdir()] == ['mine.txt']
    empty = tmp_path / 'empty'
    empty.mkdir()
    summary = exporter.export(run, empty, zip_it=True, log=lambda *_: None)      # an empty folder is allowed
    assert (tmp_path / 'empty.zip').is_file() and summary['zip'].endswith('empty.zip') and summary['files'] > 10


def test_the_readme_says_whether_the_prompting_scheme_is_unmodified(tmp_path):
    from unittest.mock import patch
    data, run = build_run(tmp_path)
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    assert 'Prompting scheme: unmodified' in (out / 'README.md').read_text()
    with patch.object(exporter.protected_scheme, 'check', return_value=['mmv/engine/prompts/writer_base.md']):
        changed = tmp_path / 'changed'
        exporter.export(run, changed, log=lambda *_: None)
    assert 'changed Mondo\'s protected prompting scheme (the writer prompt)' in (changed / 'README.md').read_text()


def test_the_exact_keys_stored_in_the_app_are_redacted_wherever_they_appear(tmp_path):
    data, run = build_run(tmp_path)
    (run / 'operation.log').write_text('calling provider with secret-value-12345 attached\n')
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None, secrets=['secret-value-12345'])
    assert 'secret-value-12345' not in (out / '05_receipts/operation.log').read_text()
    assert 'operation.log`: 1 secret' in (out / 'README.md').read_text()


def test_lip_sync_runs_list_the_singer_and_the_lyric_lines(tmp_path):
    data, run = build_run(tmp_path)
    request = json.loads((run / 'request.json').read_text())
    request.update(mouth_mode='lip_sync', lyric_lines=[{'start': 0.5, 'end': 1.5, 'text': 'Hello | there', 'section': 'intro'}])
    (run / 'request.json').write_text(json.dumps(request))
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    readme = (out / 'README.md').read_text()
    assert 'HONK lip sync' in readme and 'main singer: ANIMAL_PIG' in readme
    assert '| 0.50-1.50 | intro | Hello / there |' in readme


def test_app_wrapper_exports_a_finished_run_under_the_data_folder_and_never_twice_over(tmp_path):
    data, run = build_run(tmp_path)
    store = Storage(data)
    store.save_key('WAVESPEED_API_KEY', 'stored-key-abcdef123456')
    (run / 'output.json').unlink()
    with pytest.raises(ValueError, match='finished'):
        exporter.export_package(store, 'run1')                    # no output.json yet
    (run / 'output.json').write_text(json.dumps({'duration': 4.0, 'file': 'music-video.mp4'}))
    first = exporter.export_package(store, 'run1')
    # human-friendly name: the title and the date and time the video was made (operation.json finished = 1125.0 -> 1970-01-01)
    import re, time as _time
    assert re.fullmatch(r'Demo_\d{4}-\d\d-\d\d_\d{4}', Path(first['path']).name) and first['private_actors'] == []
    assert Path(first['path']).name == 'Demo_' + _time.strftime('%Y-%m-%d_%H%M', _time.localtime(1125.0))
    second = exporter.export_package(store, 'run1', zip_it=True)
    assert second['path'] == first['path'] + '-2' and Path(second['zip']).is_file() and second['zip'].endswith('-2.zip')
    third = exporter.export_package(store, 'run1')
    assert third['path'] == first['path'] + '-3'
    with pytest.raises(ValueError):
        exporter.export_package(store, '../../etc')
    with pytest.raises(ValueError):
        exporter.export_package(store, 'missing')


def test_missing_optional_files_are_listed(tmp_path):
    data, run = build_run(tmp_path)
    (run / 'music-video.mp4').unlink()
    (run / 'quality.json').unlink(missing_ok=True)
    out = tmp_path / 'out'
    exporter.export(run, out, log=lambda *_: None)
    readme = (out / 'README.md').read_text()
    assert 'quality.json' in readme and 'no finished video' in readme
