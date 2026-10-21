"""Small repairs for writer replies that are almost valid JSON."""
from __future__ import annotations

import json
import re

STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)
CONTROL = re.compile(r'[\x00-\x1f]')
BROKEN_JSON = 'writer did not return valid JSON'
MAX_FREE_RETRIES = 2


def escape_control_characters(raw):
    """Escape raw newlines/tabs inside JSON strings (a common local-model slip); text outside strings is untouched."""
    return STRING.sub(lambda m: CONTROL.sub(lambda c: json.dumps(c.group())[1:-1], m.group()), raw)


def is_broken_json(problems):
    return len(problems) == 1 and problems[0].startswith(BROKEN_JSON)


def draft_feedback(shot_bodies):
    """The previous draft, so a retry revises it instead of rewriting every shot from scratch."""
    return ('\n\nYour previous draft of the shots follows. Revise only the shots the failures name; '
            'keep every other shot exactly as written:\n' + json.dumps(shot_bodies, indent=1))
