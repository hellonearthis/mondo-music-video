# Collaborator review record

## October 18, 2026 — fork integration, head 4e1cbb0 (release 1.6.10)

Fetched into an isolated checkout at task start. Reviewed `3365943..4e1cbb0`
(10 commits, fork releases 1.6.5 to 1.6.10). Codex ran a read-only adversarial
review of the working tree (it could not reach GitHub from its sandbox).

| Change | Decision | Reason and evidence |
| --- | --- | --- |
| `app.js` split into `webapp/js/*.js` modules | Adopted with fixes | Fork tests read module-private values as globals (`saveProject`, `sseConnected`, `sseSource`) and failed; tests now import the modules via read-only exports. Package data lacked `js/*.js`; added. Local `compact_prompts` and vocabulary-editor fixes re-applied in the modules. |
| Preview/Start busy states, banners | Adopted | Covered by the browser suite. |
| Theme contrast and sticky sidebar | Adopted | CSS only. |
| Vocabulary guide dialog and endpoint | Adopted | Serves `docs/VOCABULARY_GUIDE.md`; reuses the existing file. |
| Local-writer context hint | Adopted | Message text only. |
| Operation-log clearing at start | Adopted | Active run stays visible. Not exercised against a real long run. |
| Configurable encoders (added then reverted) | Nothing to adopt | Net zero in 1.6.10. |
| Facial-movement label "(when lyrics present)" | Kept this repository's label | Depends on the owner's decision on the lyrics-gated silent-mouth rule (see TEAM_STATUS). |
| Vocabulary preset lost on project reopen | Fixed (Codex finding, confirmed in code) | Catalog now loads before project restore; regression test fails on the original order. |

Version: 1.6.10 matches the fork's label so different content does not collide
with the fork's numbering. Writer/ident prompts, `schema.py` and `style.py` are
unchanged by these commits.

## October 18, 2026 — fork integration, head 3365943 (release 1.6.4)

Fetched into an isolated checkout at task start. Reviewed `7f87f91..3365943`
(fork 1.6.2 to 1.6.4, author hellonearthis); it contains the previously deferred
dock and the 14ee458 leftovers. Codex ran a read-only adversarial review of the
applied tree; the coordinator read the dock, pipeline, worker, quality, vision and
web-layer diffs. Full suite 253 passed, 53 subtests, mock services only.

| Change | Decision | Evidence / remaining work |
| --- | --- | --- |
| Vocabulary customizer, presets, API, agent and MCP (30 tools) | Adopted with a fix | Codex found stale editor text overwriting loaded/reset drafts; confirmed in code, fixed, browser regression test added (fails on the original). Skill and agent docs extended. |
| Status dock (`mmv/services.py`) | Adopted with a fix | Cache is keyed by store; only user-configured URLs probed, no credentials returned. Initial SSE probe moved off the event loop. Job-thread callback still probes on a cache miss: not shown to be a problem. |
| Token reductions (compact job JSON, stable system prompt, ident trimming) | Adapted: opt-in `compact_prompts`, default off | The owner's hand-written prompts stay the default. Trimming measured on the real 64 KB ident prompt in every mode. Tests pin the default to the original prompt and message. Effect of compact prompts on output quality is untested. |
| Vision frames at 512 px and `max_tokens` 160 | Adapted: only with `compact_prompts`; full-size frames and no cap by default | Real GPU comparison (see VERIFICATION.md): one borderline frame in 16 judged differently at 512 px; saved about 1.5 s per clip. |
| `--image-min-tokens 1024` in `start.ps1` | Adopted, not yet gated | Windows launcher only; not exercised here. Remaining work: decide whether it belongs behind the compact option. |
| Single-pass ffmpeg frames, streaming hashes, parallel probes | Adopted | Covered by existing tests. |
| Test acceleration and fork test edits | Adopted; one fix | Fork browser test expected an old version string; corrected. |
| Rewritten RELEASES and VERIFICATION history | Omitted | It renamed and replaced this repository's records; a new 1.6.4 entry credits the fork instead. |

Version: 1.6.4 matches the fork's final label, as with 1.3.0, to avoid a number
collision for different content. Codex could not reach GitHub from its sandbox.

## October 18, 2026 — OAP 0.3 integration

Fetched hellonearthis's fork into an isolated temporary checkout at task start.
The new head `78f31ae33f50a9578043d2af33ce05158603ab86` is a merge of this
repository's 1.2.1 (`d6aa193`) into the fork's `764ca66`, labeled fork version
1.2.2. Compared with `d6aa193` it carries the pending hardware status dock
(`180b237`), earlier fork changes from `14ee458` not adopted in 1.1.2 (Laya torch
import placement, validation message wording, `--image-min-tokens 1024` for
vision models in `start.ps1`, vocabulary counts and an engine test), and merge
content of its own: a server-sent `log` event listener in `app.js`, dock refresh
wiring, a longer page title, two test adjustments and version/doc relabeling.
None of it was integrated in this OAP release; it was outside the assigned task
and has not yet had a full review. The dock and these items remain deferred, not
rejected, pending the focused integration pass described below.

This release is numbered 1.3.0 so it does not collide with the fork's 1.2.2
label for a different build.

## October 17, 2026 — starter assets in agent installation

Fetched the isolated collaborator checkout; origin/main is still
`764ca66843843217d51c8708cb1e1fa952d9f364`, with no new commits. This
1.2.1 follow-up integrates public starter imports into both installers and adds
local actor/style deletion controls. No actor asset contents or workflow defaults
change; the separate collaborator hardware dock remains pending its focused review.

## October 17, 2026 — agent installation and provider setup

Fetched the isolated collaborator checkout again: origin/main remains
`764ca66843843217d51c8708cb1e1fa952d9f364`. No new contributions were found.
The hardware/status dock review below remains pending its focused integration;
this setup delivery does not change either collaborator's workflow defaults.

## October 17, 2026 — startup updater development

Checked and downloaded hellonearthis's fork through `764ca66` into an isolated
checkout at task start. The previously integrated substantive review remains
`132c3d3` (released here in 1.1.2).

The new feature commit `180b237` adds a live engine/hardware status dock through
`mmv/services.py`, API status fields, UI components and tests. The merge also
contains this repository's already-published 1.1.0 and public style presets.
Those upstream assets and defaults are already present here.

The dock is useful collaborative work and is deferred, not rejected. It is a
separate UI/monitoring feature from the requested startup updater, and needs a
focused integration pass before claiming equivalent behavior here. Specific
review items from initial code inspection:

- Its probe cache is process-global rather than keyed by store/settings; verify
  invalidation and isolation when configured endpoints change.
- Probe calls perform synchronous network requests from status/event handling;
  measure their effect on event-loop responsiveness and disconnected services.
- Verify status semantics for SDK/proxy rendering and explicit Laya fallback
  selections, keeping the owner's defaults and the collaborator's options.
- Review returned endpoint/error details for credential redaction and check the
  dock at mobile widths and in both themes.

These are review questions from code inspection, not claimed test failures.
Next review should compare `132c3d3..764ca66` against the current main branch,
exercise the new tests with mocks, and integrate the dock with fixes where
needed. Do not silently skip it or re-import already published style assets.
