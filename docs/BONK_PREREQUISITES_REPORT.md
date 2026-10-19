# Actor-dancing prerequisite handoff

Scope: build step 0 of the approved revision-2 design. Base revision:
`aeade8c4490b9473561b556f1098ea91519efcd8`. The design was absent from
this isolated worktree and was read, without modification, from the main
checkout's `docs/BONK_DESIGN.md`. No dance module or dance tests were touched.

## Changes

- `mmv/worker.py`: passage cache lookup now uses `seg_system`, matching save.
  Singing passages can reuse cached prompts. Singing hits run schema and
  lip-sync checks, then the existing quality check. Sealed/natural hits retain
  their existing quality check and sealed rigging-tail insertion. Saved-run
  fallback also recognizes `writer_system_singing.md`.
- `mmv/worker.py`: `passage_cache_key`, optional `extra_validators` on lookup,
  and optional `validators_version` on lookup/save form the integration hook.
  Empty version preserves the existing `validated-v2` key byte for byte.
  Validators reject both direct and saved-run cache hits; exceptions cause a
  cache miss. `cached_shot_bodies` extracts assembled shot clauses for checks.
- `mmv/passage_plans.py`: a version-1 SHA-256 binding covers non-null `lipsync`
  and `dance` values. New productions with these plans store
  `passage_plan_binding` in `prepared.json`. After prompt validation, the worker
  writes `passage-plan-prompts.json`, binding the plan and the exact prompt map.
  Unsupported versions, changed plans, changed prompts or a missing prompt
  binding stop guarded resume with an explicit digest-mismatch message.
- `mmv/pipeline.py`, `mmv/production.py`, `webapp/mondo_web.py`: resume eligibility,
  the resume quote's second preparation, and start all use `prepare_resume`.
  Normal preparation still rechecks inputs/OAP/workflow/settings, but skips
  lip-sync planning when saved versioned plans exist and restores the saved
  per-passage decisions. Produce verifies again before overwriting files;
  direct worker resume verifies too. Binding metadata is excluded from quote
  fingerprints. Legacy runs without the binding continue to replan as before.
- `tests/test_passage_prerequisites.py`,
  `tests/fixtures/passage_worker_golden.json`: recorded sealed, natural and
  lip-sync golden fixtures BEFORE implementation edits, and verified all seven
  initial baseline tests before editing. They record actual worker-composed
  system text, JSON job, assembled prompt at each mocked validator boundary,
  validator-call order and saved cache keys. Writer and validation services are
  mocked; these fixtures prove orchestration equivalence, not render quality.
  Recorded quote fingerprints cover omitted/legacy mouth fields too. Future
  off-mode fields are injected at the worker boundary; the API does not yet
  accept dance fields.
- `tests/test_passage_plan_resume.py`: replay, corruption, version mismatch,
  prompt binding, pre-overwrite rejection, legacy behaviour, actual preparation
  planner bypass, new-run binding persistence, and route-level resume/start
  checks without a socket server. Consent is still required at start.

## Deliberate limits and next integration

This is the narrow saved-plan fix, not complete replay of all preparation.
Timing, casting, score, style, references and settings are still rebuilt and
subject to the existing quote fingerprint. Subliminal planning is unchanged.
Legacy runs receive no retroactive integrity guarantee and are not migrated.
The digest is an accidental-change check, not an authenticated signature.

The future dance planner must honor `saved_prepared`/the saved-plan branch
before doing new planning. Restoration already preserves `dance`, but this
branch cannot bypass a future planner until that planner is wired accordingly.
Future dance cache wiring must append its checks, use the same non-empty
`validators_version` for lookup and save, and preserve the existing mouth checks.
Cached shot clauses contain assembly-inserted cut/timestamp prefixes.

Step 1 must separately preserve request/prepared fingerprint normalization when
adding off-default API fields. This delivery does not add those fields or claim
that future API normalization is already implemented. No prompts or protected
rules were changed, and no real renders were performed.

No version bump, commit, push, external fork check, dependency download or paid/GPU
work was performed. The explicit no-network instruction superseded the normal
fork-check rule. Full integration testing needs a sandbox permitting localhost
mock servers and working ASGI transports; see validation below.

## Validation

- Initial pre-edit golden baseline: 7 passed.
- Final prerequisite, protected-scheme and worker vision-stage selection:
  66 passed in 2.44s. The protected-scheme ASGI endpoint test was excluded
  because its transport stalls in this sandbox; the other protection tests ran.
- `git diff --check`: passed.
- Requested full command was launched with `PYTHONPATH=$PWD` and the shared
  absolute virtualenv interpreter. It accumulated errors and stalled; stopped
  with exit 130. A focused integration failure showed Numba could not write its
  cache beside the shared virtualenv.
- Full-suite rerun with `NUMBA_CACHE_DIR=/tmp/bonk-numba-cache` accumulated errors
  and a failure, then stalled. A 120-second bound plus 10-second termination
  grace ended it with exit 137. No complete suite summary is available; further
  failures cannot be ruled out.
- Diagnostic full collection with the same temporary Numba cache and `-x
  --tb=short`: 50 passed, 3 errors, 21 subtests passed in 16.46s (exit 2).
  All three reported errors were `PermissionError: Operation not permitted`
  when browser/agent/OAP fixtures attempted localhost mock HTTP server sockets.
  The earlier integration-specific retry hit the same socket restriction.
- Logs remain in `/tmp/bonk-full-pytest.log`,
  `/tmp/bonk-full-tmp-cache-pytest.log`, `/tmp/bonk-first-failure.log` and
  `/tmp/bonk-resume-pytest.log`. The full suite must be rerun in an environment
  allowing its mock servers and ASGI transport; it is not claimed green.
