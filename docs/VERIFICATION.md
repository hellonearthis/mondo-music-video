# Verification — 1.0.18

## 1.0.18 Live Engine & Hardware Status Monitor (Laya, llama.cpp, ComfyUI, Vision)

- Verified live engine status reporting for Laya, llama.cpp, ComfyUI, and Vision via `/api/services/status`.
- Verified state differentiation: actively processing vs. sleeping (ready/idle standby) vs. offline/unconfigured.
- Verified service dock UI elements, pulse dot animations, and responsive layout across desktop and mobile viewports.
- Verified version `1.0.18` across `webapp/mondo_web.py`, `pyproject.toml`, `README.md`, CLI, MCP, and live `/api/version`.

## 1.0.17 Integration of upstream features (starter cast, dark mode, resizable cast list)

- Verified four signed starter actor OAP packages in `examples/starter-cast` with checksums and manifest.
- Verified default dark mode styling and theme toggle persistence.
- Verified resizable cast list styling and browser interaction.
- Verified service error reporting and diagnostic identification for ComfyUI, llama.cpp, Vision, and Laya.
- Verified version `1.0.17` across `webapp/mondo_web.py`, `pyproject.toml`, `README.md`, CLI, MCP, and live `/api/version`.

## 1.0.16 (Upstream) resizable cast selector

Both existing Chromium flows and the version consistency test passed. A separate browser check with the 85-actor local roster dragged the list, retained the selected actor, and confirmed no page overflow at a 360px viewport. Fresh handler import and live `/api/version` both reported 1.0.16.

## Optional starter cast publication

Verified exactly four signed OAP archives against their allowlist and SHA-256 manifest (`animal_pig.oap`, `henchman_1.oap`, `human_female_casual_01.oap`, `robobabe1.oap`). Each contains only `manifest.json` and `identity/reference.png`. All four imported into a temporary empty roster, retained their visual descriptions, and passed casting checks.

## 1.0.15 (Upstream) default dark theme

Verified default dark rendering, switching to light, preference persistence across reloads in both directions, and a visible toggle without page overflow at 360px. Desktop and mobile previews were visually inspected.

## 1.0.14 (Upstream) actor card overviews

All 68 tests and 28 subtests passed in 25.87 seconds, including existing Chromium flows. The display helper was checked against all 85 local actors: each returned its Identity overview, without Hair or later sections; plain descriptions remained intact. Full stored descriptions were unchanged.

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

## 1.0.16 Service error reporting & diagnostic service identification

- Verified `identify_service` correctly identifies ComfyUI, llama.cpp (Writer), Vision, and Laya from URLs, logs, and command configurations.
- Verified `start_service` error messages explicitly state the failing service name (e.g. `ComfyUI service is not running`), health URL, and the corresponding configuration key (`comfy_launch` or `writer_launch`).
- Verified `Jobs.command` extracts and surfaces the underlying process failure detail in the operation status message.
- Verified `/api/log/{run_id}` output includes `comfy-service.log` when present alongside `writer-service.log`.
- Verified version `1.0.16` across `webapp/mondo_web.py`, `pyproject.toml`, `README.md`, CLI, MCP, and live `/api/version`.

## 1.0.15 Laya CPU fallback, device settings dropdown & llama.cpp token buffer guide

- Verified automatic fallback from `cuda` and `mps` to `cpu` when PyTorch does not have CUDA/MPS support compiled or available.
- Verified `laya_device` select dropdown in `webapp/app.js` with options for `cpu`, `cuda`, and `mps`.
- Verified `start.ps1` with `-ContextSize` parameter, `--image-min-tokens 1024`, `-b 2048 -ub 1024`, and proper stdin piping for `writer_launch` JSON quoting.
- Verified `#llama-helper-dialog` modal in `webapp/index.html` and `webapp/app.js` with launch JSON copying and "Apply to Writer Launch" action.
- Verified `tests/test_original_engine.py` unit test coverage for device fallback.
- Verified version `1.0.15` across `webapp/mondo_web.py`, `pyproject.toml`, `README.md`, CLI, MCP, and live `/api/version`.

## 1.0.14 song preview player & studio direction guide

- Verified `.song-preview-wrap` and `.song-preview` `<audio>` player element in `webapp/index.html` and `webapp/style.css`.
- Verified `GET /api/uploads/song/{filename}` audio streaming with path-traversal protection.
- Verified version `1.0.14` across `webapp/mondo_web.py`, `pyproject.toml`, `README.md`, CLI, MCP, and live `/api/version`.

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
