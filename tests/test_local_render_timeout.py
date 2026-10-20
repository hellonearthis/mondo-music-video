"""Exercise the real original polling adapter with simulated long-running work."""
from unittest.mock import Mock

import pytest

from mmv.engine.comfy import ComfyClient
from mmv.storage import DEFAULTS
from mmv.worker import render_timeout


def test_local_polling_allows_long_renders_without_none_comparison(monkeypatch):
    client = ComfyClient('localhost', 8188)
    result = {'status': {'status_str': 'success'}, 'outputs': {}}
    reads = Mock(side_effect=[{}, {}, {'saved-request': result}])
    monkeypatch.setattr(client, '_get', reads)
    clock = iter([0, 4000, 9000])
    monkeypatch.setattr('mmv.engine.comfy.time.time', lambda: next(clock))
    monkeypatch.setattr('mmv.engine.comfy.time.sleep', lambda _: None)
    assert client.wait('saved-request', timeout_s=render_timeout('local_h3', 0)) == result
    assert reads.call_count == 3
    assert render_timeout('comfy_sdk_h3') is None


def test_default_wait_is_two_hours_per_clip_and_zero_means_unlimited():
    assert DEFAULTS['render_timeout_minutes'] == 120
    assert render_timeout('local_h3', DEFAULTS['render_timeout_minutes']) == 7200.0
    assert render_timeout('local_h3', 0) == float('inf')


def test_hung_renderer_fails_with_a_timeout_at_the_default(monkeypatch):
    client = ComfyClient('localhost', 8188)
    monkeypatch.setattr(client, '_get', Mock(return_value={}))
    clock = iter([0, 100, 8000])
    monkeypatch.setattr('mmv.engine.comfy.time.time', lambda: next(clock))
    monkeypatch.setattr('mmv.engine.comfy.time.sleep', lambda _: None)
    with pytest.raises(TimeoutError, match='7200'):
        client.wait('stuck', timeout_s=render_timeout('local_h3'))
