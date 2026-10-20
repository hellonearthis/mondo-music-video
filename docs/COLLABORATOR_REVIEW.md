# Collaborator review record

## October 19, 2026 — independent dance differentiation (1.8.5)

At the owner's request Claude Code reviewed the repair read-only (CLI-reported
`claude-haiku-5-5`; receipt in the ignored local collaboration report). The first
sandbox attempt failed DNS; the network-enabled attempt completed. No fork work
was included: the owner explicitly directed focus on dancing.

Confirmed from the operator test's saved jobs/prompts: separate stem cues shared
generic move-per-beat hints, a prompt called a dancer the lead, and names instead
of tags bypassed action attribution. Added independent-only movement families
and checks without altering protected originals or group/off rules.

Adopted Claude findings: reject identical mixed-family signatures; resolve
collisions among three choreographed actors even with a larger selected roster;
distinguish copying another dancer from following music or a mirror prop;
handle affirmative nonstop actions and body actions in mouth-policy sentences;
run both dance test classes under direct unittest execution. Added regression
coverage. Name attribution uses saved cast display names; it remains lexical.

Claude questioned approval for the additive independent rule block. Existing
owner approval is recorded in BONK_DESIGN.md and the prior task handoff; this
repair stays within that opt-in mode, leaving protected prompts/pins untouched.
No automatic paid retry was added. Camera repetition is confirmed but recorded
only on the roadmap, per the owner's deferral. Real same-song/seed validation of
the revised choreography remains outstanding.

## October 19, 2026 — live-test timeout repair (1.8.4)

Task-start check found new fork head `eeab8c0b729650d41fa8f2b0093750129c543f9b`.
Fetched into isolated `/tmp/mmv-fork-review-20261019`, without changing the main
checkout or sharing object stores. Focused review of the timeout repair confirms
hellonearthis independently identified the `None`/numeric comparison failure seen
in our real local render test. Adapted at the worker boundary with numeric infinity
so the owner's unlimited-wait default remains; protected engine files stay intact.
The fork's finite 7200-second default is not silently substituted for that default.
The numeric-adapter mock regression simulates history arriving after 9000 seconds.

Other new fork commits (`63f4826`, `8b70f0a`, `bff3b9e`, `183eeb8`, `312b0c3`)
include incomplete-run management/deletion, functional vocabulary/library/output UI,
service-offline handling and concurrent service probes, plus upstream review fixes.
Initial scope inspection confirms substantial unrelated UI/service changes (25 files,
including the timeout commit). Full correctness/privacy/defaults/consent review and
mock integration of those contributions is deferred to a separate integration batch,
rather than expanding this explicitly requested real dance test. They are not rejected
or claimed fully reviewed; latest fully completed broad review remains `1704454`.


## October 19, 2026 — independent dancing (1.8.3)

Task-start fork check: `1704454c4d3f538866b1cb3eed72af5dfb74f0e5`,
unchanged from the completed review below. No new fork contributions to integrate.
Claude Code reviewed current integration read-only through the guarded launcher;
CLI-reported model and receipt are recorded in the ignored local task board.
Antigravity's independent UI/API review has now been received and checked against
the implementation. Its model/effort are self-reported as Gemini 3.8 Flash / High,
not independently verified. The reviewer ran no tests or renders and made no tracked
edits. Both requested reviews are received; visual render validation remains pending.

| Claude finding | Disposition |
| --- | --- |
| Stem cues ignore score edits | Fixed: apply the same edits to copies of stem analysis; regression checks nudge, muted beats and bar phase without modifying caches. |
| Parse failure can retain stale soft-advice draft | Fixed: clear prompt after parsing/assembly failure and require an assembled prompt before retaining a fallback. |
| Empty stem energy mislabeled measured | Fixed: explicit mix fallback for empty-energy parts. |
| Failed cached analysis aborts preview | Fixed: unreadable/failed part analysis falls back independently. |
| Part override names a non-dancer | Intentional API validation, not a defect: reject inconsistent selections rather than silently ignore them. UI currently selects the whole cast. |
| Auto cycle includes explicit overrides | Intentional stable slot assignment: an override must not shift other actors' automatic parts. Documented and tested. |
| Mouth/body sentence can be excluded from lexical dance check | Existing conservative check retained: changing shared mouth-sentence treatment risks group-mode regression. Independent instructions request each visible dancer's body action. A targeted future validator change needs separate fixtures. |
| Soft-advice prompts revalidated on cache reuse | Existing safety behavior retained. Relaxing cache validation needs separate review; no paid submission retries added. |


| Antigravity observation | Verified disposition |
| --- | --- |
| Stable assignments, actor-ID persistence, explicit fallback, semantic controls and unchanged mouth rules | Confirmed against implementation and existing browser/API/worker tests. No blocking defect reported. |
| Optional grid layout for many actors | Deferred cosmetic suggestion; the current native controls remain usable. No measured layout failure was reported, so this review handoff adds no product changes. |
| Deselected actors retain manual overrides | Intentional: reselecting an actor restores their choice, while request serialization filters to currently selected actors. Existing browser test covers binding preservation. |
| Existing stem analysis only | Clarification: existing stem WAVs can also be analyzed on CPU with a worker subprocess. This does not download models, separate audio or submit network/paid work. |

The report's statement that the implementation "strictly satisfies all project
constraints" is a read-only review assessment, not proof of generated video quality
or precise synchronization. The recorded mock-suite results remain the verification
evidence; same-song/same-seed real comparison is still outstanding.


## October 19, 2026 — Antigravity review follow-up (release 1.8.2)

Antigravity delivered its read-only review of fork `1704454`; model/effort were
self-reported as Gemini 3.8 Flash / High, not independently verified. Codex checked
all findings against the integration and original 1.8.0 source.

| Finding | Verified disposition |
| --- | --- |
| Navigation recursion, multi-fold restoration, actor numbering | Already fixed in 1.8.1 with browser coverage. Recursion crosses an `await`; repeated asynchronous reopening is established, while the report's synchronous stack-overflow mechanism is not. |
| Missing vocabulary guide dialog | Confirmed, including in pre-fork 1.8.0. Restored a small dialog displaying the existing guide endpoint and wired its Open Visual vocabulary action to the sidebar workspace. Both guide entry points and the return action are covered in Chromium. |
| Stale guide navigation to removed editor dialog | Confirmed stale code; now targets the workspace. The formerly missing guide meant this handler was unreachable before the repair. |
| Dark hover contrast on the new overflow button | Confirmed pale-on-pale colors. Added a dark background/light foreground hover rule; browser regression computes rendered contrast and requires at least 4.5:1. |
| Overflow action lacks category context | Added a category-specific accessible name, checked in Chromium. |
| Unapplied draft discarded on navigation/reopen | Preserved existing Apply/discard semantics, added visible workspace copy explaining them. A dirty indicator or draft-preservation change remains a separate UX decision; it is not silently enabled. |
| Category tab roles | Pre-existing accessibility gap. Deferred to a complete keyboard/focus/tab-semantics implementation; adding roles alone would leave tab keyboard behavior incomplete. |
| Narrow action bar wrapping | Review concern, not a demonstrated regression; no viewport measurement was supplied. Deferred responsive assessment rather than presenting it as a proven collision. |
| Legacy dialog class names | Harmless CSS compatibility names retained to avoid unnecessary selector churn. |

Antigravity made no tracked edits or test/render calls. Both requested helper reviews
are now received and triaged. Validation is recorded in VERIFICATION.md.

## October 19, 2026 — fork integration, head 1704454 (release 1.8.1)

Reviewed isolated checkout `/tmp/mmv-fork-review-20261019` at exact revision
`1704454c4d3f538866b1cb3eed72af5dfb74f0e5`, following last reviewed fork head
`dc71556b5ef12876042ce0ab13fda5bcc5c9670f`. The intervening history includes our
own releases through `47c745a` (1.8.0), merged by fork commit `889abc7`; the new
contribution commits from hellonearthis are `50e7d59` and `1704454`.
Compared their final tree against our current 1.8.0, rather than reapplying our releases.

| Contribution | Decision and evidence |
| --- | --- |
| Targeted vocabulary summary updates | Adopted: edit only the affected category card; cap summary chips at 20 with a link to the complete category tab. Browser regression checks that unrelated cards keep their DOM identity. |
| Dedicated Visual vocabulary workspace | Adopted with fixes: the fork's `panel("vocab")` called `openVocabularyPanel()`, which unconditionally clicked the same navigation button, causing repeated asynchronous reopening and draft resets. Navigation now occurs only when the workspace is hidden; initialization does not navigate again. Restore the saved vocabulary and profile before opening the workspace. |
| Three advanced production folds | Adopted with independent persistence: the fork saved whether any fold was open but restored only the first. Stable fold IDs and `details_sections` preserve each fold; old `details_open` drafts still restore. Updated moved-control browser selectors and actor navigation numbers. |
| Windows Python UTF-8 mode | Adopted: `start.ps1` adds `-X utf8` to the application launch. No prompt files, scheme pins or protection tests changed. Windows execution remains unverified on this Linux host. |
| Version and assertions | Adopted 1.8.1 once for this delivery; updated additional browser assertions missing from the fork and retained our release history. |

Claude Code independently reviewed the in-repository fork diff and integration (CLI receipt:
`claude-haiku-5-5`, read-only; no tests run by the helper). The coordinator triaged its
additional findings against `47c745a`:

| Additional review point | Disposition |
| --- | --- |
| Navigation silently swallows catalog-loading errors | Fixed: workspace navigation reports failures through the existing notice UI. |
| Hidden quick bar/saved-key row allegedly overridden by flex CSS | Rejected with evidence: `style.css` already has global `[hidden]{display:none!important}`; the helper missed it. |
| Random key retained after manual edits; randomization switches replace to append | Existing behavior in the original `buildPseudoRandomDraft`, category randomization and edit handlers, unchanged by these commits. Deferred to a separate vocabulary behavior change with reproduction tests; clarify whether the key describes the initial draw or the entire edited selection before changing its semantics. |
| Empty category possible through checkboxes/Clear all | Existing UI validation gap; `mmv/pipeline.py:apply_vocabulary_overrides` rejects an empty final pool explicitly. Deferred: add consistent UI validation without changing the planner. |
| Quick Reset clears manual customizations without confirmation | Existing handler and reset behavior, unchanged. Deferred: review wording/confirmation and preservation of manual additions as a separate usability fix. |
| Duplicate counts and preset/custom layering | Existing counting and preset handlers; backend deduplicates final pools. Layering impact remains to be reproduced. Deferred: test effective pools and align displayed counts before changing behavior. |
| Deleted preset selection not immediately saved | Existing delete handler, unchanged. Deferred: reproduce delete/reload and add a persistence regression test. |
| Summary header keyboard access and legacy dialog branches | Existing header and compatibility branches; new overflow control is a native button that opens the complete tab. Deferred header accessibility cleanup; no removal of compatibility code in this integration. |

Antigravity was assigned a separate read-only UI review via the local task board; no
callable terminal connection was available and no report had arrived at validation time.
That review was pending for 1.8.1; the completed follow-up is recorded above.

No new renderer/model defaults, paid submissions, retry paths, OAP behavior or private assets
are introduced by this delta. Agent/MCP operation continues through the existing vocabulary
preset tools and preview fields; no new tool is needed for a web navigation/layout change.
Validation is recorded in the delivery verification notes. No commit, push or publication
is part of this integration.


## October 19, 2026 — contributor credit by history merge (owner-authorized exception)

On the owner's instruction, the fork's 22 commits after the shared base `7f87f91`
(all authored as the collaborator's GitHub account) were recorded in this
repository's history with `git merge -s ours` from `dc71556`, fetched into a
separate ref. The merge changed no files: the integrated code had already been
reviewed and adopted by hand (releases 1.6.4 to 1.6.11). The files touched by
those commits were listed first and contained only source and documentation, no
actors, media, models, keys or data. This is an exception to the rule against
sharing Git object stores with the fork and is not a precedent.

## October 19, 2026 — fork integration, head dc71556 (release 1.6.11)

Fetched at the owner's request after head 4e1cbb0. One commit, `dc71556`: pseudo-random
vocabulary generator with reproducible keys, quick editing and preset saving.

| Change | Decision | Reason and evidence |
| --- | --- | --- |
| Pseudo-random vocabulary keys (`vocabulary.js`, `index.html`, `style.css`, `vocab_random_key` in the project state) | Adopted with a fix | Draft-replacing paths now use `showVocabCategory`; the largest category (269) fits the 500-entry exclude cap; project persistence test passes. A key is only reproducible while the built-in lists are unchanged (noted in RELEASES). |
| Version 1.6.11 | Matches the fork | Owner's compact option, labels and silent-mouth decision preserved when merging `index.html`. |

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
