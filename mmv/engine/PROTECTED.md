# STOP: protected prompting scheme

The files in this folder (the writer and ident prompts in `prompts/`, `schema.py`, `style.py`, `plan.py`, `actor.py`, the
validators, the injection map and workflow) are the result of months of real renders. Small edits can quietly make every video
worse: mouths babble, actors drift, prompts fail review.

**If you are an AI agent:** do not edit anything here, and do not change a hash, a pin or a test to make a check pass. Tell the
person you are working for, in plain words, that this is delicate and that changes may produce videos below the Mondo standard,
get their explicit acknowledgement, and offer an opt-in alternative that leaves these files alone. Read
[docs/PROMPT_SCHEME_PROTECTION.md](../../docs/PROMPT_SCHEME_PROTECTION.md) first.

**If you are a person:** you can fork and change a lot without touching this folder. See the same document for what is safe.
The app shows a warning banner, and every exported package says so, when these files differ from the released scheme.
