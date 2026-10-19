import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmv import lyrics
from mmv.storage import Storage


def words(text, start=0.0, step=0.4, gap_after=None):
    result, t = [], start
    for i, token in enumerate(text.split()):
        result.append({'word': token, 'start': round(t, 2), 'end': round(t + step - 0.05, 2)})
        t += step + ((gap_after or {}).get(i, 0.0))
    return result


SUNO_LYRICS = """[intro]
Yes! I am your help fren. 
We will only use the Web gooey on your TV.
No coding.
No terminal.
No deleting anything.

[chorus]
I will give you short steps.
One action per line.

I will tell you exactly which buttons to click in CAPITALS.

[verse]
What are we doing today?
Make a music video?
Add a new actor?
Check the schedule?

Tell me what you want to do, and I will guide your mouse clicks!
"""


class LyricsTests(unittest.TestCase):
    def test_owner_suno_lyrics_have_sections_without_marker_pseudo_lines(self):
        lines = [line.strip() for line in SUNO_LYRICS.splitlines() if line.strip() and not line.startswith('[')]
        heard = words(' '.join(lines).lower(), start=1.0)
        timed = lyrics.align_lines(SUNO_LYRICS, heard)
        self.assertEqual([line['text'] for line in timed], lines)
        self.assertEqual([line['section'] for line in timed], ['intro'] * 5 + ['chorus'] * 3 + ['verse'] * 5)
        self.assertTrue(all(line['timing'] == 'matched' and line['matched'] == 1.0 for line in timed))
        self.assertTrue(all(not line['backing'] for line in timed))

    def test_suno_markers_inline_labels_and_backing_vocals(self):
        parsed = lyrics.parse_lyrics('[ Verse   1 ]\nHello (my friend)\n(ooh ooh)\n[Chorus] la la\n[Male Vocal]\nSing again')
        self.assertEqual(parsed, [
            {'text': 'Hello my friend', 'section': 'verse 1', 'kind': 'sung', 'backing': False},
            {'text': 'ooh ooh', 'section': 'verse 1', 'kind': 'sung', 'backing': True},
            {'text': 'la la', 'section': 'chorus', 'kind': 'sung', 'backing': False},
            {'text': 'Sing again', 'section': 'male vocal', 'kind': 'sung', 'backing': False}])
        timed = lyrics.align_lines('[Verse 1] Hello\n(ooh ooh)', words('hello ooh ooh'))
        self.assertEqual([line['backing'] for line in timed], [False, True])
        self.assertEqual([line['section'] for line in timed], ['verse 1', 'verse 1'])
        self.assertIsNone(lyrics.parse_lyrics('hello')[0]['section'])
        self.assertEqual(len(lyrics.parse_lyrics('[' + 'a' * 50 + '] hello')[0]['section']), 40)

    def test_instrumental_blocks_are_parsed_but_not_timed(self):
        for marker in ('Instrumental', 'Guitar Solo', 'Interlude', 'Break', 'Drop', 'Beat'):
            with self.subTest(marker=marker):
                text = '[Verse 1] hello friend\n[' + marker + ']\nThese look like lyrics\n[Chorus] sing again'
                parsed = lyrics.parse_lyrics(text)
                self.assertEqual(parsed[1]['kind'], 'instrumental')
                timed = lyrics.align_lines(text, words('hello friend sing again'))
                self.assertEqual([line['text'] for line in timed], ['hello friend', 'sing again'])
                self.assertTrue(all(line['matched'] == 1.0 for line in timed))
        with self.assertRaises(ValueError):
            lyrics.align_lines('[Instrumental]\nonly music', words('only music'))

    def test_instrumental_detection_uses_whole_words_and_voice_words_win(self):
        sung = ('Vocal Solo', 'Breakdown', 'Dropout Chorus', 'Beatbox Verse', 'Rap Break', 'Spoken Break', 'Choir Interlude')
        for marker in sung:
            with self.subTest(marker=marker):
                self.assertEqual(lyrics.parse_lyrics(f'[{marker}]\nhello there')[0]['kind'], 'sung')
        for marker in ('Guitar Solo', 'Instrumental Break', 'Drum Break', 'Synth Interlude'):
            with self.subTest(marker=marker):
                self.assertEqual(lyrics.parse_lyrics(f'[{marker}]\nla la')[0]['kind'], 'instrumental')

    def test_empty_markers_and_huge_lyrics_are_rejected(self):
        for text in ('', '   ', '[Verse 1]\n[Chorus]', '()'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                lyrics.parse_lyrics(text)
        with self.assertRaises(ValueError):
            lyrics.parse_lyrics('a' * 16001)
        self.assertEqual(len(lyrics.parse_lyrics('a' * 16000)[0]['text']), 16000)

    def test_repeated_suno_chorus_matches_the_later_words_after_the_verse(self):
        chorus, verse = 'We sing together tonight', 'Another story fills the sky'
        first = words(chorus, start=1.0)
        middle = words(verse, start=10.0)
        second = words(chorus, start=20.0)
        timed = lyrics.align_lines('[Chorus]\n' + chorus + '\n[Verse 1]\n' + verse + '\n[Chorus]\n' + chorus,
                                   first + middle + second)
        self.assertEqual([line['start'] for line in timed], [1.0, 10.0, 20.0])
        self.assertGreater(timed[2]['start'], timed[1]['end'])
        self.assertTrue(all(line['timing'] == 'matched' for line in timed))

    def test_group_lines_drops_short_hallucinated_blips(self):
        heard = words('Last sung line.', start=50.0)
        heard += [{'word': "We'll be right back.", 'start': 56.5, 'end': 56.6}]
        self.assertEqual([line['text'] for line in lyrics.group_lines(heard)], ['Last sung line.'])
        self.assertEqual(len(lyrics.group_lines([{'word': 'held', 'start': 1.0, 'end': 1.25}])), 1)

    def test_words_group_into_lines_at_pauses_and_sentence_ends(self):
        heard = words('Interdimensional lover I dated you all across time and space. Hello again', gap_after={1: 1.5})
        lines = lyrics.group_lines(heard)
        self.assertEqual(lines[0]['text'], 'Interdimensional lover')                # long pause
        self.assertEqual(lines[1]['text'], 'I dated you all across time and space.')   # sentence end
        self.assertEqual(lines[2]['text'], 'Hello again')
        self.assertTrue(all(line['end'] > line['start'] for line in lines))
        self.assertEqual(lyrics.group_lines([]), [])
        long = lyrics.group_lines(words('one ' * 25))
        self.assertTrue(all(len(line['text'].split()) <= lyrics.MAX_LINE_WORDS for line in long))

    def test_pasted_lyrics_are_timed_from_what_was_heard(self):
        heard = words('interdimensional lover i dated you all across time and space', start=10.0)
        timed = lyrics.align_lines('Interdimensional lover,\nI dated you\nAll across time and space', heard)
        self.assertEqual([t['timing'] for t in timed], ['matched'] * 3)
        self.assertEqual(timed[0]['start'], 10.0)
        self.assertLess(timed[0]['end'], timed[1]['start'] + 0.01)
        self.assertEqual(timed[1]['text'], 'I dated you')
        self.assertTrue(all(timed[i]['start'] >= timed[i - 1]['end'] for i in range(1, 3)))

    def test_unmatched_lines_are_interpolated_between_neighbours_and_flagged(self):
        heard = words('first line words here', start=2.0) + words('last line words here', start=20.0)
        timed = lyrics.align_lines('first line words here\nsomething never sung at all\nlast line words here', heard)
        self.assertEqual([t['timing'] for t in timed], ['matched', 'interpolated', 'matched'])
        self.assertGreaterEqual(timed[1]['start'], timed[0]['end'])
        self.assertLessEqual(timed[1]['end'], timed[2]['start'] + 0.01)

    def test_a_guessed_line_gets_a_short_window_not_the_whole_gap_and_weak_matches_are_uncertain(self):
        heard = words('first line words here', start=2.0) + words('last line words here', start=40.0)
        timed = lyrics.align_lines('first line words here\nnever heard line\nlast line words here', heard)
        guessed = timed[1]
        self.assertEqual(guessed['timing'], 'interpolated')
        self.assertLessEqual(guessed['end'] - guessed['start'], lyrics.GUESS_SECONDS + 0.01)
        weak = lyrics.align_lines('alpha beta gamma delta epsilon zeta\nfirst line words here', words('alpha first line words here', start=1.0))
        self.assertEqual(weak[0]['timing'], 'uncertain')
        self.assertEqual(weak[1]['timing'], 'matched')

    def test_alignment_refuses_text_that_does_not_match_the_song(self):
        heard = words('completely different words being sung over here', start=1.0)
        with self.assertRaisesRegex(ValueError, 'do not match'):
            lyrics.align_lines('zebra quantum pickle\nvelocity marmalade', heard)
        with self.assertRaises(ValueError):
            lyrics.align_lines('   \n ', heard)
        with self.assertRaises(ValueError):
            lyrics.align_lines('some words', [])

    def test_repeated_choruses_stay_in_order(self):
        heard = words('la la la hello world la la la hello world', start=0.0)
        timed = lyrics.align_lines('la la la hello world\nla la la hello world', heard)
        self.assertLess(timed[0]['start'], timed[1]['start'])
        self.assertTrue(all(t['end'] > t['start'] for t in timed))

    def test_the_gpu_is_used_only_when_the_model_fits_and_advice_follows_the_hardware(self):
        from mmv import stems
        for free, model, expected in ((24.0, 'large-v3', 'cuda'), (8.0, 'large-v3', 'cpu'), (8.0, 'medium', 'cuda'), (1.0, 'tiny', 'cpu')):
            with patch.object(stems, '_gpu', return_value={'gpu': 'T', 'free': int(free * 1024 ** 3), 'total': 0}):
                self.assertEqual(lyrics.pick_device(model), expected, (free, model))
        big = lyrics.recommend({'gpu': 'Big', 'vram_free_gb': 22.0, 'vram_total_gb': 24.0, 'ram_gb': 64.0})
        self.assertEqual((big['model'], big['device']), ('large-v3', 'cuda'))
        small = lyrics.recommend({'gpu': 'Small', 'vram_free_gb': 6.0, 'vram_total_gb': 8.0, 'ram_gb': 4.0})
        self.assertEqual(small['device'], 'cpu')
        self.assertTrue(any('has not been measured' in note for note in small['notes']))
        self.assertTrue(any('System RAM is 4.0 GB' in note for note in small['notes']))

    def test_status_reports_cached_models_and_nothing_is_downloaded_unasked(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'large-v3.pt').write_bytes(b'x')
            with patch.dict(os.environ, {'MMV_WHISPER_DIR': temp}), patch.object(lyrics, 'available', return_value=False):
                report = lyrics.status(Storage(temp))
                self.assertTrue(report['models']['large-v3']['cached'])
                self.assertFalse(report['models']['small']['cached'])
                self.assertEqual(report['models']['small']['download'], 'about 470 MB')
                with self.assertRaisesRegex(ValueError, 'Whisper add-on'):
                    lyrics.require_ready('large-v3')
            with patch.dict(os.environ, {'MMV_WHISPER_DIR': temp}), patch.object(lyrics, 'available', return_value=True):
                lyrics.require_ready('large-v3')
                with self.assertRaisesRegex(ValueError, 'not downloaded yet'):
                    lyrics.require_ready('small')
                with self.assertRaises(ValueError):
                    lyrics.require_ready('gigantic')

    def test_transcribe_runs_the_worker_once_and_caches_by_song_source_and_model(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            Path(argv[3]).write_text(json.dumps({'language': 'en', 'words': words('hello there friend', start=1.0)}))
            import subprocess
            return subprocess.CompletedProcess(argv, 0, '', '')

        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'small.pt').write_bytes(b'x')
            store = Storage(temp)
            song = Path(temp) / 'song.wav'
            song.write_bytes(b'x')
            with patch.dict(os.environ, {'MMV_WHISPER_DIR': temp, 'MMV_LYRICS_PYTHON': '/opt/whisper/bin/python'}), \
                    patch.object(lyrics, 'available', return_value=True), patch.object(lyrics, 'pick_device', return_value='cpu'), \
                    patch.object(lyrics.subprocess, 'run', side_effect=fake_run):
                first = lyrics.transcribe(store, song, 'abc', 'small', use_vocals=False)
                second = lyrics.transcribe(store, song, 'abc', 'small', use_vocals=False)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], '/opt/whisper/bin/python')
            self.assertEqual(calls[0][-1], 'cpu')
            self.assertEqual(first['source'], 'mix')
            self.assertEqual(first['lines'], second['lines'])
            self.assertEqual(first['lines'][0]['text'], 'hello there friend')


if __name__ == '__main__':
    unittest.main()
