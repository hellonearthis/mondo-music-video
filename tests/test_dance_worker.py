"""Dancing through the real worker boundary: mock writer, temporary data, no services or GPU."""
import json
import pytest
from mmv import dance, quality, lipsync
from mmv.storage import read_json
from tests.test_passage_prerequisites import capture, FIXTURE

DANCE = {'dance_mode': 'group'}
GOOD = '<Subject 1> dances to the beat, hitting a sharp pose on the downbeat.'


def test_a_dancing_passage_gets_the_dance_rules_after_the_base_and_before_the_quality_rules(tmp_path, monkeypatch):
    actual, home, directory, *_ = capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body=GOOD)
    call = actual['calls'][0]
    base = json.loads(FIXTURE.read_text())['sealed']['calls'][0]['system']
    assert call['system'] == base[:-len(quality.WRITER_RULES)] + '\n\n' + dance.DANCE_RULES + quality.WRITER_RULES
    assert call['job']['dance']['tempo_bpm'] == 120.0 and call['job']['dance']['dancers'][0]['subject'] == '<Subject 1>'
    assert (directory / 'writer_system_dance.md').read_text() == call['system']
    assert [c['name'] for c in actual['validation']][:2] == ['schema', 'quality']
    assert 'singing' not in [c['name'] for c in actual['validation']]                  # dancing adds no singing check
    assert actual['validation'][0]['silent_mouths'] is True                              # mouths stay sealed while dancing


def test_a_passage_with_no_dancer_is_the_untouched_path(tmp_path, monkeypatch):
    actual, *_ = capture(tmp_path, monkeypatch, 'sealed')
    assert actual == json.loads(FIXTURE.read_text())['sealed']


def test_singing_and_dancing_combine_without_weakening_the_singing_rules(tmp_path, monkeypatch):
    body = '<Subject 1> sings "hello world" while dancing, hitting a sharp pose on the downbeat.'
    actual, home, directory, *_ = capture(tmp_path, monkeypatch, 'lip_sync', dance_settings=DANCE, body=body)
    system = actual['calls'][0]['system']
    assert lipsync.SINGING_RULES in system
    assert system.index(lipsync.SINGING_RULES) < system.index(dance.DANCE_RULES) < system.index(dance.DANCE_SINGER_SENTENCE)
    assert system.endswith(quality.WRITER_RULES)
    job = actual['calls'][0]['job']
    assert 'singing' in job and 'dance' in job and job['dance']['lead'] == '<Picture 1>'
    assert 'singing' in [c['name'] for c in actual['validation']]


def test_merely_standing_is_rejected_and_nothing_is_cached(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='validation failed'):
        capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body='<Subject 1> stands there.')
    assert not list((tmp_path / 'home' / 'cache' / 'prompts').glob('*.json'))


def test_dance_cache_hits_are_revalidated_and_use_a_versioned_key(tmp_path, monkeypatch):
    first, *_ = capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body=GOOD)
    sealed_keys = json.loads(FIXTURE.read_text())['sealed']['cache_keys']
    assert first['cache_keys'] and first['cache_keys'] != sealed_keys
    second, *_ = capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body=GOOD)
    assert not second['calls']                                                         # reused from the cache
    monkeypatch.setattr(dance, 'dance_problems', lambda *a, **k: ['rejected'])
    with pytest.raises(ValueError, match='validation failed'):                          # the cached prompt is refused, the rewrite too
        capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body=GOOD)


def test_a_draft_with_only_style_advice_left_is_kept_and_recorded(tmp_path, monkeypatch):
    advice = ['Shot 1 has a downbeat; give the dancers an accent, a hit or a deliberate hold there.']
    monkeypatch.setattr(dance, 'dance_problems', lambda *a, **k: advice)
    actual, home, directory, *_ = capture(tmp_path, monkeypatch, 'sealed', dance_settings=DANCE, body=GOOD)
    assert read_json(directory / 'seg000.dance-advice-kept.json') == advice
    assert read_json(directory / 'prompts.json')['seg000']

