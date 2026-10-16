"""Test-only worker bootstrap: mock the learned decision model, retain its adapter."""
from unittest.mock import patch
from mmv.worker import main

class Agent:
    cfg = {}
    def system_one(self, state, questions):
        answers = {}
        for key, question in questions.items():
            if key == 'visual_density':
                answers[key] = {'type':'score', 'score':3, 'probabilities':{'0':0,'1':0,'2':0,'3':1,'4':0}, 'confidence':1}
            else:
                selected = {'structural_completeness':'complete','style_adherence':'strong_match','restriction_adherence':'safe'}[key]
                answers[key] = {'type':'choice','choice':selected,'confidence':1}
        return {'answers':answers}

if __name__ == '__main__':
    with patch('mmv.engine.validators.laya_semantic.LayaSemanticValidator._load_agent',return_value=Agent()):
        main()
