import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from mmv import stems
from mmv.engine.analyze import ScoreMap, Section
from mmv.storage import Storage, write_json


def stem_wave(path, seconds=10, rate=22050):
    t = np.arange(int(seconds * rate)) / rate
    amplitude = np.where(t < seconds / 2, 0.05, 0.9)          # quiet first half, loud second half
    data = (np.sin(2 * np.pi * 220 * t) * amplitude * 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data.tobytes())


class FakeContext:
    def __init__(self):
        self.commands, self.updates = [], []

    def update(self, *args, **kwargs):
        self.updates.append(args)

    def command(self, argv, **kwargs):
        self.commands.append(argv)


class StemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Storage(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_nothing_is_ready_by_default_and_requires_the_addon_and_the_model(self):
        with patch.object(stems, 'installed', return_value=False):
            report = stems.status(self.store)
            self.assertFalse(report['installed'])
            self.assertFalse(any(model['ready'] for model in report['models'].values()))
            with self.assertRaisesRegex(ValueError, 'Demucs add-on'):
                stems.require_ready(self.store, 'drums')
        with patch.object(stems, 'installed', return_value=True):
            with self.assertRaisesRegex(ValueError, 'stem model first'):
                stems.require_ready(self.store, 'drums')
            self.assertEqual(stems.model_for('guitar'), 'htdemucs_6s')
            self.assertEqual(stems.model_for('vocals'), 'htdemucs')
            self.assertEqual(stems.model_for('vocals', 'high'), 'htdemucs_ft')
            self.assertEqual(stems.model_for('guitar', 'high'), 'htdemucs_6s')     # 6-stem has no high variant
            with self.assertRaises(ValueError):
                stems.model_for('drums', 'ultra')
            with self.assertRaisesRegex(ValueError, 'htdemucs_ft'):
                stems.require_ready(self.store, 'drums', 'high')
            with self.assertRaises(ValueError):
                stems.model_for('mix')

    def test_recommendation_follows_the_hardware_and_never_downloads(self):
        gpu = {'gpu': 'Test GPU', 'vram_free_gb': 8.0, 'vram_total_gb': 12.0, 'ram_gb': 32.0}
        advice = stems.recommend(gpu)
        self.assertEqual((advice['device'], advice['quality']), ('cuda', 'standard'))
        self.assertIn('Test GPU', advice['notes'][0])
        small = stems.recommend({'gpu': 'Tiny', 'vram_free_gb': 1.0, 'vram_total_gb': 4.0, 'ram_gb': 4.0})
        self.assertEqual(small['device'], 'cpu')
        self.assertTrue(any('RAM is 4.0 GB' in note for note in small['notes']))
        self.assertTrue(any('only if stray sounds' in note for note in small['notes']))
        with patch.object(stems, '_gpu', return_value={'gpu': None, 'free': 0, 'total': 0}), \
                patch.dict(stems._HARDWARE, {'at': 0.0, 'value': None}), patch.object(stems, 'installed', return_value=False):
            report = stems.status(self.store)
        self.assertEqual(report['recommendation']['device'], 'cpu')
        self.assertEqual(report['models']['htdemucs_ft']['download'], '324 MB')
        self.assertFalse(any(model['ready'] for model in report['models'].values()))

    def test_prepare_model_downloads_through_the_job_and_records_a_marker(self):
        context = FakeContext()
        with patch.object(stems, 'installed', return_value=True):
            stems.prepare_model(self.store, 'htdemucs', context)
            self.assertIn('get_model', context.commands[0][2])
            self.assertTrue(stems.status(self.store)['models']['htdemucs']['ready'])
            with self.assertRaises(ValueError):
                stems.prepare_model(self.store, 'unknown', context)
        with patch.object(stems, 'installed', return_value=False), self.assertRaisesRegex(ValueError, 'Install'):
            stems.prepare_model(self.store, 'htdemucs', FakeContext())

    def test_separate_caches_per_song_and_model(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            out = Path(argv[argv.index('-o') + 1]) / argv[argv.index('-n') + 1]
            out.mkdir(parents=True)
            for stem in stems.MODELS[argv[argv.index('-n') + 1]]:
                stem_wave(out / f'{stem}.wav', 1)
            return subprocess.CompletedProcess(argv, 0, '', '')

        song = Path(self.temp.name) / 'song.wav'
        stem_wave(song, 1)
        with patch.object(stems.subprocess, 'run', side_effect=fake_run), \
                patch.object(stems, '_gpu', return_value={'gpu': None, 'free': 0, 'total': 0}):
            first = stems.separate(self.store, song, 'abc', 'htdemucs')
            second = stems.separate(self.store, song, 'abc', 'htdemucs')
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            self.assertIn('cpu', calls[0])
            stems.separate(self.store, song, 'abc', 'htdemucs_6s')
            self.assertEqual(len(calls), 2)
        self.assertTrue((first / 'drums.wav').is_file())

    def test_a_failed_separation_leaves_no_partial_cache(self):
        song = Path(self.temp.name) / 'song.wav'
        stem_wave(song, 1)
        failed = subprocess.CompletedProcess([], 1, '', 'boom')
        with patch.object(stems.subprocess, 'run', side_effect=[failed]), \
                patch.object(stems, '_gpu', return_value={'gpu': None, 'free': 0, 'total': 0}):
            with self.assertRaisesRegex(ValueError, 'Stem separation failed'):
                stems.separate(self.store, song, 'abc', 'htdemucs')
        self.assertFalse((self.store.home / 'analysis' / 'stems' / 'abc-htdemucs').exists())

    def test_driven_score_takes_energy_and_labels_from_the_stem_and_keeps_the_grid(self):
        beats = list(range(12, 240, 12))                            # 10 s at 24 fps
        score = ScoreMap('song', 240, 22050, 120.0, 4, beat_frames=beats, downbeat_frames=beats[::4],
                         beat_energy=[0.9 - i * 0.01 for i in range(len(beats))],
                         sections=[Section(0, 120, 0, 0.9, 'peak'), Section(120, 240, 1, 0.1, 'low')])
        path = Path(self.temp.name) / 'stem.wav'
        stem_wave(path)
        driven = stems.driven_score(score, path)
        self.assertEqual(driven.beat_frames, score.beat_frames)
        self.assertEqual(driven.downbeat_frames, score.downbeat_frames)
        self.assertEqual(len(driven.beat_energy), len(beats))
        self.assertLess(driven.sections[0].energy, driven.sections[1].energy)
        self.assertEqual([s.label for s in driven.sections], ['low', 'peak'])
        self.assertEqual(score.sections[0].label, 'peak')           # the source is untouched


if __name__ == '__main__':
    unittest.main()
