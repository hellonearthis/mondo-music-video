# Verification — 1.1.3

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

No real GPU or paid production has been run for this path. The operator check
and reproduction instructions are in [COMFY_SDK.md](COMFY_SDK.md). Real GPU execution remains unverified.

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
