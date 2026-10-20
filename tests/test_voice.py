import tempfile
import unittest
from pathlib import Path

from mmv import voice


def tone(path, hz, seconds=4.0, sr=22050):
    import numpy as np
    import soundfile
    t = np.arange(int(seconds * sr)) / sr
    soundfile.write(str(path), 0.4 * np.sin(2 * np.pi * hz * t), sr)


class VoiceTests(unittest.TestCase):
    def test_pitch_classes(self):
        self.assertEqual(voice.classify_pitch(120, 10), 'male')
        self.assertEqual(voice.classify_pitch(330, 10), 'female')
        self.assertIsNone(voice.classify_pitch(200, 10))      # overlap range: unsure
        self.assertIsNone(voice.classify_pitch(120, 1))       # too little voiced audio
        self.assertIsNone(voice.classify_pitch(None, 10))

    def test_estimate_from_tones(self):
        with tempfile.TemporaryDirectory() as temp:
            low, high = Path(temp) / 'low.wav', Path(temp) / 'high.wav'
            tone(low, 110)
            tone(high, 330)
            self.assertEqual(voice.estimate_voice(low)['gender'], 'male')
            self.assertEqual(voice.estimate_voice(high)['gender'], 'female')

    def test_actor_gender(self):
        self.assertEqual(voice.actor_gender('Adult female with a gaunt build. She wears a dress. Her makeup is pink.'), 'female')
        self.assertEqual(voice.actor_gender('A man in a suit. He is tall and his coat is grey.'), 'male')
        self.assertIsNone(voice.actor_gender('A pink pig in a tracksuit.'))
        self.assertIsNone(voice.actor_gender('A woman and a man stand together. She, he.'))
        self.assertIsNone(voice.actor_gender(None))

    def test_check_singer(self):
        genders = {'a': 'female', 'b': 'male', 'c': None}
        self.assertEqual(voice.check_singer('male', genders, 'a'), {'warn': True, 'voice': 'male', 'singer': 'female', 'suggested': 'b'})
        self.assertFalse(voice.check_singer('male', genders, 'b')['warn'])
        self.assertFalse(voice.check_singer('male', genders, 'c')['warn'])      # unknown singer: silent
        self.assertFalse(voice.check_singer(None, genders, 'a')['warn'])        # unsure voice: silent
        self.assertIsNone(voice.check_singer('male', {'a': 'female'}, 'a')['suggested'])


class FakeStore:
    def __init__(self, home, descriptions):
        self.home, self.descriptions = home, descriptions

    def actor(self, actor_id):
        return {'description': self.descriptions[actor_id]}


class VoiceCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = FakeStore(self.home, {'her': 'A woman. She wears red. Her hair is long.', 'him': 'A man. He wears blue. His coat is long.',
                                           'pig': 'A pink pig.'})
        self.plan = {'singer': 'her', 'actors': {'her': 'Her', 'him': 'Him', 'pig': 'Pig'}}

    def cache(self, gender):
        import json
        from mmv import stems
        folder = stems._root(self.store)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"voice-abc-{stems.model_for('vocals')}.json").write_text(
            json.dumps({'gender': gender, 'median_hz': 120.0, 'voiced_seconds': 30.0}))

    def test_warns_and_suggests_match(self):
        self.cache('male')
        result = voice.voice_check(self.store, 'abc', {}, self.plan)
        self.assertTrue(result['warn'])
        self.assertEqual((result['suggested'], result['suggested_name']), ('him', 'Him'))
        self.assertEqual(result['genders'], {'her': 'female', 'him': 'male', 'pig': None})

    def test_silent_cases(self):
        self.assertIsNone(voice.voice_check(self.store, 'abc', {}, self.plan))             # no stem yet: nothing runs
        self.cache(None)
        self.assertIsNone(voice.voice_check(self.store, 'abc', {}, self.plan))             # unsure voice
        self.assertIsNone(voice.voice_check(self.store, 'abc', {}, None))                  # not a lip-sync production
        self.cache('female')
        self.assertFalse(voice.voice_check(self.store, 'abc', {}, self.plan)['warn'])      # match: reported, not warned


if __name__ == '__main__':
    unittest.main()
