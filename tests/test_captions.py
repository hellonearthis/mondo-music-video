import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mmv import captions

FFMPEG = shutil.which('ffmpeg')
LINES = [{'start': 1.0, 'end': 3.0, 'text': 'Hello {world} \\ again', 'timing': 'matched'},
         {'start': 3.5, 'end': 3.6, 'text': 'short', 'timing': 'manual'},
         {'start': 4.0, 'end': 5.0, 'text': 'guessed', 'timing': 'interpolated'},
         {'start': 8.0, 'end': 12.0, 'text': 'runs past the song', 'timing': 'matched'}]


def video(path, seconds=6, fps=24):
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=blue:s=160x90:r={fps}:d={seconds}', '-f', 'lavfi',
                    '-i', f'sine=frequency=440:duration={seconds}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def frames(path):
    return captions._probe_size(path)[2]


class CueTests(unittest.TestCase):
    def test_settings(self):
        self.assertIsNone(captions.clean({}))
        self.assertIsNone(captions.clean({'mode': 'off'}))
        self.assertEqual(captions.clean({'mode': 'burned'}), {'mode': 'burned', 'style': 'classic', 'position': 'bottom', 'size': 'medium'})
        with self.assertRaises(ValueError):
            captions.clean({'mode': 'neon'})

    def test_cues_shift_skip_guesses_hold_short_lines_and_stop_at_the_song_end(self):
        got = captions.cues(LINES, 2.0, song_s=8.0, total_s=12.0)       # the song occupies 2..10 s of the video; an ident follows
        self.assertEqual(got, [(3.0, 5.0, 'Hello {world} \\ again'), (5.5, 5.9, 'short')])
        self.assertTrue(all(end <= 10.0 for _, end, _ in got))
        self.assertNotIn('guessed', [t for _, _, t in got])
        unconfirmed = captions.cues([{'start': 1, 'end': 2, 'text': 'maybe', 'timing': 'uncertain'}], 0.0, 5.0, 5.0)
        self.assertEqual(unconfirmed, [])

    def test_cues_never_overlap_and_the_video_end_wins_over_the_song_end(self):
        got = captions.cues([{'start': 0, 'end': 5, 'text': 'a'}, {'start': 2, 'end': 9, 'text': 'b'}], 0.0, song_s=20.0, total_s=6.0)
        self.assertEqual(got, [(0.0, 2.0, 'a'), (2.0, 6.0, 'b')])

    def test_srt_and_ass_text(self):
        srt = captions.to_srt([(1.5, 3.25, 'one'), (3700.0, 3701.0, 'two')])
        self.assertIn('1\n00:00:01,500 --> 00:00:03,250\none\n', srt)
        self.assertIn('01:01:40,000', srt)
        ass = captions.to_ass([(1.5, 3.25, 'Hi {\\i1}there\\N')], 640, 360)
        self.assertIn('PlayResX: 640', ass)
        self.assertIn('Dialogue: 0,0:00:01.50,0:00:03.25,Lyric,{\\fad(180,180)}Hi (/i1)there/N', ass)

    def test_looks_are_validated_defaulted_and_change_the_script(self):
        self.assertEqual(captions.look(None), {'style': 'classic', 'position': 'bottom', 'size': 'medium'})
        for bad in ({'style': 'comic'}, {'position': 'left'}, {'size': 'huge'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                captions.look(bad)
        self.assertEqual(captions.clean({'mode': 'burned', 'style': 'neon'}), {'mode': 'burned', 'style': 'neon', 'position': 'bottom', 'size': 'medium'})
        items = [(0, 2, 'honk')]
        classic, bold, top = (captions.to_ass(items, 1280, 720, look) for look in (None, {'style': 'bold'}, {'position': 'top', 'size': 'large'}))
        self.assertIn(',2,', classic.split('Style: Lyric,')[1].split('\n')[0])                    # bottom-centre alignment
        self.assertIn('HONK', bold)
        self.assertIn('honk', classic)
        self.assertIn('{\\fad(', classic)
        self.assertIn(',8,', top.split('Style: Lyric,')[1].split('\n')[0])
        self.assertNotEqual(classic.split('[Events]')[0], top.split('[Events]')[0])

    def test_plan_run_validates_lines_on_its_own_and_needs_some(self):
        self.assertIsNone(captions.plan_run({'mode': 'off'}, None, 0, 10, 10))
        empty = captions.plan_run({'mode': 'sidecar'}, [], 0, 10, 10)
        self.assertEqual((empty['cues'], empty['note']), ([], captions.NO_LINES))
        with self.assertRaises(ValueError):
            captions.plan_run({'mode': 'sidecar'}, [{'start': 3, 'end': 1, 'text': 'x'}], 0, 10, 10)
        plan = captions.plan_run({'mode': 'sidecar'}, LINES, 0.0, 10.0, 10.0)
        self.assertEqual((plan['mode'], len(plan['cues'])), ('sidecar', 3))

    def test_downloads_list_only_recorded_extras(self):
        self.assertEqual(captions.downloads({}), [])
        self.assertEqual(captions.downloads({'captions': {'srt': 'lyrics.srt', 'uncaptioned_copy': 'a.mp4'}, 'subliminal': {'clean_copy': 'c.mp4'}}),
                         ['lyrics.srt', 'a.mp4', 'c.mp4'])


@unittest.skipUnless(FFMPEG and shutil.which('ffprobe'), 'ffmpeg is needed')
class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        video(self.dir / 'music-video.mp4')
        self.plan = captions.plan_run({'mode': 'burned'}, LINES, 0.0, 6.0, 6.0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sidecar_writes_the_srt_and_leaves_the_video_alone(self):
        before = (self.dir / 'music-video.mp4').read_bytes()
        result = captions.apply_to_run(self.dir, {**self.plan, 'mode': 'sidecar'})
        self.assertEqual(result, {'mode': 'sidecar', 'cues': len(self.plan['cues']), 'srt': 'lyrics.srt'})
        self.assertEqual((self.dir / 'music-video.mp4').read_bytes(), before)
        self.assertIn('-->', (self.dir / 'lyrics.srt').read_text())

    def test_burned_keeps_frames_and_the_uncaptioned_copy_and_draws_something(self):
        before = frames(self.dir / 'music-video.mp4')
        original = (self.dir / 'music-video.mp4').read_bytes()
        result = captions.apply_to_run(self.dir, self.plan)
        self.assertEqual(result['uncaptioned_copy'], captions.UNCAPTIONED_NAME)
        self.assertEqual(frames(self.dir / 'music-video.mp4'), before)
        self.assertEqual((self.dir / captions.UNCAPTIONED_NAME).read_bytes(), original)
        self.assertNotEqual((self.dir / 'music-video.mp4').read_bytes(), original)
        self.assertFalse((self.dir / 'captions-work').exists())

    def test_a_failed_burn_leaves_the_video_untouched_and_reports_it(self):
        original = (self.dir / 'music-video.mp4').read_bytes()
        with mock.patch.object(captions, 'burn', side_effect=ValueError('boom')):
            result = captions.apply_to_run(self.dir, self.plan)
        self.assertEqual(result['burn_error'], 'boom')
        self.assertNotIn('uncaptioned_copy', result)
        self.assertEqual((self.dir / 'music-video.mp4').read_bytes(), original)
        self.assertTrue((self.dir / 'lyrics.srt').exists())
        self.assertFalse((self.dir / 'captions-work').exists())


@unittest.skipUnless(FFMPEG and shutil.which('ffprobe'), 'ffmpeg is needed')
class FinishedVideoTests(unittest.TestCase):
    """caption_finished on a temporary store, with a fake job context."""

    def setUp(self):
        import json
        import types
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.store = types.SimpleNamespace(home=self.home)
        self.run = self.home / 'runs' / 'abc'
        self.run.mkdir(parents=True)
        video(self.run / 'music-video.mp4')
        lines = [{'start': 0.5, 'end': 2.0, 'text': 'one', 'timing': 'matched'}, {'start': 2.5, 'end': 4.0, 'text': 'two', 'timing': 'uncertain'}]
        self.write = lambda name, value: (self.run / name).write_text(json.dumps(value))
        self.write('output.json', {'file': 'music-video.mp4', 'kind': 'video', 'title': 'T', 'duration': 6})
        self.write('request.json', {'lyric_lines': lines})
        self.write('plan.json', {'fps': 24, 'total_frames': 144, 'segments': [{'trim_frames': 144}]})

    def tearDown(self):
        self.tmp.cleanup()

    def context(self, cancelled=False):
        import types
        out = self.home / 'runs' / 'new'
        out.mkdir(exist_ok=True)

        def command(argv, cwd=None):
            subprocess.run([str(a) for a in argv], check=True, capture_output=True, cwd=cwd)

        def check():
            if cancelled:
                raise RuntimeError('cancelled')
        return types.SimpleNamespace(log_path=out / 'operation.log', record={'id': 'new'}, update=lambda *a, **k: None, command=command, check=check)

    def test_unconfirmed_lines_are_not_captioned_and_the_job_runner_is_used(self):
        captions.caption_finished(self.store, 'abc/music-video.mp4', [], self.context())
        self.assertEqual(frames(self.home / 'runs' / 'new' / 'captioned.mp4'), frames(self.run / 'music-video.mp4'))
        self.assertEqual((self.home / 'runs' / 'new' / 'lyrics.srt').read_text().count('-->'), 1)

    def test_a_cancelled_job_publishes_nothing(self):
        with self.assertRaises(RuntimeError):
            captions.caption_finished(self.store, 'abc/music-video.mp4', [], self.context(cancelled=True))
        self.assertFalse((self.home / 'runs' / 'new' / 'captioned.mp4').exists())
        self.assertFalse((self.home / 'runs' / 'new' / 'output.json').exists())

    def test_a_lost_backup_or_a_deleted_opening_ident_is_refused(self):
        self.write('output.json', {'file': 'music-video.mp4', 'kind': 'video', 'captions': {'uncaptioned_copy': 'music-video-uncaptioned.mp4'}})
        with self.assertRaisesRegex(ValueError, 'twice'):
            captions.caption_finished(self.store, 'abc/music-video.mp4', [], self.context())
        self.write('output.json', {'file': 'music-video.mp4', 'kind': 'video'})
        self.write('request.json', {'start_ident': 'abc/gone.mp4', 'lyric_lines': [{'start': 1, 'end': 2, 'text': 'x'}]})
        (self.home / 'runs' / 'ident').mkdir()
        self.write('request.json', {'start_ident': 'ident/ident.mp4', 'lyric_lines': [{'start': 1, 'end': 2, 'text': 'x'}]})
        with self.assertRaisesRegex(ValueError, 'ident that was deleted'):
            captions.caption_finished(self.store, 'abc/music-video.mp4', [], self.context())


if __name__ == '__main__':
    unittest.main()
