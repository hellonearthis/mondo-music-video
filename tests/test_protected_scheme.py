import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmv import protected_scheme

ROOT = Path(__file__).resolve().parents[1]
WHY = ("The protected prompting scheme changed. Do NOT edit the pins or this test to make it pass. Warn the person you work for "
       "that this can make videos worse, get their explicit approval, validate real before/after renders and read "
       "docs/PROMPT_SCHEME_PROTECTION.md. Only the scheme's owner re-pins, with tools/update_protected_pins.py --owner-approved-change.")


class ProtectedSchemeTests(unittest.TestCase):
    def test_the_scheme_is_as_released(self):
        self.assertEqual(protected_scheme.check(), [], WHY)
        self.assertIsNone(protected_scheme.notice())

    def test_a_changed_deleted_or_retyped_item_is_detected_and_line_endings_are_not(self):
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp)
            for path in protected_scheme.FILES:
                (copy / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, copy / path)
            with patch.object(protected_scheme, 'ROOT', copy):
                self.assertEqual(protected_scheme.check(), [])
                writer = copy / 'mmv/engine/prompts/writer_base.md'
                writer.write_bytes(writer.read_bytes().replace(b'\n', b'\r\n'))        # a Windows checkout is not a change
                self.assertEqual(protected_scheme.check(), [])
                writer.write_bytes(writer.read_bytes() + b'\nBe more concise.\n')
                self.assertEqual(protected_scheme.check(), ['mmv/engine/prompts/writer_base.md'])
                self.assertIn('the writer prompt', protected_scheme.notice())
                self.assertIn('may not meet the Mondo standard', protected_scheme.notice())
                (copy / 'mmv/engine/schema.py').unlink()
                self.assertEqual(set(protected_scheme.check()), {'mmv/engine/prompts/writer_base.md', 'mmv/engine/schema.py'})
            with patch.dict(protected_scheme.TEXTS, {'mmv.lipsync.SINGING_RULES': '0' * 64}):
                self.assertEqual(protected_scheme.check(), ['mmv.lipsync.SINGING_RULES'])
                self.assertIn('the singing wording', protected_scheme.describe(protected_scheme.check()))

    def test_changing_how_prompts_are_composed_is_caught_even_when_no_text_changes(self):
        from mmv.engine import style
        real = style.compose_writer_prompt

        def without_the_sealed_rule(*args, **kwargs):
            kwargs['silent_mouths'] = False                       # the composer stops inserting the sealed-lips rule
            return real(*args, **kwargs)
        with patch.object(style, 'compose_writer_prompt', without_the_sealed_rule):
            changed = protected_scheme.check()
        self.assertIn('composed writer prompt (sealed mouths)', changed)
        self.assertEqual(protected_scheme.check(), [])
        with patch.object(style, 'compose_ident_prompt', return_value='shorter ident'):
            self.assertEqual(protected_scheme.check(), ['composed ident prompt'])
        with patch.object(style, 'compose_writer_prompt', side_effect=RuntimeError('broken')):
            self.assertIn('prompt composition', protected_scheme.check())

    def test_every_protected_rule_and_the_prompts_are_pinned(self):
        pinned = set(protected_scheme.FILES) | set(protected_scheme.TEXTS)
        for needed in ('mmv/engine/prompts/writer_base.md', 'mmv/engine/prompts/ident_base.md', 'mmv/engine/schema.py',
                       'mmv/engine/validators/base.py', 'mmv.engine.style.SILENT_MOUTHS_RULE_V013', 'mmv.engine.schema.RIGGING_TAIL',
                       'mmv.engine.style.NATURAL_MOUTHS_RULE', 'mmv.lipsync.SINGING_RULES', 'mmv.lipsync.SINGING_AUDIO_SENTENCE',
                       'mmv.quality.WRITER_RULES', 'mmv/engine/plan.py', 'mmv/engine/style.py', 'mmv/engine/actor.py',
                       'mmv/engine/workflows/h3_ref2video_audionodeadded.json', 'mmv/engine/validators/laya_semantic.py'):
            self.assertIn(needed, pinned, f'{needed} must stay pinned. {WHY}')

    def test_the_guidance_that_stops_agents_is_present_and_names_the_warning_step(self):
        agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        self.assertIn('Protected prompting scheme', agents)
        self.assertIn('stop and warn the person', agents)
        self.assertIn('Never edit the pins', agents)
        guide = (ROOT / 'docs/PROMPT_SCHEME_PROTECTION.md').read_text(encoding='utf-8')
        for phrase in ('Stop and warn the person', 'below the Mondo standard', 'opt-in', 'Never hide a change', 'before and after'):
            self.assertIn(phrase.lower(), guide.lower())
        self.assertIn('STOP: protected prompting scheme', (ROOT / 'mmv/engine/PROTECTED.md').read_text(encoding='utf-8'))
        owners = (ROOT / '.github/CODEOWNERS').read_text(encoding='utf-8')
        self.assertIn('/mmv/engine/', owners)
        self.assertIn('/mmv/protected_scheme.py', owners)

    def test_the_pin_updater_refuses_without_the_owner_flag(self):
        done = subprocess.run([sys.executable, str(ROOT / 'tools/update_protected_pins.py')], capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn('Do not run it to make a check pass', done.stderr + done.stdout)
        self.assertEqual(protected_scheme.check(), [])

    def test_the_app_reports_integrity_and_a_modified_scheme_gets_a_notice(self):
        from fastapi.testclient import TestClient
        from webapp.mondo_web import create_app
        with tempfile.TemporaryDirectory() as temp:
            client = TestClient(create_app(temp, test_hosts=True))
            self.assertEqual(client.get('/api/integrity').json(), {'intact': True, 'changed': [], 'notice': None})
            with patch.object(protected_scheme, 'check', return_value=['mmv/engine/prompts/writer_base.md']):
                body = client.get('/api/integrity').json()
            self.assertFalse(body['intact'])
            self.assertEqual(body['changed'], ['the writer prompt'])
            self.assertIn('Mondo standard', body['notice'])


if __name__ == '__main__':
    unittest.main()
