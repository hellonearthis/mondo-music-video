"""Independent dance never initiates separation or model preparation."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

from mmv import stems
from mmv.storage import write_json


def test_no_existing_stems_means_no_subprocess_or_gpu(tmp_path, monkeypatch):
    run = Mock(side_effect=AssertionError('must not run'))
    monkeypatch.setattr(stems.subprocess, 'run', run)
    monkeypatch.setattr(stems, 'separate', run)
    monkeypatch.setattr(stems, 'prepare_model', run)
    assert stems.cached_dance_scores(NS(home=tmp_path), 'song', tmp_path / 'score.json') == {}
    run.assert_not_called()


def test_existing_analysis_is_reused_without_model_or_audio(tmp_path, monkeypatch):
    from mmv.engine.analyze import ScoreMap
    root = tmp_path / 'analysis' / 'stems'
    root.mkdir(parents=True)
    path = root / 'driven-song-htdemucs-bass.json'
    ScoreMap('fixture', 48, 22050, 120, 4, beat_frames=[0, 12, 24, 36], beat_energy=[0, 1, 0, 1]).to_json(path)
    monkeypatch.setattr(stems.subprocess, 'run', Mock(side_effect=AssertionError('must not run')))
    result = stems.cached_dance_scores(NS(home=tmp_path), 'song', tmp_path / 'score.json')
    assert result['bass']['beat_energy'] == [0, 1, 0, 1]
    assert set(result) == {'bass'}


def test_grid_edits_apply_to_stem_copies_not_cached_analysis(tmp_path):
    from mmv.engine.analyze import ScoreMap
    root = tmp_path / 'analysis' / 'stems'
    root.mkdir(parents=True)
    path = root / 'driven-song-htdemucs-drums.json'
    ScoreMap('fixture', 48, 22050, 120, 4, beat_frames=[0, 12, 24, 36],
             downbeat_frames=[0], beat_energy=[0, 1, .5, 0]).to_json(path)
    result = stems.cached_dance_scores(NS(home=tmp_path), 'song', tmp_path / 'score.json',
                                      edits={'beat_nudge_ms': 125, 'muted_beats': [1], 'bar_one_beat': 2})
    assert result['drums']['beat_frames'] == [3, 27, 39]
    assert result['drums']['beat_energy'] == [0, .5, 0]
    assert result['drums']['downbeat_frames'] == [27]
    assert ScoreMap.from_json(path).beat_frames == [0, 12, 24, 36]


def test_unreadable_part_falls_back_without_losing_other_parts(tmp_path):
    root = tmp_path / 'analysis' / 'stems'
    root.mkdir(parents=True)
    (root / 'driven-song-htdemucs-drums.json').write_text('broken json')
    assert stems.cached_dance_scores(NS(home=tmp_path), 'song', tmp_path / 'score.json') == {}
