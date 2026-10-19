import unittest
from types import SimpleNamespace as NS

from mmv import lipsync
from mmv.engine.schema import RIGGING_TAIL


def segment(sid, start_s, end_s, shots=((1, 0, 48), (2, 48, 48))):
    return NS(segment_id=sid, audio_slice_start_s=start_s, audio_slice_end_s=end_s,
              shots=[NS(n=n, start_frame=s, frames=f) for n, s, f in shots])


def casting(*members_by_segment, roster=('pig', 'goon')):
    return {'roster': [{'actor_id': a} for a in roster],
            'segments': {sid: {'cast': [{'actor_id': a, 'picture_tag': f'<Picture {i + 1}>'} for i, a in enumerate(actors)]}
                         for sid, actors in members_by_segment}}


LINES = [{'start': 2.0, 'end': 4.0, 'text': 'Interdimensional lover'}, {'start': 4.5, 'end': 6.0, 'text': 'I dated you'}]


class LipSyncTests(unittest.TestCase):
    def test_lines_are_validated_and_sorted(self):
        self.assertEqual(lipsync.clean_lines([]), [])
        cleaned = lipsync.clean_lines([{'start': 3, 'end': 4, 'text': ' b  c '}, {'start': 1, 'end': 2, 'text': 'a'}])
        self.assertEqual([line['text'] for line in cleaned], ['a', 'b c'])
        for bad in ([{'start': 2, 'end': 1, 'text': 'x'}], [{'start': 0, 'end': 1, 'text': ''}], [{'start': 'a', 'end': 1, 'text': 'x'}],
                    [{'start': float('nan'), 'end': 1, 'text': 'x'}], [{'start': 0, 'end': 1, 'text': 'x' * 400}], 'text',
                    [{'start': 0, 'end': 1}], [{'start': -1, 'end': 1, 'text': 'x'}]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lipsync.clean_lines(bad)

    def test_passages_sing_only_when_the_audible_slice_has_enough_sung_seconds(self):
        segs = [segment('s0', 0, 2.0), segment('s1', 1.5, 4.5), segment('s2', 6.0, 9.0), segment('s3', 5.5, 6.4)]
        cast = casting(('s0', ['pig']), ('s1', ['goon', 'pig']), ('s2', ['pig']), ('s3', ['pig']))
        result = lipsync.plan_passages(segs, cast, LINES, ['pig'], seed=1)['passages']
        self.assertFalse(result['s0']['singing'])                     # no lines in 0-2 s
        self.assertTrue(result['s1']['singing'])                      # 2.0-4.0 s sung = 2 s
        self.assertEqual(result['s1']['picture_tag'], '<Picture 2>')   # singer is the second cast member, not assumed first
        self.assertEqual(result['s1']['lines'][0]['start'], 0.5)       # relative to the slice start (1.5 s)
        self.assertFalse(result['s2']['singing'])                     # slice starts as the lines end
        self.assertFalse(result['s3']['singing'])                     # only 0.5 s of singing: below the threshold

    def test_only_the_main_singer_sings_so_other_cast_leave_the_passage_sealed(self):
        segs = [segment('s1', 2, 5), segment('s2', 2, 5), segment('s3', 2, 5)]
        cast = casting(('s1', ['goon']), ('s2', []), ('s3', ['goon', 'pig']))
        result = lipsync.plan_passages(segs, cast, LINES, ['pig'], seed=1)['passages']
        self.assertFalse(result['s1']['singing'])                       # the singer is not on screen: no one else sings for them
        self.assertIn('main singer is not on screen', result['s1']['reason'])
        self.assertFalse(result['s2']['singing'])
        self.assertIn('no actor is cast', result['s2']['reason'])
        self.assertTrue(result['s3']['singing'])                        # the singer is one of two actors on screen
        self.assertEqual((result['s3']['actor_id'], result['s3']['picture_tag']), ('pig', '<Picture 2>'))

    def test_singer_choice_is_seeded_and_respects_the_roster(self):
        self.assertEqual(lipsync.resolve_singer(['a', 'b'], ['b'], 1), 'b')
        self.assertEqual(lipsync.resolve_singer(['a', 'b'], ['zzz'], 5), lipsync.resolve_singer(['b', 'a'], [], 5))
        self.assertEqual({lipsync.resolve_singer(['a', 'b', 'c'], [], seed) for seed in range(40)}, {'a', 'b', 'c'})
        self.assertIsNone(lipsync.resolve_singer([], [], 1))

    def test_only_the_singer_carries_lines_and_the_audio_sentence_is_swapped_outside_the_engine(self):
        cast = [{'actor_id': 'pig', 'lines': [], 'direction': ''}, {'actor_id': 'goon', 'lines': [], 'direction': ''}]
        out = lipsync.with_singer_lines(cast, 'goon', [{'start': 0, 'end': 1, 'text': 'hello there'}])
        self.assertEqual(out[0]['lines'], [])
        self.assertEqual(out[1]['lines'], ['hello there'])
        self.assertEqual(cast[1]['lines'], [])                         # input untouched
        prompt = ("<Audio 1> is the rhythmic and tempo reference for the target video, providing the beat and "
                  "pacing the visuals follow.")
        self.assertIn('follow the sung vocal', lipsync.swap_audio_sentence(prompt, '<Audio 1>'))

    def test_every_shot_gets_the_words_sung_inside_it(self):
        seg = segment('s1', 0, 4, shots=((1, 0, 24), (2, 24, 24), (3, 48, 24), (4, 72, 24)))
        lines = [{'start': 0.5, 'end': 2.5, 'text': 'one two three four'}]
        plan = lipsync.shot_lyrics(seg, lines)
        self.assertEqual([p['sung'] for p in plan], [True, True, True, False])      # shot 3 holds only 0.5 s? no: 2.0-2.5 s
        self.assertEqual(' '.join(p['words'] for p in plan if p['sung']), 'one two three four')
        self.assertEqual(plan[3]['words'], '')
        self.assertEqual(lipsync.shot_lyrics(seg, [])[0], {'n': 1, 'sung': False, 'words': ''})

    SINGER = ['<Picture 3>', '<Subject 3>']
    OTHERS = ['<Picture 1>', '<Subject 1>', '<Picture 2>', '<Subject 2>']

    def check(self, bodies, lines, shots=None):
        seg = segment('s1', 0, 4, shots=shots or tuple((i + 1, i * 48, 48) for i in range(len(bodies))))
        singing = {'picture_tag': '<Picture 3>', 'lines': lines}
        return lipsync.lipsync_problems(' '.join(bodies), bodies, seg, singing, self.SINGER, self.OTHERS)

    def test_actors_appear_as_subject_tags_in_shots_and_the_check_understands_that(self):
        lines = [{'start': 0.0, 'end': 4.0, 'text': 'Interdimensional lover'}]
        good = ['<Subject 3> sings "interdimensional" with lips shaping each word. <Subject 1> keeps lips sealed.',
                '<Subject 3> holds the note, mouthing "lover" again.']
        self.assertEqual(self.check(good, lines), [])
        wrong_tag = ['<Subject 1> sings "interdimensional".', '<Subject 1> sings "lover".']
        self.assertTrue(self.check(wrong_tag, lines))
        sealed = ['<Subject 3>’s lips are sealed, his jaw relaxed.', good[1]]
        self.assertTrue(any('Shot 1' in p and 'sealed' in p for p in self.check(sealed, lines)))
        no_quote = [good[0], '<Subject 3> sways with eyes closed.']
        self.assertTrue(any('Shot 2' in p for p in self.check(no_quote, lines)))
        two_words = [{'start': 0.0, 'end': 4.0, 'text': 'hello there dear friend'}]
        missing_words = ['<Subject 3> sings "hello there" with lips shaping each word.', '<Subject 3> sings with lips shaping a long held vowel.']
        self.assertTrue(any('Shot 2' in p and 'must quote' in p for p in self.check(missing_words, two_words)))
        elsewhere = ['<Subject 1> is the singer. ' + good[0], '<Subject 1> sways. The word lover is on a banner.']
        self.assertTrue(any('Shot 2' in p for p in self.check(elsewhere, lines)))
        tail = [good[0] + ' ' + RIGGING_TAIL, good[1]]
        self.assertTrue(any('sealed-lips closing phrase' in p for p in self.check(tail, lines)))

    def test_quoted_lyrics_with_punctuation_are_not_split_into_sentences(self):
        lines = [{'start': 0.0, 'end': 2.0, 'text': 'Yes! I am your help fren.'}]
        for quote in ('"Yes! I am"', "'Yes! I am'", '“Yes! I am”'):
            body = [f'<Subject 3> sings {quote} while his lips shape every word. <Subject 1> keeps lips sealed.']
            self.assertEqual(self.check(body, lines, ((1, 0, 48),)), [], quote)
        self.assertEqual([c for c, _ in lipsync._units("It's a hum. He sings 'Hello, there! Yes.' loudly. Done.", ['<S3>'], [])],
                         ["It's a hum.", "He sings 'Hello, there! Yes.' loudly.", 'Done.'])

    def test_the_third_real_writer_attempt_with_pronouns_and_mixed_sentences_is_accepted(self):
        """Shots 6, 13 and 14 of the real halp fren writer response: 'He sings ...' continues the sentence about
        the singer, and a sentence can show the singer singing while another actor keeps sealed lips."""
        shots = ((1, 0, 18), (2, 18, 18), (3, 36, 18))
        lines = [{'start': 0.0, 'end': 2.25, 'text': 'I am your help fren. Web gooey'}]
        words = [w['words'] for w in lipsync.shot_lyrics(segment('s', 0, 4, shots=shots), lines)]
        bodies = ["The camera holds a static shot from over the shoulder of <Subject 3>, whose black hood frames his strong jaw. "
                  f"He sings '{words[0]}', his lips moving with precise articulation, his jaw working in time with the music.",
                  f"A two shot frames <Subject 3> and <Subject 1>, the runway lights casting shadows. <Subject 3> sings '{words[1]}', "
                  "his lips moving with precise articulation, while <Subject 1> watches with a relaxed expression, her lips sealed.",
                  f"An extreme close-up shows <Subject 3>'s face as he sings '{words[2]}', his brows raised. His lips move with exaggerated precision."]
        self.assertEqual(self.check(bodies, lines, shots), [])
        bystander = [bodies[0], bodies[1].replace('her lips sealed', 'she hums along'), bodies[2]]
        self.assertTrue(any('only <Subject 3> sings' in p for p in self.check(bystander, lines, shots)))
        pronoun_of_other = [bodies[0], '<Subject 1> dances beside him. She sings along loudly.', bodies[2]]
        self.assertTrue(any('only <Subject 3> sings' in p for p in self.check(pronoun_of_other, lines, shots)))

    def test_only_pronoun_led_sentences_continue_an_actor_and_open_bystander_mouths_are_refused(self):
        lines = [{'start': 0.0, 'end': 0.75, 'text': 'terminal'}]
        shot = ((1, 0, 24),)
        # real writer text: a scene clause about "the sung word" is not blamed on a bystander who is not visible
        scene = ['<Subject 3> sings "terminal" with lips shaping the word. <Subject 1> is not visible, but the sung word resonates in the frame.']
        self.assertEqual(self.check(scene, lines, shot), [])
        # real writer text: a bystander whose lips part is refused
        parted = ['<Subject 3> sings "terminal" with his jaw working. <Subject 1> turns its head and its lips part as it listens.']
        self.assertTrue(any('only <Subject 3> sings' in p for p in self.check(parted, lines, shot)))
        pronoun = ['<Subject 3> sings "terminal" with his jaw working. <Subject 1> dances beside him. Her mouth opens wide.']
        self.assertTrue(any('only <Subject 3> sings' in p for p in self.check(pronoun, lines, shot)))
        sealed = ['<Subject 3> sings "terminal" with his jaw working. <Subject 1> watches, her lips sealed and her mouth not open.']
        self.assertEqual(self.check(sealed, lines, shot), [])

    def test_a_single_sung_word_needs_the_singer_singing_but_not_a_quote(self):
        lines = [{'start': 0.0, 'end': 0.75, 'text': 'No'}]
        self.assertEqual(self.check(['<Subject 3> sings with his lips shaping a short word.'], lines, ((1, 0, 24),)), [])
        self.assertTrue(self.check(['<Subject 3> stands in the crowd.'], lines, ((1, 0, 24),)))

    def test_a_shot_without_the_singer_must_say_no_one_is_singing(self):
        lines = [{'start': 0.0, 'end': 2.0, 'text': 'hello there'}]
        silent_frame = ['<Subject 1> and <Subject 2> dance. <Subject 3> is absent from this frame, and no one on screen is singing.']
        self.assertEqual(self.check(silent_frame, lines), [])
        vague = ['<Subject 1> and <Subject 2> dance together under lights.']
        self.assertTrue(self.check(vague, lines))

    def test_the_bypasses_codex_found_stay_rejected(self):
        lines = [{'start': 0.0, 'end': 2.0, 'text': 'hello there'}]
        self.assertTrue(self.check(['<Subject 3> keeps lips firmly sealed while <Subject 1> sings "hello there".'], lines))
        self.assertTrue(self.check(['<Subject 3> keeps lips firmly sealed beside a sign reading "hello there".'], lines))
        self.assertTrue(any('separate sentences' in p for p in self.check(['<Subject 3> and <Subject 1> sing "hello there" together.'], lines)))
        self.assertTrue(any('only <Subject 3> sings' in p for p in
                            self.check(['<Subject 3> sings "hello there" with lips shaping each word. <Subject 1> hums along loudly.'], lines)))
        ok = ['<Subject 3> sings "hello there" while lips and jaw shape each word. <Subject 1> keeps lips firmly sealed and does not sing.']
        self.assertEqual(self.check(ok, lines), [])
        self.assertEqual(self.check(['<Subject 3> is not silent: the voice rings as he sings "hello there" with open lips.'], lines), [])
        # two actors in a sentence without any mouth claim is fine
        self.assertEqual(self.check(['<Subject 1> and <Subject 3> walk past. <Subject 3> sings "hello there" with open lips.'], lines), [])

    def test_the_real_writer_output_that_failed_the_first_halp_fren_run_is_flagged_where_it_was_wrong(self):
        """Shots from the first real GPU-test writer response (Henchman = Subject 3): shot 6 says his lips are sealed
        while the lyric is sung; shot 7 does not describe singing; shot 13 correctly says he is absent."""
        shots = tuple((n, (n - 1) * 18, 18) for n in range(1, 4))           # three 0.75 s shots, all inside a sung line
        lines = [{'start': 0.0, 'end': 2.25, 'text': 'Yes! I am your help fren.'}]
        bodies = ['<Subject 3>’s lips are sealed, his jaw relaxed. <Subject 1>’s updo hair is visible over his shoulder.',
                  'The camera tilts down from <Subject 3>’s black boots to <Subject 1>’s tan sandals as they move in tandem.',
                  '<Subject 1> and <Subject 2> dance together. <Subject 3> is absent from this frame, and no one on screen is singing.']
        problems = self.check(bodies, lines, shots)
        self.assertTrue(any('Shot 1' in p and 'sealed' in p for p in problems))
        self.assertTrue(any('Shot 2' in p and 'does not describe' in p for p in problems))
        self.assertFalse(any('Shot 3' in p for p in problems))
        fixed = ['<Subject 3> sings "Yes! I" in time with the music, his lips and jaw forming the words. <Subject 1> keeps lips sealed.',
                 '<Subject 3> sings "am your" with his jaw working, his stomping boots keeping the beat.', bodies[2]]
        self.assertEqual(self.check(fixed, lines, shots), [])

    def test_guessed_lines_never_unseal_a_passage_until_confirmed(self):
        segs = [segment('s1', 0, 6)]
        cast = casting(('s1', ['pig']))
        guessed = [{'start': 0.0, 'end': 6.0, 'text': 'never actually heard', 'timing': 'interpolated'},
                   {'start': 1.0, 'end': 5.0, 'text': 'barely matched', 'timing': 'uncertain'}]
        plan = lipsync.plan_passages(segs, cast, lipsync.clean_lines(guessed), ['pig'], seed=1)
        self.assertFalse(plan['passages']['s1']['singing'])
        self.assertEqual(plan['unconfirmed_lines'], 2)
        confirmed = [{**line, 'timing': 'manual'} for line in guessed]
        self.assertTrue(lipsync.plan_passages(segs, cast, lipsync.clean_lines(confirmed), ['pig'], seed=1)['passages']['s1']['singing'])
        with self.assertRaises(ValueError):
            lipsync.clean_lines([{'start': 0, 'end': 1, 'text': 'x', 'timing': 'maybe'}])

    def test_section_labels_travel_with_the_lines_into_the_passage_job(self):
        lines = lipsync.clean_lines([{'start': 2, 'end': 4, 'text': 'hello there', 'section': ' Chorus '}, {'start': 5, 'end': 6, 'text': 'plain'}])
        self.assertEqual(lines[0]['section'], 'chorus')
        self.assertNotIn('section', lines[1])
        sung = lipsync.passage_lines(lines, 1.5, 4.5)
        self.assertEqual(sung[0]['section'], 'chorus')
        with self.assertRaises(ValueError):
            lipsync.clean_lines([{'start': 0, 'end': 1, 'text': 'x', 'section': 'y' * 41}])

    def test_shots_with_little_singing_are_not_required_to_sing(self):
        lines = [{'start': 0.0, 'end': 2.2, 'text': 'one two three'}]
        bodies = ['<Subject 3> sings "one two three" clearly.', 'A quiet street at dusk with drifting leaves.']
        self.assertEqual(self.check(bodies, lines, ((1, 0, 48), (2, 48, 48))), [])


if __name__ == '__main__':
    unittest.main()
