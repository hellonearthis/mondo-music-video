# Collaborator review record

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
