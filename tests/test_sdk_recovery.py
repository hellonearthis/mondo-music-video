"""Local SDK completion recovery with synthetic media and a non-submitting proxy."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from mmv.comfy_sdk import ComfySdkH3Backend
from mmv.engine.backends.base import BackendError
from mmv.storage import read_json, write_json


@pytest.fixture
def recovery(tmp_path):
    video = tmp_path / 'fixture.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    'color=c=blue:s=64x64:r=24', '-frames:v', '8', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(video)], check=True)
    song = tmp_path / 'song.wav'
    song.write_bytes(b'synthetic input')
    backend = ComfySdkH3Backend()
    backend.directory = tmp_path / 'renders'
    backend.url = 'http://127.0.0.1:8189'
    backend.timeout = 1
    backend.builder = SimpleNamespace(base={}, map={'targets': {}})
    output = SimpleNamespace(content_type='video/mp4', node_id='92',
                             to_file=lambda path: path.write_bytes(video.read_bytes()))
    remote = SimpleNamespace(id='job-1', status='succeeded', outputs=[output])
    backend.session = SimpleNamespace(jobs=Mock(), submit=Mock(return_value=remote))
    job = dict(segment_id='seg000', images=[], song=str(song), gen_frames=8,
               audio_start_s=0, audio_end_s=1, prompt='blue', duration_input=1,
               seed=0, width=64, height=64, slug='recovery')
    backend.builder.build = Mock(return_value=({}, None))
    backend.builder.map.update(image_refs={'loader_class': 'Image', 'loader_field': 'image'},
                               audio_refs={'loader_class': 'Audio', 'loader_field': 'audio'})
    with patch('mmv.comfy_sdk.slice_audio', side_effect=lambda src, dest, start, duration: dest.write_bytes(b'audio')):
        result = backend.render_segment(**job)
    directory = backend.directory / 'seg000'
    backend.session.submit.reset_mock()
    backend.session.jobs.get.return_value = SimpleNamespace(id='job-1', status='expired', outputs=[])
    return backend, job, directory, result


def test_expired_job_uses_valid_local_completion(recovery):
    backend, job, directory, result = recovery
    manifest = read_json(directory / 'completion.json')
    assert manifest['frame_count'] == 8
    assert manifest['files']['video']['size'] == Path(result['video']).stat().st_size
    assert backend.render_segment(**job) == result
    backend.session.jobs.get.assert_not_called()
    backend.session.submit.assert_not_called()


@pytest.mark.parametrize('damage', ['corrupt', 'missing_manifest', 'partial', 'escape', 'symlink',
                                     'frames', 'short', 'hash', 'malformed', 'result_id', 'manifest_id',
                                     'state', 'missing_result', 'missing_video', 'manifest_endpoint'])
def test_invalid_completion_falls_back_to_expired_proxy(recovery, damage):
    backend, job, directory, result = recovery
    manifest_path = directory / 'completion.json'
    manifest = read_json(manifest_path)
    if damage == 'corrupt':
        Path(result['video']).write_bytes(b'corrupt')
    elif damage == 'missing_manifest':
        manifest_path.unlink()
    elif damage == 'partial':
        Path(result['video']).rename(directory / 'video.mp4.partial')
    elif damage in ('escape', 'symlink'):
        outside = directory.parent / 'outside.mp4'
        Path(result['video']).rename(outside)
        if damage == 'symlink':
            Path(result['video']).symlink_to(outside)
        else:
            result['video'] = str(outside)
            write_json(directory / 'result.json', result)
    elif damage in ('frames', 'short', 'hash', 'manifest_id', 'manifest_endpoint'):
        if damage == 'frames':
            manifest['frame_count'] = 9
        elif damage == 'short':
            job['gen_frames'] = 9
            # Keep the receipt bound to these inputs, testing the independent length check.
            import hashlib
            digest = hashlib.sha256(json.dumps({k:v for k,v in job.items() if k not in ('images', 'song')}, sort_keys=True).encode())
            digest.update(Path(job['song']).read_bytes())
            digest.update(json.dumps(backend.builder.base, sort_keys=True).encode())
            digest.update(json.dumps(backend.builder.map, sort_keys=True).encode())
            record = read_json(directory / 'comfy-request.json')
            record['fingerprint'] = manifest['fingerprint'] = digest.hexdigest()
            write_json(directory / 'comfy-request.json', record)
        elif damage == 'hash':
            manifest['files']['video']['sha256'] = 'wrong'
        elif damage == 'manifest_id':
            manifest['job_id'] = 'other'
        else:
            manifest['endpoint'] = 'http://127.0.0.1:9999'
        write_json(manifest_path, manifest)
    elif damage == 'malformed':
        manifest_path.write_text('{')
    elif damage == 'result_id':
        result['request_id'] = 'other'
        write_json(directory / 'result.json', result)
    elif damage == 'state':
        record = read_json(directory / 'comfy-request.json')
        record['state'] = 'running'
        write_json(directory / 'comfy-request.json', record)
    elif damage == 'missing_result':
        (directory / 'result.json').unlink()
    else:
        Path(result['video']).unlink()
    with pytest.raises(BackendError, match='ended expired'):
        backend.render_segment(**job)
    backend.session.jobs.get.assert_called_once_with('job-1')
    backend.session.submit.assert_not_called()


@pytest.mark.parametrize('change', ['fingerprint', 'endpoint', 'unknown'])
def test_receipt_guards_remain_before_local_completion(recovery, change):
    backend, job, directory, _ = recovery
    record = read_json(directory / 'comfy-request.json')
    if change == 'unknown':
        record.pop('job_id')
        record['state'] = 'unknown'
    else:
        record[change] = 'different'
    write_json(directory / 'comfy-request.json', record)
    with pytest.raises(BackendError, match='unknown' if change == 'unknown' else 'different inputs'):
        backend.render_segment(**job)
    backend.session.jobs.get.assert_not_called()
    backend.session.submit.assert_not_called()


@pytest.mark.parametrize('failure', ['download', 'decode', 'short'])
def test_failed_media_never_writes_completion(recovery, failure):
    backend, job, directory, result = recovery
    record = read_json(directory / 'comfy-request.json')
    record['state'] = 'running'
    write_json(directory / 'comfy-request.json', record)
    original = Path(result['video']).read_bytes()
    def download(path):
        path.write_bytes(b'partial' if failure in ('download', 'decode') else original)
        if failure == 'download':
            raise OSError('interrupted transfer')
    backend.session.jobs.get.return_value = SimpleNamespace(id='job-1', status='succeeded', outputs=[
        SimpleNamespace(content_type='video/mp4', node_id='92', to_file=download)])
    probe = patch('mmv.comfy_sdk.assemble.probe_frames', return_value=7) if failure == 'short' else patch('mmv.comfy_sdk.time.sleep')
    with probe:
        if failure == 'download':
            with pytest.raises(OSError, match='interrupted transfer'):
                backend.render_segment(**job)
        else:
            assert backend.render_segment(**job) == result
    assert not (directory / 'completion.json').exists()
    backend.session.submit.assert_not_called()
