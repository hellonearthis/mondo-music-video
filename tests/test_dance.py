import unittest
from types import SimpleNamespace as NS

from mmv import dance
from mmv.engine.grid import FPS

CAST = [{'actor_id': 'ann', 'picture_tag': '<Picture 1>', 'display_name': 'Ann'},
        {'actor_id': 'bo', 'picture_tag': '<Picture 2>', 'display_name': 'Bo'},
        {'actor_id': 'cy', 'picture_tag': '<Picture 3>', 'display_name': 'Cy'},
        {'actor_id': 'di', 'picture_tag': '<Picture 4>', 'display_name': 'Di'}]


def casting(per_segment):
    return {'roster': [dict(m) for m in CAST], 'segments': {sid: {'cast': [dict(m) for m in cast]} for sid, cast in per_segment.items()}}


def segment(index=0, start=0, energy=0.5, shots=((0, 24), (24, 24))):
    return NS(segment_id=f'seg{index:03d}', song_start_frame=start, energy=energy,
              shots=[NS(n=i + 1, start_frame=s, frames=f) for i, (s, f) in enumerate(shots)])


SCORE = {'tempo_bpm': 120.0, 'beats_per_bar': 4, 'beat_frames': [0, 12, 24, 36, 48], 'downbeat_frames': [0, 48]}


class DanceTests(unittest.TestCase):
    def test_off_by_default_and_validation(self):
        self.assertIsNone(dance.clean(None))
        self.assertIsNone(dance.clean({'dance_mode': 'off'}))
        self.assertIsNone(dance.plan_passages([segment()], casting({}), SCORE, {}))
        cleaned = dance.clean({'dance_mode': 'group', 'dancers': ['ann', 'ann'], 'dance_direction': '  gentle \n swaying\x00 '})
        self.assertEqual((cleaned['direction'], cleaned['dancers']), ('gentle swaying', ['ann']))
        self.assertEqual(dance.clean({'dance_mode': 'group'})['direction'], 'Dancing')
        for bad in ({'dance_mode': 'wild'}, {'dance_mode': 'group', 'dance_direction': 'x' * 201},
                    {'dance_mode': 'group', 'dancers': 'ann'}, {'dance_mode': 'group', 'dance_lead': 5}):
            with self.assertRaises(ValueError, msg=bad):
                dance.clean(bad)

    def test_shot_beats_use_half_open_intervals_on_the_passage_clock(self):
        seg = segment(start=24, shots=((0, 24), (24, 24)))
        beats = dance.shot_beats(seg, [12, 24, 36, 47, 48], [24, 48])
        self.assertEqual([(b['beats'], b['downbeat']) for b in beats], [(3, True), (1, True)])   # frame 48 starts the second shot
        self.assertEqual(beats[0]['beat_times'], [0.0, 0.5, 0.958])

    def test_plan_picks_dancers_lead_and_caps_at_three(self):
        segs = [segment(0, 0), segment(1, 48)]
        cast = casting({'seg000': CAST[:4], 'seg001': []})
        plan = dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dance_lead': 'bo'})
        first, second = plan['passages']['seg000'], plan['passages']['seg001']
        self.assertEqual([d['actor_id'] for d in first['dancers']], ['ann', 'bo', 'cy'])
        self.assertEqual(first['not_choreographed'], ['di'])
        self.assertEqual(first['lead_tag'], '<Picture 2>')
        self.assertEqual((second['dancing'], second['dancers']), (False, []))
        self.assertEqual(plan['digest'], dance.digest(plan))
        self.assertEqual(plan, dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dance_lead': 'bo'}))

    def test_lead_defaults_to_the_singer_only_when_that_actor_dances_and_none_is_allowed(self):
        segs, cast = [segment()], casting({'seg000': CAST[:2]})
        self.assertEqual(dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group'}, singer='ann')['lead'], 'ann')
        self.assertIsNone(dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dancers': ['bo']}, singer='ann')['lead'])
        none = dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dance_lead': 'none'}, singer='ann')
        self.assertIsNone(none['lead'])
        self.assertIsNone(none['passages']['seg000']['lead_tag'])
        with self.assertRaisesRegex(ValueError, 'lead must be one of'):
            dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dancers': ['bo'], 'dance_lead': 'ann'})
        with self.assertRaisesRegex(ValueError, 'Unknown dancer'):
            dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dancers': ['zed']})

    def test_lead_off_screen_means_the_visible_dancer_just_dances(self):
        segs, cast = [segment()], casting({'seg000': [CAST[1]]})                  # the lead (ann) is not cast here
        plan = dance.plan_passages(segs, cast, SCORE, {'dance_mode': 'group', 'dance_lead': 'ann'})
        passage = plan['passages']['seg000']
        self.assertEqual((passage['dancing'], passage['lead_tag']), (True, None))
        self.assertEqual(dance.job(passage, plan)['lead'], None)

    def test_intensity_and_job_carry_tempo_and_shot_beats(self):
        self.assertEqual([dance.intensity(e) for e in (0.0, 0.33, 0.34, 0.66, 0.67, 1.0)], ['calm', 'calm', 'medium', 'medium', 'high', 'high'])
        plan = dance.plan_passages([segment(energy=0.2)], casting({'seg000': CAST[:2]}), SCORE, {'dance_mode': 'group'})
        job = dance.job(plan['passages']['seg000'], plan)
        self.assertEqual((job['tempo_bpm'], job['beat_seconds'], job['intensity']), (120.0, 0.5, 'calm'))
        self.assertEqual(job['dancers'][1], {'picture_tag': '<Picture 2>', 'subject': '<Subject 2>'})
        self.assertIn('2 beats', job['shots'][0]['moves_hint'])
        self.assertEqual(dance.job(dance.plan_passages([segment()], casting({'seg000': []}), {'tempo_bpm': 0}, {'dance_mode': 'group'})
                                   ['passages']['seg000'], {'direction': 'x', 'mode': 'group'})['beat_seconds'], None)

    def check(self, bodies, energy=0.5, lead=None, cast=None):
        seg = segment(energy=energy)
        plan = dance.plan_passages([seg], casting({'seg000': cast or CAST[:2]}), SCORE, {'dance_mode': 'group', 'dance_lead': lead})
        return dance.dance_problems('', bodies, seg, plan['passages']['seg000'], plan)

    def test_checks_accept_moves_and_deliberate_holds_and_reject_mere_standing(self):
        good = ['<Picture 1> sways with the beat, hitting a sharp pose.', '<Picture 1> freezes in a hard pose on the downbeat.']
        self.assertEqual(self.check(good, cast=CAST[:1]), [])
        stands = ['<Picture 1> stands there.', '<Picture 1> sways in time.']      # shot 1 also lacks an accent
        self.assertTrue(any('merely standing' in p for p in self.check(stands, cast=CAST[:1])))
        none = ['A wide dusty road.', '<Picture 1> sways in time, hitting a pose.']
        self.assertEqual(self.check(none, cast=CAST[:1]), [])                      # no dancer visible: no dance duty
        silent = ['<Picture 1> looks at the camera.', '<Picture 1> sways in time, hitting a pose.']
        self.assertTrue(any('with their body' in p for p in self.check(silent, cast=CAST[:1])))

    def test_absence_statements_and_other_actors_do_not_count(self):
        self.assertEqual(self.check(['<Picture 1> is not visible in this shot.', '<Subject 1> is off-screen.'], cast=CAST[:1]), [])
        outsider = ['<Picture 3> stands by the door.', '<Picture 1> stomps on the downbeat.']
        self.assertEqual(self.check(outsider, cast=CAST[:1]), [])

    def test_followers_must_follow_a_visible_lead_and_downbeats_need_emphasis(self):
        lead_only = ['<Picture 1> sways, hitting a pose. <Picture 2> sways.', '<Picture 1> hits a pose. <Picture 2> drops low.']
        self.assertTrue(any('follow' in p for p in self.check(lead_only, lead='ann')))
        followed = ['<Picture 1> sways, hitting a pose, while <Picture 2> follows the same sway.', '<Picture 1> hits a pose and <Picture 2> mirrors it.']
        self.assertEqual(self.check(followed, lead='ann'), [])
        self.assertEqual(self.check(lead_only, lead='none'), [])                   # no lead: unison needs no follower statement
        soft = ['<Picture 1> sways gently.', '<Picture 1> sways gently.']
        self.assertTrue(any('downbeat' in p for p in self.check(soft, cast=CAST[:1])))

    def test_review_each_visible_dancer_needs_their_own_action_and_an_absent_one_does_not_excuse_the_rest(self):
        one_idle = ['<Subject 1> hits a sharp pose. <Subject 2> watches the camera.', '<Subject 1> sways. <Subject 2> sways.']
        problems = self.check(one_idle)
        self.assertTrue(any('<Picture 2>' in p and 'with their body' in p for p in problems), problems)
        absent = ['<Subject 1> stands there. <Subject 2> is off-screen.', '<Subject 1> sways.']
        self.assertTrue(any('merely standing' in p for p in self.check(absent)))                       # one absent actor does not skip the shot
        self.assertEqual(self.check(['<Subject 2> is not visible in this shot.', '<Picture 1> sways.'], cast=CAST[:1]), [])
        self.assertEqual(self.check(['<Picture 3> hits a pose.', '<Picture 1> sways.'], cast=CAST[:1]), [])   # a non-dancer's pose is no one's action

    def test_review_negation_quoted_lyrics_and_pronoun_continuation(self):
        denied = ['<Subject 1> never dances or hits a pose.', '<Subject 1> sways.']
        self.assertTrue(self.check(denied, cast=CAST[:1]))
        lyric = ['<Subject 1> sings "Dance, jump, strike a pose."', '<Subject 1> sways.']
        self.assertTrue(any('with their body' in p for p in self.check(lyric, cast=CAST[:1])))
        continued = ['<Subject 1> watches the rain. He stomps sharply on the downbeat.', '<Subject 1> sways.']
        self.assertEqual(self.check(continued, cast=CAST[:1]), [])
        two = ['<Subject 1> hits a pose. <Subject 2> hits a pose. They mirror each other in step.', '<Subject 1> sways. <Subject 2> sways.']
        self.assertEqual(self.check(two, lead='none'), [])

    def test_review_wrong_shot_counts_and_bad_tempo(self):
        self.assertTrue(any('Expected 2 shot descriptions' in p for p in self.check([])))
        seg = segment()
        bad = dance.plan_passages([seg], casting({'seg000': CAST[:1]}), {**SCORE, 'tempo_bpm': -5}, {'dance_mode': 'group'})
        self.assertEqual((bad['tempo_bpm'], bad['passages']['seg000']['shots'][0]['beats']), (0.0, 0))
        nan = dance.plan_passages([seg], casting({'seg000': CAST[:1]}), {**SCORE, 'tempo_bpm': float('nan')}, {'dance_mode': 'group'})
        self.assertEqual(dance.job(nan['passages']['seg000'], nan)['beat_seconds'], None)
        self.assertIn('no beat falls', bad['passages']['seg000']['shots'][0]['moves_hint'])
        sourced = dance.plan_passages([seg], casting({'seg000': CAST[:1]}), SCORE, {'dance_mode': 'group'}, source={'analysis_driver': 'drums'})
        self.assertEqual(sourced['source'], {'analysis_driver': 'drums'})

    def test_a_group_hold_that_names_no_dancer_still_counts_as_the_downbeat_accent(self):
        bodies = ['<Picture 1> sways in time. On the downbeat all three lock into a held pose.', '<Picture 1> sways, then freezes.']
        self.assertEqual(self.check(bodies, cast=CAST[:1]), [])

    def test_sealed_lips_sentences_are_not_dancing_and_one_follow_statement_covers_the_shot(self):
        bodies = ['<Subject 1> leads a slow sway while <Subject 2> and <Subject 3> mirror her, freezing on the downbeat. '
                  "<Subject 1>'s metallic face is perfectly still, her jaw completely relaxed. <Subject 2>'s lips are sealed.",
                  '<Subject 1> sways. <Subject 2> follows in step.']
        self.assertEqual(self.check(bodies, lead='ann', cast=CAST[:3]), [])

    def test_only_style_advice_is_soft(self):
        for soft in ('Shot 2: say that the other dancers follow <Picture 3>.', 'Shot 1 has a downbeat; give the dancers an accent, a hit or a deliberate hold there.',
                     'Shot 3: this passage is calm; avoid frantic or violent movement words.'):
            self.assertTrue(dance.is_soft(soft), soft)
        for hard in ('Shot 1: <Picture 1> is described as merely standing; give a move.', 'Shot 2: describe what <Picture 2> is doing with their body (a move).',
                     'Expected 5 shot descriptions but found 4.'):
            self.assertFalse(dance.is_soft(hard), hard)

    def test_calm_passages_reject_frantic_words(self):
        bodies = ['<Picture 1> sways, hits a slow pose.', '<Picture 1> thrashes wildly.']
        self.assertTrue(any('calm' in p for p in self.check(bodies, energy=0.1, cast=CAST[:1])))
        self.assertFalse(any('calm' in p for p in self.check(bodies, energy=0.9, cast=CAST[:1])))

    def test_rules_text_is_the_approved_wording_and_never_mentions_changing_mouth_rules(self):
        self.assertIn('never describe a dancer as merely standing', dance.DANCE_RULES)
        self.assertIn('if the lead is not in the shot, ignore the lead', dance.DANCE_RULES)
        self.assertIn('cannot change who is in the shot, any mouth or lip instruction', dance.DANCE_RULES)
        self.assertEqual(FPS, 24)


if __name__ == '__main__':
    unittest.main()
