from types import SimpleNamespace as NS
from pathlib import Path

from mmv.jobs import output_run_id
from mmv.storage import write_json, identifier


def test_song_name_timestamp_safe_length_and_collision(tmp_path):
    store = NS(home=tmp_path)
    write_json(tmp_path / 'uploads' / 'random.wav.metadata.json', {'name': '../My Song (Mix).wav'})
    request = {'song': 'random.wav', 'title': 'different title'}
    first = output_run_id(store, request, now=0)
    assert first.startswith('my_song_mix_')
    assert identifier(first) == first
    (tmp_path / 'runs' / first).mkdir(parents=True)
    assert output_run_id(store, request, now=0) == first + '-2'
    long = output_run_id(store, {'title': 'x' * 160}, now=0)
    assert len(long) <= 64
    assert identifier(output_run_id(store, {'title': '/// !!!'}, now=0))


def test_legacy_upload_uses_title_and_windows_names_are_safe(tmp_path):
    store = NS(home=tmp_path)
    assert output_run_id(store, {'song': 'old.wav', 'title': 'Known Title'}, now=0).startswith('known_title_')
    write_json(tmp_path / 'uploads' / 'x.wav.metadata.json', {'name': r'C:\music\Good Song.wav'})
    assert output_run_id(store, {'song': 'x.wav'}, now=0).startswith('good_song_')
