"""Small repairs for writer replies that are almost valid JSON."""
from __future__ import annotations

import json
import re

STRING = re.compile(r'"(?:[^"\\]|\\.)*"', re.S)
CONTROL = re.compile(r'[\x00-\x1f]')
THINK_BLOCK = re.compile(r'<think>.*?</think>', re.S | re.I)
BROKEN_JSON = 'writer did not return valid JSON'
MAX_FREE_RETRIES = 2

LAYA_STYLE_DIVERGENCE_THRESHOLD = 0.65
LAYA_STYLE_RETRY_NOTE = (
    'Semantic Validator rejected: Style adherence was judged divergent from the style card. '
    'Re-anchor lighting, surface texture, and edge behaviour to the aesthetic directives.'
)


def extract_json_object(raw: str) -> str:
    """Strip <think>...</think> reasoning blocks and extract the outermost balanced JSON object if wrapped in commentary."""
    text = THINK_BLOCK.sub('', str(raw or '')).strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith('```'):
            text = '\n'.join(lines[1:-1]).strip()
    start = text.find('{')
    if start < 0:
        return text
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    return text[start:]


def escape_control_characters(raw):
    """Strip <think> wrappers/commentary and escape raw newlines/tabs inside JSON strings; text outside strings is untouched."""
    extracted = extract_json_object(raw)
    return STRING.sub(lambda m: CONTROL.sub(lambda c: json.dumps(c.group())[1:-1], m.group()), extracted)


def is_broken_json(problems):
    return len(problems) == 1 and problems[0].startswith(BROKEN_JSON)


def laya_style_feedback(response: dict | None, strict: bool = False) -> tuple[list[str], list[str]]:
    """Inspect Laya's style_adherence judgment without altering the protected validator.

    Returns (advice_notes, retry_problems). High-confidence style divergence (>= 0.65) is always recorded
    in advice_notes for operator visibility, and escalated to retry_problems when strict_prompt_checks is active.
    """
    if not isinstance(response, dict):
        return [], []
    answers = response.get('answers')
    if not isinstance(answers, dict):
        return [], []
    adherence = answers.get('style_adherence')
    if not isinstance(adherence, dict):
        return [], []
    selected = str(adherence.get('selected') or '').strip().lower()
    try:
        confidence = float(adherence.get('confidence') or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if selected != 'divergent' or confidence < LAYA_STYLE_DIVERGENCE_THRESHOLD:
        return [], []
    advisory = (
        f"Laya style adherence note: judged divergent (confidence {confidence:.2f}); "
        "check lighting, surface texture, and edge behaviour against the style card."
    )
    return [advisory], ([LAYA_STYLE_RETRY_NOTE] if strict else [])


def draft_feedback(shot_bodies):
    """The previous draft, so a retry revises it instead of rewriting every shot from scratch."""
    return ('\n\nYour previous draft of the shots follows. Revise only the shots the failures name; '
            'keep every other shot exactly as written:\n' + json.dumps(shot_bodies, indent=1))
