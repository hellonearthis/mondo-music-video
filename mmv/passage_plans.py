"""Persistence guard for per-passage decisions that saved prompts depend on.

This is an integrity check, not a signature. Input/workflow/OAP/consent checks
remain the responsibility of normal preparation and quote fingerprinting.
"""
import hashlib
import json
from copy import deepcopy
from .storage import read_json, write_json

VERSION = 1
FIELDS = ('lipsync', 'dance', 'instruments')
KEY = 'passage_plan_binding'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def plans(prepared):
    return {key: prepared[key] for key in FIELDS if prepared.get(key) is not None}


def binding(prepared):
    return {'version': VERSION, 'digest': digest(plans(prepared))}


def verify(prepared):
    saved = prepared.get(KEY)
    if KEY not in prepared:
        if prepared.get('instruments') is not None:
            raise ValueError('Saved instrument plan has no binding; restore the original prepared.json before resuming')
        if prepared.get('dance') is not None:
            raise ValueError('Saved dance plan has no binding; restore the original prepared.json before resuming')
        return False  # Legacy runs keep the old preparation/resume behaviour.
    if (not isinstance(saved, dict) or type(saved.get('version')) is not int
            or saved != binding(prepared)):
        raise ValueError('Saved passage plan version or digest mismatch; restore the original prepared.json before resuming')
    return True


def restore(current, saved):
    if not verify(saved):
        return current
    result = dict(current)
    for key in FIELDS:
        if key in saved:
            result[key] = deepcopy(saved[key])
        else:
            result.pop(key, None)
    result[KEY] = deepcopy(saved[KEY])
    return result


def bind_prompts(directory, prepared, prompts):
    if verify(prepared):
        write_json(directory / 'passage-plan-prompts.json', {**prepared[KEY], 'prompts_digest': digest(prompts)})


def verify_prompts(directory, prepared):
    if verify(prepared):
        expected = {**prepared[KEY], 'prompts_digest': digest(read_json(directory / 'prompts.json', {}))}
        if read_json(directory / 'passage-plan-prompts.json', {}) != expected:
            raise ValueError('Saved prompts and passage plan digest mismatch; restore the original prompts and plan before resuming')
