"""Golden parity and failure checks for the extracted music-video engine."""
from dataclasses import asdict
import ast
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mmv.engine.analyze import ScoreMap
from mmv.engine.plan import plan
from mmv.engine.backends import get_backend
from mmv.engine.schema import WriterResponse, assemble_prompt, validate_prompt
from mmv.engine.validators.laya_semantic import LayaSemanticValidator

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=Path(__file__).parent/'fixtures'

class OriginalEngineTests(unittest.TestCase):
    def test_original_golden_plan(self):
        score=ScoreMap.from_json(FIXTURES/'score.json')
        actual=plan(score,width=1024,height=576,vocab=json.loads((ROOT/'mmv/engine/config/vocab.json').read_text()),
                    seed=17,cast_size=3,ref_policy='all',bars_per_phrase=2,backend=get_backend('local_h3'))
        self.assertEqual(asdict(actual),json.loads((FIXTURES/'plan.json').read_text()))

    def test_unchanged_original_source_hashes(self):
        manifest=json.loads((ROOT/'docs/SOURCE_EXTRACTION.json').read_text())
        unchanged=[entry for entry in manifest if entry['adaptation']=='none']
        self.assertGreaterEqual(len(unchanged),10)
        for entry in unchanged:
            self.assertEqual(hashlib.sha256((ROOT/entry['public']).read_bytes()).hexdigest(),entry['sha256'],entry['public'])

    def test_hosted_phrase_shrinks_on_original_musical_edges(self):
        vocab=json.loads((ROOT/'mmv/engine/config/vocab.json').read_text())
        for name in ('local_h3','wavespeed','seedance_2','seedance_2_5'):
            score=ScoreMap.from_json(FIXTURES/'score.json');backend=get_backend(name)
            result=plan(score,width=1024,height=576,vocab=vocab,seed=17,cast_size=1,ref_policy='all',backend=backend)
            self.assertEqual(result.segments[0].song_start_frame,0)
            self.assertEqual(sum(s.trim_frames for s in result.segments),score.duration_frames)
            for seg in result.segments:
                self.assertLessEqual(seg.gen_frames,backend.max_gen_frames)
                self.assertGreaterEqual(seg.gen_frames,seg.trim_frames)
                if seg.song_start_frame:self.assertIn(seg.song_start_frame,score.downbeat_frames)

    def test_laya_rejects_and_formats_original_corrective_note(self):
        validator=LayaSemanticValidator()
        clip={'state':{'shot_count':4},'questions':[]}
        problems=validator.decide({'answers':{'visual_density':{'expected_level':1,'confidence':.9},
            'structural_completeness':{'selected':'missing_action'},'restriction_adherence':{'selected':'safe','confidence':.9}}},clip)
        self.assertTrue(problems)
        self.assertIn('Give every shot a concrete action',validator.format_retry_feedback(problems))
        self.assertEqual(validator.decide({'answers':{'visual_density':{'expected_level':1,'confidence':.01}}},clip),[])

    def test_no_nsfw_workflow_or_controls(self):
        workflows=list((ROOT/'mmv/engine/workflows').glob('*.json'))
        self.assertEqual(len(workflows),1)
        graph=json.loads(workflows[0].read_text())
        self.assertFalse(any('lora' in n.get('class_type','').lower() for n in graph.values()))
        for file in ('webapp/index.html','webapp/mondo_web.py'):
            self.assertNotIn('nsfw_local',(ROOT/file).read_text())

    def test_python_311_syntax(self):
        for directory in ('mmv','webapp'):
            for path in (ROOT/directory).rglob('*.py'):
                ast.parse(path.read_text(),filename=str(path),feature_version=(3,11))

if __name__=='__main__':unittest.main()
