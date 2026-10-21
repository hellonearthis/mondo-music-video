import json

from mmv import dance
LOCAL = {'writer_mode': 'local', 'writer_url': 'http://127.0.0.1:1/v1', 'comfy_url': 'http://127.0.0.1:1', 'writer_model': 'x', 'writer_launch': '', 'writer_cwd': ''}

from mmv.writer_json import MAX_FREE_RETRIES, draft_feedback, escape_control_characters, is_broken_json


def _no_writer_service(monkeypatch):
    monkeypatch.setattr('mmv.runtime.http_ok', lambda *a: True)
    monkeypatch.setattr('mmv.runtime.start_service', lambda *a, **k: None)
    def stop(*a, **k):
        from tests.test_passage_prerequisites import StopBeforeRender
        raise StopBeforeRender()
    monkeypatch.setattr('mmv.runtime.stop_confirmed', stop)


def test_control_characters_inside_strings_are_escaped_and_nothing_else_changes():
    raw = '{\n "a": "one\ntwo\tthree", "b": ["x"]\n}'
    assert json.loads(escape_control_characters(raw)) == {'a': 'one\ntwo\tthree', 'b': ['x']}
    assert escape_control_characters('{"a": "ok"}') == '{"a": "ok"}'
    assert escape_control_characters('{"a": "cut off') == '{"a": "cut off'      # truncated output is not invented


def test_broken_json_is_recognised_only_when_it_is_the_sole_problem():
    assert is_broken_json(['writer did not return valid JSON: Unterminated string'])
    assert not is_broken_json(['Shot 1: describe what <Picture 1> is doing'])
    assert not is_broken_json([]) and MAX_FREE_RETRIES == 2


def test_previous_draft_is_sent_back_with_retry_feedback():
    text = draft_feedback(['Shot one text', 'Shot two text'])
    assert 'previous draft' in text and '"Shot one text"' in text and 'exactly as written' in text


def test_mouth_clause_is_dropped_but_the_move_in_the_same_sentence_counts():
    assert dance._dancing_text('Her arm swings wide, her lips are sealed, her hips lunge.', False) == 'Her arm swings wide, her hips lunge.'
    assert dance._dancing_text('Her lips are sealed.', False) == ''
    assert dance._dancing_text('Her face is perfectly still, her jaw relaxed.', False) == ''
    assert dance._dancing_text('Her face is calm.', False) == 'Her face is calm.'
    assert dance.MOVE.search('a deep lunge') and dance.MOVE.search('quick footwork')
    assert dance.EMPHASIS.search('a sharp arm sweep on the beat')


def test_worker_retries_unparsable_replies_without_spending_an_attempt(tmp_path, monkeypatch):
    _no_writer_service(monkeypatch)
    from tests.test_passage_prerequisites import capture
    good = json.dumps({'style_opening': 'Daylight photography.', 'shot_bodies': [
        '<Subject 1> strums strings of the guitar <Picture 2> while fretting.'], 'overall_soundscape': 'Wind.'})
    settings = {'instrument_mode': 'perform', 'actors': ['fixture_actor'], 'instrument_assignments': {'fixture_actor': 'guitar'}}
    local = LOCAL
    # Two cut-off replies in a row, then a good one: the production still succeeds and wrote three drafts.
    actual, _, directory, *_ = capture(tmp_path, monkeypatch, 'sealed', instrument_settings=settings, prepared_settings=local,
                                       replies=['{"style_opening": "cut', '{"style_opening": "cut', good])
    assert len(actual['calls']) == 3 and (directory / 'seg000.writer-3.json').exists()
    assert json.loads((directory / 'seg000.validation-1.json').read_text())[0].startswith('writer did not return valid JSON')
    # A raw newline inside a string is repaired without any retry.
    raw_newline = good.replace('while fretting.', 'while\nfretting.')
    actual, *_ = capture(tmp_path / 'again', monkeypatch, 'sealed', instrument_settings=settings, prepared_settings=local, replies=[raw_newline])
    assert len(actual['calls']) == 1


def test_worker_gives_up_after_the_free_retries_and_sends_the_draft_back(tmp_path, monkeypatch):
    _no_writer_service(monkeypatch)
    from tests.test_passage_prerequisites import capture
    bad = json.dumps({'style_opening': 'Daylight photography.', 'shot_bodies': ['<Subject 1> strums the strings of the guitar while fretting.'],
                      'overall_soundscape': 'Wind.'})
    settings = {'instrument_mode': 'perform', 'actors': ['fixture_actor'], 'instrument_assignments': {'fixture_actor': 'guitar'}}
    actual, *_ = capture(tmp_path, monkeypatch, 'sealed', instrument_settings=settings, prepared_settings=LOCAL,
                         replies=[bad] * 4, expect=ValueError, match='validation failed')
    assert len(actual['calls']) == 4
    assert 'previous draft' in actual['calls'][1]['system'] and 'strums the strings of the guitar' in actual['calls'][1]['system']
    assert 'previous draft' not in actual['calls'][0]['system']


def test_movement_family_accepts_natural_wording_for_the_assigned_family():
    words = dance.MOVEMENT_WORDS
    for text in ('performs a slow, deliberate vertical sway', 'flexes and extends her legs', 'her body rising and falling'):
        assert words['vertical'].search(text), text
    for text in ('slides her weight sideways', 'her weight shifted to one side', 'a side-lunge pose'):
        assert words['lateral'].search(text), text
    assert words['rotation'].search('twirls on the spot') and not words['rotation'].search('stands still')
    assert not words['vertical'].search('holds a lateral pose')
