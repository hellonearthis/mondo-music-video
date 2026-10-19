# Verification — 1.6.1


## 1.6.1 RunPod installation guidance (2026-10-18)

The final tree passed `.venv/bin/python -m pytest -q` outside the sandbox:
**240 tests and 53 subtests**, no skips (75.69 s). A fresh-process import of
`api_version()` returned **1.6.1**; package metadata, README, agent discovery
and version assertions were updated together. The existing user service was
not restarted for this guidance release; no live 1.6.1 claim is made.

Local Markdown links, RunPod shell example syntax (`bash -n`) and
`git diff --check` passed. Earlier socket-free checks built the existing H3 graph
with zero, one and two synthetic image references plus song audio, confirming
resolved tags, preserved loader parameters and the effective 20-step injection.
No graph was submitted for these checks.

The documentation was checked against the implementation's loopback binding,
Host/origin guards, private workflow/model selection, environment/data paths and
both H3 render paths. Official RunPod SSH, storage and exposed-port documentation
and ComfyUI H3 guidance were consulted on 2026-10-18. The fork HEAD remained
`78f31ae33f50a9578043d2af33ce05158603ab86`, matching the prior reviewed revision.

**No RunPod Pod was provisioned and no fresh RunPod installation or alternative
H3 variant was tested.** The guides require agent-side discovery, private
workflow adaptation/activation and deliberate operator-approved inference before
claiming readiness. They do not implement automatic arbitrary-workflow
conversion. No GPU/paid/Topaz work or model downloads were performed for 1.6.1.

## 1.6.0 final release verification (2026-10-18)

After the user authorized the same-song $0 GPU test and release on success,
Codex ran `.venv/bin/python -m pytest -q` outside the sandbox on the final
implementation: **240 tests and 53 subtests passed**, no skips (80.76 s).
Freshly imported and live `/api/version` handlers both reported **1.6.0**.
JavaScript syntax and `git diff --check` passed.

Real RTX 4090 SDK production `f33d46265cb24ef3a51a31d32fb12036` reused the
11.5-second Interdimensional Lover song, seed 23, robobabe1 and animal_pig,
at 736×416, with `vision_quality_check: true`. The quote and consent recorded
**$0**. The operator's existing ComfyUI was deliberately stopped under explicit
user authorization before preview; Mondo then launched and owned its renderer.
Both passages rendered through the existing SDK proxy and passed batched pixel
checks (motion **2.018** and **13.487**, no uniform borders).

Mondo stopped its ComfyUI, GPU memory dropped to approximately 1.5 GiB, and the
local Qwen vision model started and judged both passages. Both vision verdicts
were **pass**, with no problems. `vision.json` recorded requested/ran true and a
null note; no retry or warning occurred. The vision service shut down after
judging and GPU memory returned to approximately 1.2 GiB. Final output decoded
without errors: **276 video frames, 11.5 seconds, 736×416, with audio**. A sampled
contact sheet was inspected. Generated media and private run data remain local.

This live run verifies the normal renderer-to-vision handoff, proxy rendering,
judging and cleanup. A vision-triggered renderer restart/retry was not exercised
on real hardware because neither clip failed; that path is covered by mock tests.
Windows/macOS model swaps remain unverified.

Claude Code independently repeated the run as `f1abfe7deb1b444184667a2ea588dce9`
with ComfyUI initially closed and the proxy left running: Mondo launched and
later stopped only its own ComfyUI, Qwen loaded in about 10 s, and the vision
server log shows 16 slot launches for the 16 sampled frames, confirming one
image per request on the real llama-server. Both passages again passed pixel and
vision checks; afterwards ports 8188 and 8083 were closed, the external proxy
process was untouched and GPU memory was about 1.2 GiB.

The task-start fork check returned unchanged HEAD
`78f31ae33f50a9578043d2af33ce05158603ab86`; prior substantive findings and deferred
integration work remain in [COLLABORATOR_REVIEW](COLLABORATOR_REVIEW.md).

## 1.6.0 earlier sandbox completion (2026-10-18)

Outside the Codex sandbox, Claude Code ran the full suite on the integrated
checkout: **240 tests and 53 subtests passed**, no skips, and a freshly imported
version handler reported 1.6.0. At that handoff, real GPU use of the vision
check was not yet verified; see the final verification above.

Codex ran the following selection in the main checkout, with the existing
`.venv`, synthetic temporary media and mocked services:

```sh
.venv/bin/python -m pytest -q -n 0 tests/test_vision_stage.py tests/test_sdk_recovery.py tests/test_vision_check.py tests/test_quality.py::ClipInspectionTests tests/test_quality.py::PromptRuleTests tests/test_original_engine.py
```

Result: **111 tests and 20 subtests passed**, no skips (21.75 s).
Breakdown: orchestration/agent discovery 27, SDK recovery 22, vision module 45,
pixel inspection/prompt rules 8, original engine 9. Vision HTTP fixtures used
their in-process mocked transport fallback because the sandbox cannot bind
local sockets. This does not verify real HTTP service transport.

The new orchestration tests cover service ownership and swap order, restart
before vision retries, Qwen startup failures as warning-only verdicts, occupied
vision-port refusal, startup ownership races, request flag default/opt-in,
preview errors on both H3 backends, external ComfyUI skip notes, SDK launch
behavior, persisted `vision.json`/output warnings, and interrupted checks.
Pure batch tests cover pixel-first retries, one shared budget per passage,
pixel-authoritative selection, paid/unlisted renderer guards, hash-keyed verdict
reuse and spent-retry recovery. Agent preview preserves the flag through a
mocked transport; in-process MCP discovery still exposes 28 tools and includes
the new preview documentation. An exploratory MCP tool invocation stalled in
the sandbox and was interrupted; the final selection tests discovery only.
The full MCP stdio/HTTP transport checks were not run.

A separate fresh Python process imported `api_version()` and returned **1.6.0**;
pyproject.toml and README matched. No live `/api/version` request was made, and
no claim is made about an existing running app's version. `node --check
webapp/app.js`, `bash -n install.sh` and `git diff --check` passed. Original engine
hashes passed in the selected tests. Browser version assertions were updated
but browser tests were not run.

The full suite was **not run** in this takeover: local-socket tests require an
unrestricted environment. User/Claude must run `.venv/bin/python -m pytest -q`
outside the sandbox. The earlier 213-test handoff result predates these changes
and is not validation of this final tree. Phase 4 still requires an explicitly
operator-run GPU production with vision enabled, ComfyUI initially closed and
the proxy available. Vision startup failure deliberately completes using pixel
checks with a warning. No paid, GPU, Topaz or network work occurred here; the
fork update check was deferred under the user's offline instruction. Nothing
was committed, pushed, tagged or published.

## 1.5.0 motion and framing quality gates

The full suite passed **140 tests and 53 subtests**, with no skips (optional
SDK and Playwright extras installed). New `tests/test_quality.py` covers moving,
frozen, pillarboxed and dark-edged synthetic clips, a frozen shot inside a moving
passage, inspection errors, prompt rules including negations and director
framing requests, and production retry policy on the direct local renderer, the
SDK path (separate receipts and jobs), WaveSpeed (one paid submission, warning
only), persistent failures, unmeasurable retries and idents. Codex reviewed the
design and implementation; all findings were adopted. Original engine source
hashes are unchanged.

Real GPU proof on the operator's RTX 4090 through `comfy_sdk_h3`: the request
that produced a frozen, white-pillarboxed first passage in 1.4.0 was repeated
with the same seed, cast and plan. The planner again chose a static camera; the
writer, under the new rules, described visible subject and environmental motion
and passed the prompt checks and Laya on the first attempt. Both passages passed
the clip gate without a retry: passage 1 per-shot motion 2.03 (previously 0.05)
with no borders; passage 2 per-shot motion 7.0-26.3. Visual review confirmed a
full-frame moving first passage. The run took about nine minutes and cost $0.

## 1.4.0 Watch the song conduct

The full suite passed **110 tests and 53 subtests** (15 optional-extra skips).
New `tests/test_score_view.py` covers seconds conversion, downbeat/beat/split cut
classification, opening-ident offsets, refusal for idents, missing analysis and
unknown runs, and absence of local paths. The agent test reads the score of a
complete mocked production; MCP stdio discovery verifies 28 tools and 1.4.0.

Chromium was driven against a copy of a real run (ad hoc Playwright script):
caption updates, click seeking, playback sync, keyboard cut-to-cut seeking with
Home/End, slider ARIA values, no growth in live views across repeated output
refreshes, both themes, no horizontal overflow at 390 px and no page errors.
Codex adversarial review found an observer leak and missing keyboard access;
both were fixed and re-checked. The reinstalled live app on the operator's data
reported `/api/version` 1.4.0 and served the score for its music video (seven
planned cuts, all on beats, three on downbeats). No generation ran.

## 1.3.0 Open Actor Protocol 0.3

With OAP 0.3.0 (`35902b1`) installed, the full suite passed **107 tests and 53
subtests** (15 skipped: optional Comfy SDK and Playwright/SDK browser flows). The
new `tests/test_oap_v03.py` covers audition exports (cast assets omitted, hashes
kept, audition-cleared reference included, imported actors refused), schema
rejection with JSON paths, local two-role signing, outside-Agent countersigning
through a returned agreement, altered-terms and forged-signature refusal, rider
conflicts, and fail-closed verification when a stored manifest or casting call
is missing, damaged or substituted. Agent client tests cover the same workflow
and the `confirm` guard; MCP stdio discovery verifies 27 tools and version 1.3.0.
The four 0.2 starter packages still schema-validate and verify under 0.3.

The Actors tab was driven in Chromium against a temporary data directory (an
ad hoc Playwright script, not a committed test): audition export, drafting,
Director and Agent signing, verification and bundle download, with no page
errors, both themes, and no horizontal overflow at 390 px. Codex adversarial
review found two fail-open verification cases; both were fixed and tested. A
locally built wheel contains `mmv/agreements.py` and pins OAP 0.3.0. No paid,
GPU or Topaz work ran. A freshly imported version handler and the restarted live
app's `/api/version` both reported 1.3.0 against the operator's existing data
(85 actors loaded). Native Windows/macOS runs were not performed.

## 1.2.1 starter installation and local library deletion

The full suite passed **113 tests and 53 subtests in 36.22 seconds**, including
six Chromium flows. Additional targeted starter tests passed **6 tests in
10.42 seconds**, including a stubbed Python/pip shell-installer check for starter
invocation, noninteractive signer acceptance, flag order and explicit opt-out.
No dependencies were downloaded by that test. Native PowerShell execution
remains an operator check; the script uses the same starter command/flags.

Temporary-data tests verify all four signed OAP imports, preserved original
packages, complete styles, existing/custom-ID preservation, corrupted-bundle
refusal before import, pending signer acceptance, deletion blocked during active
operations, deletion persistence across Storage recreation/installer reruns,
explicit starter restoration, retained exports, and refusal to follow asset
symlinks during deletion. Chromium verifies canceled/confirmed deletion, removal
from cast/style selectors, reload persistence and absence of browser errors.
Shell/JavaScript syntax and diff checks passed. No paid, GPU or Topaz work ran.

MCP stdio discovery verifies 22 tools and app version 1.2.1. New tool tests cover
API add/select/remove, confirmation refusal, no secret values in results, manual
configuration restoration, bounded settings patches and update inspection,
provider-model discovery with mocked HTTP, public starter signer review/import,
actor/style deletion and explicit restoration. Profile activation/deletion,
settings patches and starter imports refuse active operations. A final targeted
provider run passed **7 tests and 10 subtests in 1.04 seconds**, including rejection
of a provider that echoes its discovery credential in a model ID.

Source and wheel packages include only the four authorized public actor packages
and six complete style presets; bundle hashes and private-file exclusions were
checked. An isolated installed-wheel import from outside the checkout installed
all ten starters in temporary data, preserving signed OAP packages. Native
PowerShell remains unverified. Existing MCP clients require a reconnect.

Final operator checks freshly imported the 1.2.1 version handler, restarted the
idle preview and confirmed live `/api/version` 1.2.1. A fresh stdio connection
launched the installed wheel in isolated Python mode from outside the checkout:
MCP initialization reported **1.2.1**, discovery returned **22 tools**, and its
read-only version tool reached the live **1.2.1** app. This check changed no
operator profiles, actors, styles or production data.

## 1.2.0 agent installation and multiple API profiles

The complete suite passed **104 tests and 52 subtests in 30.04 seconds**,
including five Chromium flows. Profile checks exercise independent role/account
selection, credential isolation from generic environment keys, key updates,
manual configuration restoration, no silent overwrites, owner-only POSIX file
permissions, invalid/cross-role profiles, active-operation guards and agent CLI
save/list/activation. Browser verification switches writer accounts while
retaining a separate vision account, saves a profile through Settings, and
restores manual configuration. Additional targeted profile checks cover malformed
configuration and redaction of an inactive account's key from historical logs.

Mock API discovery checks cover GET-only requests, invalid URLs, missing keys,
bounded/invalid responses, redacted errors and blocked redirects. The discovery
CLI creates no application data and submits no generation. Local guide links
and pinned writer metadata were checked. JavaScript/Python syntax and diff
checks passed. Both source and wheel packages built; their contents include the new modules
and source installation guides, with only the four authorized actor packages.
Private profiles, data, secrets and contest notes are excluded. No real provider calls, paid generations, GPU inference
or Topaz work ran.

Fresh version-handler import and the restarted live `/api/version` report
**1.2.0**. Native Windows execution and real provider chat/video compatibility
remain operator checks. New video APIs require an adapter; this release supplies
the agent implementation guide rather than a universal video API client.
The collaborator fork remains `764ca66843843217d51c8708cb1e1fa952d9f364`.

## 1.1.3 optional startup updater

The complete suite passed **93 tests and 38 subtests in 28.48 seconds**, including
four Chromium flows. Updates default off in storage and API settings. Browser
checks verified the update/version notice, repository link, and toggling/saving
the preference in both directions. Disposable local Git tests covered normal and
non-default tracked branches, notify-only checks, clean fast-forward updates,
re-exec arguments, checkout leases, unchanged private assets, ignored collisions,
local changes/divergence, interrupted operations, offline preparation and package
installation/recovery failures. Pip was mocked for these Git transaction tests.

A separate offline check used actual pip to install, upgrade and restore a tiny
mock application wheel in a disposable virtualenv; it did not modify the operator
installation. Actual full-MMV upgrade/dependency recovery and native Windows
restart remain operator checks. No paid, GPU or Topaz operations ran.

Python compilation, JavaScript/shell syntax and diff checks passed. Both 1.1.3
wheel and source packages built; the updater and update guide are included, and
private data, credentials and contest/video planning notes are excluded. Update
state/log files are explicitly ignored and excluded from source distributions.
The four previously authorized actor packages remain the only packaged roster.

Fresh handler import and the restarted live `/api/version` reported 1.1.3.
The live settings endpoint confirmed `auto_updates: false`, and startup completed
its tracked-repository check without installation. Collaborator revision
`764ca66` was downloaded/reviewed for task-start context; the separate new dock
is recorded in `COLLABORATOR_REVIEW.md` for focused follow-up.

## 1.1.2 expanded aspect selectors

Final publication check: **75 tests and 38 subtests passed in 30.32 seconds**,
including all three Chromium flows, using temporary data and mock services.

Verified all 13 aspect options in both music-video and ident dropdowns, including
9:21 immediately after 21:9. Every option passed the API request schema and
resolution planning for both local H3 and SDK H3 at 0.6 MP. Existing backend
dimension-grid snapping is unchanged. The version consistency test passed;
fresh version import and restarted live preview reported 1.1.2. The launcher
bounds graceful shutdown so open event streams cannot indefinitely block exit.
No GPU or paid generation ran. This release also includes the reviewed 1.1.1
integration described below.

## 1.1.1 reviewed fork integration

Reviewed fork revision `132c3d3` (hellonearthis). The complete suite passed:
**75 tests and 38 subtests in 29.99 seconds**, including all three Chromium flows.
New checks cover song bytes and Range requests, blocked non-audio/symlink access,
actual HTTP event delivery and disconnect cleanup, job diagnostic extraction and
secret redaction, opt-in device selection, alternate vocabulary integrity, song
playback/reload, model-preserving writer tuning and polling after a connected
stream fails. Tests use temporary storage, synthetic media and mock inference;
no paid, GPU or Topaz work ran.

A fresh version-handler import and the restarted live preview reported 1.1.1.
Python compilation, JavaScript syntax, shell syntax and diff whitespace checks
passed. The original default vocabulary, golden fixture, planner/casting source,
H3 workflow/map and storage defaults are unchanged. Friend-specific tuning,
fallback and reduced-vocabulary settings are selectable alternatives.

The 1.1.1 wheel and source distribution built successfully. The wheel contains
the optional vocabulary profile; source archives contain only the four approved
actor packages, with no local data, private keys or contest/video planning notes.
All local application data remains ignored and untracked.

Native PowerShell/Windows execution and real Laya device availability were not
verified here. Device selection tests stub hardware and inference; they do not
load a model. Real GPU SDK execution remains the separate operator check below.

## Optional public style presets

All six published preset hashes and API schemas were verified. Installing the
six JSON files into temporary application storage exposed all six alongside
Daylight Cinema through `/api/styles`. Public copies contain SFW costume/sound
adaptations and explicit content boundaries; private local originals were not
modified. The source distribution includes exactly these six presets, with no
local actor/style data, credentials or private contest/video planning files.
No paid or GPU operations ran. The app version remains 1.1.0.

## 1.1.0 browser title

Verified that the HTML title is `🪿 Mondo Music Video`. The version consistency
test passed; a fresh handler import and the restarted live preview both reported
1.1.0. Diff whitespace checks passed. Imported styles remain local pending review.

## 1.0.16 resizable cast selector

Both existing Chromium flows and the version consistency test passed (3 tests,
10.58 seconds). A separate browser check with the 85-actor local roster dragged
the list from 160px to 333px, retained the selected actor, and confirmed no page
overflow at a 360px viewport. Fresh handler import and live `/api/version` both
reported 1.0.16. JavaScript syntax and diff whitespace checks passed. No paid or
GPU work ran; all local actor files remain ignored.

## Optional starter cast publication

Verified exactly four signed OAP archives against their allowlist and SHA-256
manifest. Each contains only `manifest.json` and `identity/reference.png`;
reference hashes match the selected local images. All four imported into a
temporary empty roster, retained their visual descriptions, and passed casting
checks. No paid or GPU operations ran. All 255 local actor files remained
ignored and untracked. A built source distribution contained exactly the four
approved packages and no local data, private keys, studio metadata backups,
credentials or contest notes. This asset/documentation addition leaves the
application at 1.0.15.

## 1.0.15 default dark theme

Verified default dark rendering, switching to light, preference persistence across
reloads in both directions, and a visible toggle without page overflow at 360px.
Desktop and mobile previews were visually inspected. The initial full run passed
67 tests and 28 subtests; one browser flow encountered a reload/restore timing
race in the test. Moving the theme reload checks to the end resolved it: both
browser flows passed on the focused rerun (9.33 seconds). JavaScript syntax and
diff checks passed. Fresh version import and live `/api/version` reported 1.0.15.

## 1.0.14 actor card overviews

All 68 tests and 28 subtests passed in 25.87 seconds, including existing Chromium
flows. JavaScript syntax and diff whitespace checks passed. The display helper
was checked against all 85 local actors: each returned its Identity overview,
without Hair or later sections; plain descriptions remained intact. Full stored
descriptions were unchanged. A fresh version-handler import and the restarted
live preview `/api/version` both reported 1.0.14.

Run from a checkout:

```sh
python -m pip install '.[comfy,mcp,test]'
python -m pytest -q
# Optional serial execution:
python -m pytest -q -n 0
# The existing unittest runner also remains supported:
python -m unittest discover -s tests -v
node --check webapp/app.js
bash -n install.sh
```

The automated suite uses temporary data, synthetic media and local mock AI
services. It runs the actual analyzer, planner, writer contract, Laya adapter,
renderer adapters and FFmpeg assembly. Learned Laya decisions are mocked in
that suite; no model download or paid generation is triggered by running tests.

Coverage includes source hashes and original golden plans; backend phrase/frame
limits; reference-slot contracts; OAP signatures, riders and package integrity;
hosted consent and request receipts; failed-writer render prevention; cancellation
of the app's own local job; single-operation enforcement; agent CLI and real MCP
transports; credentials; local HTTP boundaries; downloader integrity; and Topaz
command construction with preservation of the source video.

## 1.0.13 expanded vocabulary

All **68 tests passed**, plus 28 subtests, in **25.29 seconds** with four
workers. Both Chromium flows ran, and live temporary agent/browser test servers
reported 1.0.13. Fresh version imports, Python compilation, JavaScript/shell
syntax and whitespace checks passed. No user service was restarted.

The supplied vocabulary data is copied as an owner-authorized SFW subset,
recorded in SOURCE_EXTRACTION.json with original/published hashes and table
counts. Tests rotate every expanded table through two complete cycles without
repeated draws, check duplicates and obvious NSFW terms, retain fixed camera
and rigging contracts, and verify the recorded published hash.

The historical golden plan remains unchanged and uses a frozen legacy
vocabulary fixture. A separate golden plan covers the expanded default. Tests
compare structural timing, frame counts, cuts, reference slots and all three
casting policies across four backends and three seeds. These checks preserve
original engine parity while making the deliberate visual vocabulary change
explicit. The full pipeline tests use the expanded default, not a test-only
vocabulary override. No automated test reads the private source file or uses
real models or paid/GPU generation.

## Historical 1.0.12 reviewed integration

All **65 tests passed**, plus eight subtests, in **23.74 seconds** using four
workers on the Linux development environment. Both cached Chromium tests ran.
JavaScript/shell syntax, Python compilation and whitespace checks passed, and a
1.0.12 wheel built successfully. Fresh version imports and the live temporary
agent/browser test app reported 1.0.12. The original bundled workflow, vocabulary
and golden plan were also checked byte for byte against the published baseline.
User services were not restarted; no real model switching or GPU work was run.

The default pytest configuration uses four workers. During fork review, the same
58 tests passed in 68.86 seconds with unittest and 23.18 seconds with four-worker
pytest on this Linux environment. Timing depends on hardware and installed test
extras; use `-n 0` when serial execution is preferred.

Regression coverage checks active custom workflow/model preservation, immutable
source graphs and maps, custom loader IDs, precision preservation, newly selected
map paths, discovery fallback per model category, rejection of unavailable and
ambiguous models, and bounded Windows permission-error retries. Cached Chromium
checks installed model dropdowns, file/folder browsing, OAP guide tabs, actual
signed package metadata, escaped display text, explicit signer trust and mobile
layout. Existing SDK recovery, assembly, agent/MCP, OAP and golden-plan checks
remain in the suite. All media/services are synthetic; no paid/GPU/Topaz work is
performed by these tests.

## 1.0.11 Comfy SDK verification

All **56 tests passed** on the Linux development environment, including the
cached Chromium browser flow and real SDK-to-proxy transport test. JavaScript
syntax, shell syntax, Python compilation and `git diff --check` passed. A
1.0.11 wheel built successfully; its contents include the adapter and pinned
SDK/proxy extra, with no handoff draft or credentials. A freshly imported
version handler and the live temporary test app both reported 1.0.11. Existing
long-running user services were not restarted as part of these checks.

The new path is tested with the pinned official Python SDK against a mock v2
service and with the actual pinned official proxy against a synthetic native
ComfyUI server. Coverage includes asset transfer and loader substitution, a
frame-exact assembled music video, receipt recovery without writer or generation
resubmission, lost submission responses, no hidden 429 retry, per-job
cancellation, OAP rejection before uploads, settings invalidation and token
redaction. A browser test covers renderer selection, preview/consent, recovery
and playback when cached Chromium and Playwright are installed.

Reproduction instructions are in [COMFY_SDK.md](COMFY_SDK.md). The real GPU
operator check below was later completed.

### Real GPU operator check — October 18, 2026

The owner authorized a short end-to-end production through `comfy_sdk_h3` on
the development machine: an RTX 4090 (24 GB), ComfyUI 0.41.0 at commit
`c06bf5f`, and the pinned SDK (`6d2dd72`) and proxy (`1569dc1`) installed with the
`comfy` extra. The proxy ran on loopback port 8189 in front of ComfyUI on 8188.
The writer was the local llama.cpp service and Laya ran on CUDA. The quote was
$0.00 (`paid: false`) and consent was recorded before start.

The 11.5-second, 99 BPM test song cast two public starter actors (Robotic Woman,
then Hambo, section casting) at 736×416 (0.3 MP). Both passages passed Laya on
the first review. Each passage's `comfy-request.json` recorded
`backend: comfy_sdk_h3`, the loopback endpoint, SDK revision `6d2dd72`, state
`succeeded` and a distinct proxy job ID. Passage 1 (73 frames) rendered in about
17 minutes including model load; passage 2 (226 frames) took about 5 minutes.
The assembly report shows both clips returned exactly the requested frames
(delta 0) and were trimmed to 61 and 215 frames. The output is H.264/AAC,
24 fps, 276 frames, exactly 11.5 seconds. The score view showed all seven
planned cuts on beats, three on downbeats.

The transport, receipts, timing and assembly worked, but the owner judged the
creative result a failure: passage 1 is effectively a still image. Its mean
frame-to-frame luminance change was 0.05 (0-255 scale, 184×104 grayscale),
against 1.25 for the same quiet passage in an earlier run with a slow push-in and
about 10 for both peak passages. The plan specified "The camera holds a static
shot"; the writer then dropped the planned motion cue and described a
motionless subject and static composition, and Laya accepted it. MMV checked
only frame counts, so the frozen clip was assembled. The passage also rendered
the sampled footage cue "Amateur cine-club footage" as a projected film frame
with a white surround. Passage 2 showed the intended single-subject
fragmentation. SDK execution on real GPU is verified for this environment;
other GPUs, operating systems and ComfyUI or node versions are not. A
motion-quality safeguard is proposed separately.

## Original-engine parity

On the development machine, the original and extracted analyzers processed the
same generated 40-second click track and returned exactly equal scores: 80 beats
and 20 downbeats. Twelve planner/casting/writer-job comparisons matched exactly
across four renderer backends and three seeds. The repository includes portable
score/plan golden fixtures, not private media or actors.

The source extraction manifest records source hashes and adaptations. One
planner correction handles hosted adapters that raise on oversized durations:
the existing phrase-shrinking loop now shrinks those phrases along the same
musical edges. Golden parity is checked on inputs within the original contract.

## Historical 1.0.10 integration checks

All 45 automated tests passed. The integration suite covers
matching-instruction prompt recovery and public
actor descriptions reaching the writer. The original bundled H3 workflow is
retained byte for byte. JavaScript and shell syntax checks passed.
Windows launch, real GPU generation and browser interaction have not been
reverified for this integration.

## Historical 1.0.0 release checks

All 37 automated checks passed. Headless Chromium passed the complete upload,
analysis preview, production and playback-metadata flow at desktop and mobile
widths, including absence of manual timing controls and no mobile overflow.

A separate real local GPU production used the supplied 11.52-second song at
0.3 MP: 736 × 416, 19 detected beats, 5 downbeats, 2 sections and 9 planned shots.
The local LLM wrote the prompts, GPU Laya reviewed them (including a corrective
writer pass), and the standard H3 workflow rendered both passages. The original
assembler produced 276 frames at 24 fps, an 11.5-second H.264/AAC video. Full
FFmpeg decoding passed. No API generation credits were used. The test media,
model files and private run records are not distributed with the source.

The installed release environment was checked independently with Torch 2.14.1,
Transformers 5.20.0 and GPU Laya: the saved production prompt passed review on
CUDA in 492 ms after model loading. The live app version was verified as 1.0.0.

## External systems

GPU Laya inference and the real local song-to-video workflow are checked
separately from the automated mocks. Paid-provider service availability, model
quality and spelling in generated idents depend on the selected models/services.
Hosted adapter tests do not spend API credits. Topaz tests verify invocation;
they do not establish compatibility with every Topaz installation.

See PLATFORMS.md for the OS coverage. No test on one machine establishes that
all GPU drivers, custom-node versions, model files or operating systems work.

## Fork integration 1.6.4 (2026-10-18)

Full suite with mock services only: 253 passed, 53 subtests, no skips (52 s), run in
an isolated worktree and again in the main checkout. New browser regression test
for the vocabulary editor fails on the fork's original code and passes after the fix.
Not verified: a real GPU vision run with the downscaled frames, and the live app
version (no running process was checked or restarted).

## Compact vs full settings, real GPU comparison (2026-10-18)

Local $0 runs through the SDK renderer (quote $0.00), app 1.6.4 from the working
tree, 0.3 MP (736x416), 11.52 s song, actors `animal_pig` (Hambo) and `henchman_1`,
seed 23, vision check on, prompt reuse off. Run A `bee81610` full prompts, 610 s,
no warnings. Run B `8e65be28` `compact_prompts`, 638 s, one warning (passage 2:
unrequested framing device, letterboxing). One run each; the writer samples at
temperature 0.7, so writing differences (B's passage 2 prompt was 7,786 chars
against A's 5,219) are not attributable to compact mode.

For video, the writer system prompt was identical (14,983 chars) and the saved
jobs identical; compact changes only the job message format. Ident trimming was
not part of this run.

Isolated vision test on the same four clips, full size against 512 px, same model,
temperature 0: seven of eight clip verdicts matched. B passage 2 passed at full
size and warned at 512 px because one frame of eight (186, a dark-edged studio set)
was judged bordered; two such frames are needed for a retry. Judging took about
15 s per clip either way (about 1.5 s faster at 512 px). Frames were 40% smaller
in bytes. A single frame decides nothing about overall accuracy; seeded runs on
more clips, including ones with real letterboxing, are still needed.
Not tested: ident runs, other renderers, the Windows launcher flag.

### Correction and rerun with silent mouths active (2026-10-18)

The first A/B pair above (`bee81610`, `8e65be28`) used `lyrics: ""`. The lyrics-gated
rule in `worker.py` therefore turned silent mouths off in both: the writer was told
to describe lip, teeth and tongue articulation and no rigging tail was required, and
run B's prompts contained mouth-talking phrases. That pair does not test the
sealed-lips scheme. The rule now follows the `silent_mouths` setting (default on)
whatever the lyrics; the scheme's wording, tail and validators are unchanged.

Rerun, same song, actors, seed, 0.3 MP, vision check on, prompt reuse off, $0 local:
A `a85ac154` full prompts (632 s) and B `060525c1` compact prompts (652 s). Both:
silent-mouths rule in the writer system prompt, natural rule absent, the rigging tail
present in every shot (1 of 1 and 8 of 8), no mouth-articulation phrases in any
prompt, pixel and vision checks passing with no retries, no warnings. Contact sheets
show closed mouths in sampled frames. Stills cannot show lip motion; motion was not
reviewed frame by frame. A first attempt (`78d85b3e`) failed with a ReadTimeout while
ComfyUI staged a model for passage 2 (cause unknown, RAM fine); one fresh retry
succeeded. One run per setting, so compact versus full is still not statistically
compared, and the vision comparison at 512 px above stands as the only direct test.

## Lip-sync (HONK) real GPU run, 2026-10-19

Operator-authorised free local run through the Comfy SDK path (proxy 8189, ComfyUI 8188 started by the operator because the
vision check was off): run `f72cf0421eb24ff3a8f4af7b1030a053`, "halp fren" (57.3 s), 0.3 MP (736x416, 24 fps), seed 1, actors
`henchman_1` (singer), `human_female_casual_01`, `animal_pig`, `mouth_mode: lip_sync`, 13 lyric lines (Suno format, aligned from the
detected words on the vocals stem). Result: 6 passages, 5 sung (the 1.6 s outro stays sealed); every passage passed the pixel checks
on the first render, no quality warnings; 33 min 58 s in total (prompts were validated in an earlier attempt of the same inputs and
resumed after ComfyUI had not been started; see below). Earlier attempts failed in the prompt-writing phase before any rendering:
the singing check rejected valid prompts because actors appear as `<Subject N>` in shots (not picture tags), quoted lyrics were split at
punctuation, pronoun-led sentences were not credited, and bystander "lips part" was missed; each was fixed with a regression test built
from the real writer output. A render attempt also failed once with "Failed to reach ComfyUI" because the SDK path expects ComfyUI to be
running when the vision check is off. NOT established: lip-sync accuracy (needs the owner's viewing), repeatability across seeds, and
studio-quality clips (separate feature).
