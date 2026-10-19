"""Vision protocol and conservative verdict policy with local synthetic media only."""
import base64
import json
import io
import urllib.error
from unittest.mock import patch
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from mmv.vision_check import judge_clip, judge_frame, sample_frames, vision_command


@contextmanager
def server(replies):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, body))
            reply = replies[(len(requests) - 1) % len(replies)]
            if isinstance(reply, float):
                time.sleep(reply)
                reply = {'frame_fill': 'full', 'defects': []}
            if isinstance(reply, int):
                self.send_error(reply)
                return
            content = reply if isinstance(reply, str) else json.dumps(reply)
            data = json.dumps({'choices': [{'message': {'content': content}}]}).encode()
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
    try:
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    except PermissionError:
        # Restricted runners cannot bind sockets. Exercise the same wire payload
        # and responses in process; unrestricted runs use the actual HTTP server.
        def transport(request, timeout):
            requests.append((request.selector, json.loads(request.data)))
            reply = replies[(len(requests) - 1) % len(replies)]
            if isinstance(reply, float):
                if reply > timeout:
                    raise TimeoutError('scripted response timeout')
                reply = {'frame_fill': 'full', 'defects': []}
            if isinstance(reply, int):
                raise urllib.error.HTTPError(request.full_url, reply, 'scripted failure', {}, None)
            content = reply if isinstance(reply, str) else json.dumps(reply)
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': content}}]}).encode())
        with patch('mmv.vision_check.urllib.request.urlopen', side_effect=transport):
            yield 'http://127.0.0.1:9999/v1', requests
    else:
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{http.server_port}/v1', requests
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
    for path, body in requests:
        assert path == '/v1/chat/completions'
        assert body['temperature'] == 0
        assert len(body['messages']) == 1
        assert body['messages'][0]['role'] == 'user'
        content = body['messages'][0]['content']
        images = [c for c in content if c['type'] == 'image_url']
        assert len(images) == 1
        assert base64.b64decode(images[0]['image_url']['url'].split(',', 1)[1]).startswith(b'\x89PNG')
        assert 'unknown' in content[0]['text']


@pytest.fixture(scope='module')
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp('vision') / 'clip.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=s=96x64:r=24:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
    return path


@pytest.mark.parametrize('frames,trim,starts,budget', [
    (0, 0, [], 8), (1, 1, [0], 8), (2, 2, [0, 1], 8), (24, 24, [0, 1, 2, 5, 12], 8),
    (100, 50, [-5, 0, 12, 12, 30, 99], 8), (100, 100, list(range(0, 100, 5)), 3),
    (24, 24, [], 0), (24, 24, [0, 12], 1), (3, 3, [], 20)])
def test_sampling(frames, trim, starts, budget):
    found = sample_frames(frames, trim, starts, budget)
    assert found == sample_frames(frames, trim, starts, budget)
    assert found == sorted(set(found))
    assert len(found) <= budget
    assert all(0 <= n < min(frames, trim) for n in found)
    assert all(not cut - 2 <= n < cut + 2 for n in found for cut in starts if 0 < cut < min(frames, trim))
    if frames == 1:
        assert found == [0]


def test_sampling_path_and_trim(clip):
    assert sample_frames(clip, 12, [0, 6]) == sample_frames(24, 12, [0, 6])
    assert len(sample_frames(24, 24, [0])) == 8
    assert any(n < 12 for n in sample_frames(24, 24, [0, 12]))
    assert any(n >= 12 for n in sample_frames(24, 24, [0, 12]))


FULL = {'frame_fill': 'full', 'defects': []}
BORDER = {'frame_fill': 'bordered', 'defects': ['letterboxing']}
UNKNOWN = {'frame_fill': 'unknown', 'defects': []}


@pytest.mark.parametrize('replies,allowed,status,retry', [
    ([FULL], False, 'pass', False), ([BORDER], False, 'fail', True),
    ([BORDER] + [FULL] * 7, False, 'warn', False), ([BORDER], True, 'pass', False),
    ([dict(FULL, defects=['severe anatomical distortion'])], False, 'warn', False),
    ([dict(FULL, defects=['text or watermark'])], False, 'warn', False),
    ([dict(FULL, defects=['text on screen'])], False, 'warn', False),
    ([dict(FULL, defects=['two images superimposed'])], False, 'warn', False),
    ([dict(FULL, defects=['split screen'])], False, 'fail', True),
    ([dict(FULL, defects=['photo print'])], False, 'fail', True),
    ([dict(FULL, framing='present')], False, 'fail', True),
    ([dict(BORDER, defects=['letterboxing', 'watermark'])], True, 'warn', False),
    ([UNKNOWN], False, 'error', False), (['not JSON'], False, 'error', False),
    ([500], False, 'error', False), ([UNKNOWN, FULL], False, 'pass', False),
    ([500, FULL], False, 'pass', False)])
def test_verdict_matrix(clip, replies, allowed, status, retry):
    with server(replies) as (url, requests):
        result = judge_clip(clip, 24, [0, 12], url, 'vision', allowed)
        assert (result['status'], result['retry']) == (status, retry)
        assert len(requests) == 8
        assert isinstance(result['problems'], list)
        if allowed:
            assert not any('letterbox' in p or 'framing' in p for p in result['problems'])


@pytest.mark.parametrize('reply', ['[]', '{}', '{"frame_fill":"full","defects":[1]}',
                                  '{"frame_fill":"full","defects":[],"framing":true}', '```json\nbroken\n```'])
def test_invalid_output(reply):
    with server([reply]) as (url, _):
        assert judge_frame(url, 'vision', b'\x89PNGtest', 1)['error']


def test_fences_and_timeout(clip):
    with server(['```json\n' + json.dumps(FULL) + '\n```']) as (url, _):
        assert judge_frame(url, 'vision', b'\x89PNGtest', 1) == FULL
    with server([0.1]) as (url, _):
        assert judge_frame(url, 'vision', b'\x89PNGtest', 0.01)['error']
    with server([FULL]) as (url, requests):
        assert judge_clip(clip, 0, [], url, 'vision')['status'] == 'error'
        assert not requests
        assert judge_clip(str(clip) + '.missing', 24, [], url, 'vision')['status'] == 'error'


def test_command(tmp_path):
    model = tmp_path / 'Qwen3-VL-8B-Q4_K_M.gguf'
    model.touch()
    launch = json.dumps(['llama-server', '-m', str(model), '-ngl', 'all', '-fa', 'on', '--port=123',
                         '--alias', 'writer', '-c', '65536', '--temp', '.7', '-np', '4',
                         '--cache-reuse', '256', '--cache-type-k', 'q4_0', '--cache-type-v', 'q4_0', '--jinja'])
    with pytest.raises(ValueError, match='matching sibling'):
        vision_command(launch, 9000)
    (tmp_path / 'mmproj-unrelated-f16.gguf').touch()
    with pytest.raises(ValueError, match='matching sibling'):
        vision_command(launch, 9000)
    projector = tmp_path / 'mmproj-Qwen3-VL-8B-f16.gguf'
    projector.touch()
    argv = vision_command(launch, 9000)
    for flag, value in [('-m', str(model)), ('--mmproj', str(projector)), ('--port', '9000'),
                        ('--alias', 'mmv-vision'), ('-c', '16384'), ('--temp', '0'), ('-ngl', 'all'), ('-fa', 'on')]:
        assert argv.count(flag) == 1
        assert argv[argv.index(flag) + 1] == value
    assert '--jinja' in argv
    assert not any(a.startswith(('--cache', '-np', '--port=')) for a in argv)
    (tmp_path / 'mmproj-Qwen3-VL-8B-bf16.gguf').touch()
    with pytest.raises(ValueError, match='found 2'):
        vision_command(launch, 9000)


@pytest.mark.parametrize('launch', ['null', '[]', 'bad', '[1]', '["server"]', '["server", "-m"]'])
def test_bad_launch(launch):
    with pytest.raises(ValueError):
        vision_command(launch, 9000)


@pytest.mark.parametrize('option', ['-hf', '--model-url', '--mmproj-url', '--mmproj-auto'])
def test_command_refuses_download_options(option):
    with pytest.raises(ValueError, match='download option'):
        vision_command(json.dumps(['server', '-m', '/tmp/model.gguf', option, 'remote']), 9000)


def test_decode_errors_do_not_retry(clip):
    with patch('mmv.vision_check.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 1)):
        assert judge_clip(clip, 24, [], 'http://unused/v1', 'vision')['status'] == 'error'
    with patch('mmv.vision_check._frame_count', return_value=24), patch(
            'mmv.vision_check.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 1)):
        result = judge_clip(clip, 24, [], 'http://unused/v1', 'vision')
        assert result['status'] == 'error' and not result['retry']


def test_full_size_frames_and_no_token_cap_by_default_compact_opts_in(monkeypatch):
    import io
    import json
    from mmv import vision_check
    assert vision_check._select_filter('eq(n\\,3)', False) == 'select=eq(n\\,3)'
    assert "scale='min(512,iw)':-2" in vision_check._select_filter('eq(n\\,3)', True)
    sent = []

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        sent.append(json.loads(request.data))
        return Reply(json.dumps({'choices': [{'message': {'content': '{"frame_fill":"full","defects":[]}'}}]}).encode())

    monkeypatch.setattr(vision_check.urllib.request, 'urlopen', fake_urlopen)
    vision_check.judge_frame('http://x/v1', 'm', b'png')
    vision_check.judge_frame('http://x/v1', 'm', b'png', max_tokens=vision_check.COMPACT_MAX_TOKENS)
    assert 'max_tokens' not in sent[0]
    assert sent[1]['max_tokens'] == 160
