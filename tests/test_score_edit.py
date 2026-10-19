import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from mmv.engine.analyze import ScoreMap, Section
from mmv.engine.backends import get_backend
from mmv.engine.plan import plan
from mmv.score_edit import apply_score_edits, check_plan_coverage, detected_view, is_empty
from mmv.waveform import waveform_peaks

ROOT = Path(__file__).resolve().parents[1]


def sample_score():
    beats = list(range(12, 480, 12))               # 12 frames per beat, 39 beats, 20 s
    return ScoreMap('song', 480, 22050, 120.0, 4, beat_frames=beats,
                    downbeat_frames=beats[1::4], beat_energy=[i / len(beats) for i in range(len(beats))],
                    sections=[Section(0, 240, 0, 0.3, 'low'), Section(240, 480, 1, 0.7, 'high')])


class ScoreEditTests(unittest.TestCase):
    def test_empty_edits_change_nothing_and_never_mutate_the_source(self):
        score = sample_score()
        before = copy.deepcopy(score)
        self.assertTrue(is_empty({}) and is_empty(None) and is_empty({'bar_one_beat': None, 'beat_nudge_ms': 0,
                                                                       'muted_beats': [], 'sections': []}))
        self.assertEqual(apply_score_edits(score, {}), before)
        apply_score_edits(score, {'bar_one_beat': 2, 'muted_beats': [0, 1], 'beat_nudge_ms': 100,
                                  'sections': [{'start': 0, 'label': 'mid'}]})
        self.assertEqual(score, before)

    def test_bar_one_moves_the_bar_phase(self):
        score = sample_score()
        edited = apply_score_edits(score, {'bar_one_beat': 2})
        self.assertEqual(edited.downbeat_frames[0], score.beat_frames[2])
        self.assertEqual(edited.downbeat_frames, score.beat_frames[2::4])

    def test_nudge_shifts_grid_and_drops_beats_that_leave_the_song(self):
        score = sample_score()
        edited = apply_score_edits(score, {'beat_nudge_ms': -250})   # six frames earlier
        self.assertEqual(edited.beat_frames[0], score.beat_frames[0] - 6)
        late = apply_score_edits(score, {'beat_nudge_ms': 250})
        self.assertEqual(len(late.beat_frames), len(late.beat_energy))
        self.assertTrue(all(0 <= b < score.duration_frames for b in late.beat_frames))

    def test_muted_beats_leave_cut_candidates_but_keep_bar_counting(self):
        score = sample_score()
        edited = apply_score_edits(score, {'muted_beats': [1, 5]})
        self.assertNotIn(score.beat_frames[1], edited.beat_frames)
        self.assertEqual(len(edited.beat_frames), len(edited.beat_energy))
        self.assertEqual(edited.downbeat_frames, score.downbeat_frames)

    def test_muting_after_a_nudge_uses_original_beat_identity(self):
        score = sample_score()
        edited = apply_score_edits(score, {'beat_nudge_ms': 250, 'muted_beats': [0]})
        self.assertNotIn(score.beat_frames[0] + 6, edited.beat_frames)
        self.assertIn(score.beat_frames[1] + 6, edited.beat_frames)

    def test_sections_are_rebuilt_with_energy_from_beats(self):
        score = sample_score()
        edited = apply_score_edits(score, {'sections': [{'start': 0, 'label': 'low'}, {'start': 5, 'label': 'peak'},
                                                        {'start': 15, 'label': 'mid'}]})
        self.assertEqual([(s.start_frame, s.end_frame, s.label) for s in edited.sections],
                         [(0, 120, 'low'), (120, 360, 'peak'), (360, 480, 'mid')])
        self.assertEqual([s.index for s in edited.sections], [0, 1, 2])
        self.assertGreater(edited.sections[1].energy, edited.sections[0].energy)

    def test_invalid_edits_are_rejected(self):
        score = sample_score()
        bad = [{'beat_nudge_ms': 900}, {'bar_one_beat': 999}, {'muted_beats': [1, 1]}, {'muted_beats': [999]},
               {'muted_beats': list(range(39))},
               {'sections': [{'start': 1, 'label': 'low'}]},
               {'sections': [{'start': 0, 'label': 'loud'}]},
               {'sections': [{'start': 0, 'label': 'low'}, {'start': 0.5, 'label': 'mid'}]},
               {'sections': [{'start': 0, 'label': 'low'}, {'start': 30, 'label': 'mid'}]},
               {'sections': [{'start': 0, 'label': 'low'}, {'start': 10, 'label': 'mid'}, {'start': 5, 'label': 'high'}]}]
        for edits in bad:
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                apply_score_edits(score, edits)

    def test_detected_view_opens_the_first_section_at_zero_like_the_planner(self):
        score = sample_score()
        score.sections[0].start_frame = 2
        view = detected_view(score)
        self.assertEqual(view['sections'][0]['start'], 0)
        self.assertEqual(view['sections'][1]['start'], 10.0)
        self.assertEqual(len(view['beats']), len(score.beat_frames))

    def test_beat_zero_is_a_real_bar_choice(self):
        score = ScoreMap('song', 480, 22050, 120.0, 4, beat_frames=[12, 24, 36, 48, 60, 72],
                         downbeat_frames=[24, 72], beat_energy=[.5] * 6, sections=[Section(0, 480, 0, .5, 'mid')])
        self.assertFalse(is_empty({'bar_one_beat': 0}))
        self.assertEqual(apply_score_edits(score, {'bar_one_beat': 0}).downbeat_frames, [12, 60])

    def test_bar_phase_follows_original_beat_identity_after_a_nudge_drops_beats(self):
        score = ScoreMap('song', 96, 22050, 120.0, 4, beat_frames=[2, 14, 26, 38, 50, 62, 74, 86],
                         downbeat_frames=[14, 62], beat_energy=[.5] * 8, sections=[Section(0, 96, 0, .5, 'mid')])
        edited = apply_score_edits(score, {'beat_nudge_ms': -250, 'bar_one_beat': 1})   # six frames earlier
        self.assertEqual(edited.downbeat_frames, [8, 56])
        last = apply_score_edits(score, {'beat_nudge_ms': 250, 'bar_one_beat': 7})      # last beat still selectable
        self.assertEqual(last.downbeat_frames, [44, 92])

    def test_edits_that_would_drop_frames_from_the_plan_are_rejected_but_unedited_plans_pass(self):
        score = ScoreMap.from_json(ROOT / 'tests/fixtures/score.json')
        vocab = json.loads((ROOT / 'mmv/engine/config/vocab.json').read_text(encoding='utf-8'))

        def segments(candidate):
            made = plan(candidate, width=1024, height=576, vocab=vocab, seed=17, cast_size=3, ref_policy='all',
                        bars_per_phrase=1, backend=get_backend('local_h3'))
            return [{'song_start_frame': s.song_start_frame, 'trim_frames': s.trim_frames} for s in made.segments]

        check_plan_coverage(segments(score), score.duration_frames)
        sliver = {'sections': [{'start': 0, 'label': 'mid'}, {'start': (score.downbeat_frames[2] + 2) / 24, 'label': 'high'}]}
        with self.assertRaisesRegex(ValueError, 'shift the picture'):
            check_plan_coverage(segments(apply_score_edits(score, sliver)), score.duration_frames)
        on_bar = {'sections': [{'start': 0, 'label': 'mid'}, {'start': score.downbeat_frames[2] / 24, 'label': 'high'}]}
        check_plan_coverage(segments(apply_score_edits(score, on_bar)), score.duration_frames)

    def test_waveform_peaks_are_bounded_and_normalised(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'tone.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=3', str(path)],
                           check=True)
            result = waveform_peaks(path, peaks=100)
            self.assertAlmostEqual(result['duration'], 3.0, delta=0.1)
            self.assertEqual(len(result['peaks']), 100)
            self.assertEqual(max(result['peaks']), 1.0)
            with self.assertRaises(ValueError):
                waveform_peaks(Path(temp) / 'missing.wav')


if __name__ == '__main__':
    unittest.main()
