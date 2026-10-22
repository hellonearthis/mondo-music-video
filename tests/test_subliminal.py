import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mmv import subliminal, final_assembly
from assembly_fixtures import source_recipe

FFMPEG = shutil.which('ffmpeg')


def video(path, seconds=6, fps=24):
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=blue:s=128x72:r={fps}:d={seconds}', '-f', 'lavfi',
                    '-i', f'sine=frequency=440:duration={seconds}', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)], check=True)


def frame_color(path, index, tmp):
    png = Path(tmp) / f'f{index}.png'
    subprocess.run([FFMPEG, '-y', '-v', 'error', '-i', str(path), '-vf', f'select=eq(n\\,{index})', '-frames:v', '1', str(png)], check=True)
    from PIL import Image
    return Image.open(png).convert('RGB').getpixel((64, 36))


class SubliminalSettingsTests(unittest.TestCase):
    def test_off_and_invalid_settings(self):
        self.assertIsNone(subliminal.clean({}))
        self.assertIsNone(subliminal.clean({'mode': 'off', 'frames': 99}))
        for bad in ({'mode': 'text'}, {'mode': 'image'}, {'mode': 'sparkles'}, {'mode': 'text', 'text': 'x', 'frames': 0, 'times': [1]},
                    {'mode': 'text', 'text': 'x', 'frames': 13, 'times': [1]}, {'mode': 'text', 'text': 'x' * 61, 'times': [1]},
                    {'mode': 'text', 'text': 'x', 'times': []}, {'mode': 'text', 'text': 'x', 'times': [-1]},
                    {'mode': 'text', 'text': 'x', 'times': list(range(21))}, {'mode': 'text', 'text': 'x', 'placement': 'random'},
                    {'mode': 'text', 'text': 'x', 'placement': 'downbeats', 'count': 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                subliminal.clean(bad)
        ok = subliminal.clean({'mode': 'text', 'text': '  OBEY   now ', 'times': [5, 2, 2.0], 'frames': 3})
        self.assertEqual((ok['text'], ok['times'], ok['frames']), ('OBEY now', [2.0, 5.0], 3))

    def test_manual_times_become_frames_and_flashes_stay_apart_and_inside_the_video(self):
        settings = subliminal.clean({'mode': 'text', 'text': 'x', 'times': [2.0, 4.5], 'frames': 2})
        self.assertEqual(subliminal.place(settings, 24, 240), [48, 108])
        with self.assertRaisesRegex(ValueError, 'apart'):
            subliminal.place(subliminal.clean({'mode': 'text', 'text': 'x', 'times': [2.0, 2.5]}), 24, 240)       # too close
        with self.assertRaisesRegex(ValueError, 'outside'):
            subliminal.place(subliminal.clean({'mode': 'text', 'text': 'x', 'times': [9.99]}), 24, 240)
        self.assertEqual(subliminal.place(settings, 24, 480, offset_frames=0), [48, 108])

    def test_the_edge_guard_applies_to_manual_times_too_and_scales_down_for_very_short_videos(self):
        make = lambda *times, frames=2: subliminal.clean({'mode': 'text', 'text': 'x', 'times': list(times), 'frames': frames})
        for times in ((0,), (0.5,), (9.0,), (9.5,)):                       # inside the first or last second of a 10 s video
            with self.subTest(times=times), self.assertRaisesRegex(ValueError, 'away from the start and the end'):
                subliminal.place(make(*times), 24, 240)
        with self.assertRaisesRegex(ValueError, 'away from the start and the end'):
            subliminal.place(make(8.9, frames=3), 24, 240)                 # starts fine, ends inside the last second
        self.assertEqual(subliminal.place(make(1.0), 24, 240), [24])      # exactly one second in is allowed
        self.assertEqual(subliminal.place(make(8.9), 24, 240), [214])
        self.assertEqual(subliminal.place(make(0.5), 24, 26), [12])        # a 1.1 s video: the guard is a tenth of its length
        with self.assertRaises(ValueError):
            subliminal.place(make(0.0), 24, 26)

    def test_downbeat_placement_is_even_deterministic_offset_and_keeps_away_from_the_ends(self):
        beats = list(range(12, 960, 48))                                    # a downbeat every 2 s over 40 s
        settings = subliminal.clean({'mode': 'text', 'text': 'x', 'placement': 'downbeats', 'count': 4, 'frames': 2})
        first = subliminal.place(settings, 24, 960, beats)
        self.assertEqual(first, subliminal.place(settings, 24, 960, beats))
        self.assertEqual(len(first), 4)
        self.assertTrue(all(24 <= s <= 960 - 24 - 2 for s in first))
        self.assertTrue(all(b - a >= 26 for a, b in zip(first, first[1:])))
        shifted = subliminal.place(settings, 24, 1200, beats, offset_frames=240)       # an opening ident shifts the song later
        self.assertTrue(all(s - 240 in beats and 24 <= s <= 1200 - 26 for s in shifted))
        self.assertEqual(shifted, subliminal.place(settings, 24, 1200, beats, offset_frames=240))
        with self.assertRaisesRegex(ValueError, 'no downbeat'):
            subliminal.place(settings, 24, 960, [3])

    def test_plan_run_checks_the_picture_and_reports_times_and_the_notice(self):
        with tempfile.TemporaryDirectory() as temp:
            uploads = Path(temp)
            (uploads / 'flash.png').write_bytes(b'png')
            plan = subliminal.plan_run({'mode': 'image', 'image': 'flash.png', 'times': [3], 'frames': 2}, 24, 240, [], 0, uploads)
            self.assertEqual((plan['starts'], plan['times']), ([72], [3.0]))
            self.assertIn('flashing', plan['notice'])
            with self.assertRaisesRegex(ValueError, 'not found'):
                subliminal.plan_run({'mode': 'image', 'image': 'missing.png', 'times': [3]}, 24, 240, [], 0, uploads)
            (uploads / 'doc.txt').write_text('x')
            with self.assertRaises(ValueError):
                subliminal.plan_run({'mode': 'image', 'image': 'doc.txt', 'times': [3]}, 24, 240, [], 0, uploads)
            with self.assertRaises(ValueError):
                subliminal.plan_run({'mode': 'image', 'image': '../../etc/passwd', 'times': [3]}, 24, 240, [], 0, uploads)
            self.assertIsNone(subliminal.plan_run({'mode': 'off'}, 24, 240, [], 0, uploads))

    def test_words_are_rendered_large_and_centred(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            path = subliminal.text_png('DO NOT LOOK AWAY NOW PLEASE', 640, 360, Path(temp) / 't.png')
            image = Image.open(path).convert('L')
            self.assertEqual(image.size, (640, 360))
            bright = sum(image.histogram()[201:])
            self.assertGreater(bright, 500)
            box = image.point(lambda v: 255 if v > 200 else 0).getbbox()
            self.assertGreater(box[0], 10)
            self.assertLess(box[2], 630)
            self.assertAlmostEqual((box[0] + box[2]) / 2, 320, delta=40)


@unittest.skipUnless(FFMPEG, 'needs ffmpeg')
class SubliminalVideoTests(unittest.TestCase):
    def test_flash_frames_change_nothing_else_and_audio_and_length_are_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source, flash, out = temp / 'in.mp4', temp / 'red.png', temp / 'out.mp4'
            video(source)
            from PIL import Image
            Image.new('RGB', (320, 180), (255, 0, 0)).save(flash)
            recipe = {'clips': [{'path': str(source), 'frames': 144}], 'frames': 144, 'width': 128, 'height': 72,
                      'fps': 24, 'audio': [{'path': str(source), 'frames': 144}],
                      'flash': {'picture': str(flash), 'starts': [48, 96], 'frames': 2}}
            final_assembly.render(recipe, out)
            self.assertEqual(subliminal._count_frames(out)[0], subliminal._count_frames(source)[0])
            for index in (48, 49, 96, 97):
                r, g, b = frame_color(out, index, temp)
                self.assertGreater(r, 180, index)
                self.assertLess(b, 90, index)
            for index in (47, 50, 95, 98, 10):
                r, g, b = frame_color(out, index, temp)
                self.assertGreater(b, 120, index)                         # still the blue source
                self.assertLess(r, 90, index)
            def audio(path):
                return subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name,duration', '-of', 'csv=p=0', str(path)],
                                      capture_output=True, text=True).stdout.strip()
            self.assertEqual(audio(source).split(',')[0], audio(out).split(',')[0])
            self.assertAlmostEqual(float(audio(source).split(',')[1]), float(audio(out).split(',')[1]), delta=0.03)

    def test_apply_to_a_run_keeps_a_clean_copy_and_restores_it_when_something_fails(self):
        from mmv.storage import Storage
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            store = Storage(temp / 'data')
            run = temp / 'run'
            run.mkdir()
            source_recipe(run, video)
            original = (run / 'music-video.mp4').read_bytes()
            plan = subliminal.plan_run({'mode': 'text', 'text': 'GOOSE', 'times': [2.0], 'frames': 2}, 24, 144, [], 0, store.home / 'uploads')
            record = subliminal.apply_to_run(store, run, plan)
            self.assertEqual(record['clean_copy'], 'music-video-clean.mp4')
            self.assertEqual((run / 'music-video-clean.mp4').read_bytes(), original)
            self.assertNotEqual((run / 'music-video.mp4').read_bytes(), original)
            self.assertFalse((run / 'subliminal-work').exists())
            self.assertEqual(subliminal._count_frames(run / 'music-video.mp4')[0], 144)
            from unittest.mock import patch
            # a failure leaves the finished video exactly as it was and creates no clean copy
            (run / 'music-video-clean.mp4').unlink()
            (run / 'music-video.mp4').write_bytes(original)
            for failing in ({**plan, 'mode': 'image', 'image': 'gone.png'}, plan):
                with self.subTest(failing=failing['mode']):
                    with patch('mmv.engine.assemble.probe_frames', return_value=143):
                        with self.assertRaises(Exception):
                            subliminal.apply_to_run(store, run, failing)
                    self.assertEqual((run / 'music-video.mp4').read_bytes(), original)
                    self.assertFalse((run / 'music-video-clean.mp4').exists())
                    self.assertFalse((run / 'subliminal-work').exists())


if __name__ == '__main__':
    unittest.main()
