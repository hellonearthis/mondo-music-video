"""Exercise the real original polling adapter with simulated long-running work."""
from unittest.mock import Mock

from mmv.engine.comfy import ComfyClient
from mmv.worker import render_timeout


def test_local_polling_allows_long_renders_without_none_comparison(monkeypatch):
    client = ComfyClient('localhost', 8188)
    result = {'status': {'status_str': 'success'}, 'outputs': {}}
    reads = Mock(side_effect=[{}, {}, {'saved-request': result}])
    monkeypatch.setattr(client, '_get', reads)
    clock = iter([0, 4000, 9000])
    monkeypatch.setattr('mmv.engine.comfy.time.time', lambda: next(clock))
    monkeypatch.setattr('mmv.engine.comfy.time.sleep', lambda _: None)
    assert client.wait('saved-request', timeout_s=render_timeout('local_h3')) == result
    assert reads.call_count == 3
    assert render_timeout('comfy_sdk_h3') is None
