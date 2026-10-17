# Releases

## 1.0.16 — Resizable cast list

The music-video cast list can be resized vertically using its lower-right
handle, making larger rosters easier to browse. Its width follows the form,
and existing selections and multiple-selection controls remain intact.

## Optional starter cast — asset addition

Four owner-authorized actors are available in `examples/starter-cast` as signed
OAP packages: `animal_pig`, `robobabe1`, `henchman_1` and
`human_female_casual_01`. Import instructions and SHA-256 hashes accompany them.
All other roster actors remain private and ignored. Application behavior and
version remain 1.0.15; this adds optional assets and documentation only.

## 1.0.15 — Dark mode by default

The studio opens in dark mode, including forms, dialogs, file browsing and OAP
reports. A header toggle switches to light mode; the browser remembers the choice
and applies it before the page paints. Theme switching works even when browser
storage is unavailable.

## 1.0.14 — Actor card overviews

Actor cards show only the Identity section when a description includes structured
visual details. Full actor descriptions remain available for generation and OAP
export. Plain descriptions continue to display normally.

## 1.0.13 — Expanded SFW vocabulary and contributor thanks

Imports the owner-authorized vocabulary data into the public music-video pool,
with suggestive entries and incompatible mouth actions removed. Includes 269
settings, 233 subjects, 256 mechanisms, 227 lighting choices, 185 tones, 111
practical effects, 70 footage anchors and 31 costumes. Deduplicates tonal entries
and retains the existing camera bands, shot scales and mouth-rigging contract.
No private studio code, models, actors or runtime imports are added. The source
extraction manifest records authorization, source/published hashes and counts.

The original sampler, planner and casting code remain unchanged. The historical
golden plan is preserved with a frozen legacy vocabulary fixture, alongside a
new expanded-vocabulary golden plan. Cross-backend/seed checks verify unchanged
timing and actor assignments. Adds a README thank-you to hellonearthis.

## 1.0.12 — Reviewed model controls and setup guidance

Integrates selected improvements from hellonearthis through `c1db1c6`: installed
H3 model dropdowns, local path browsing, OAP help/inspection cards, Windows JSON
read lock retries, and four-worker testing with pytest-xdist.

Model changes now derive private copies of the active workflow and injection map,
preserving custom nodes, loader IDs and precision settings. Unchanged selections
do not override a newly chosen workflow. Ambiguous loaders and unavailable models
are rejected. OAP summaries use the upstream display name, signing public key,
content ratings and actual commercial rider without inferring permission.

The original model defaults, workflow, vocabulary and golden plan remain intact.
The expanded vocabulary and its direction guide are excluded from this delivery.

## 1.0.11 — Official Comfy SDK H3 rendering

Adds an opt-in `comfy_sdk_h3` renderer using the official Python SDK and a
loopback Comfy API v2 proxy. Reuses the original H3 workflow, planning lattice,
reference ordering, Laya review and frame-exact assembly. Assets transfer through
the SDK; no shared input/output folders are needed. Submissions are sent once,
with receipts persisted before dispatch. Known jobs and failed downloads can
resume through a new preview and consent step without rerunning the writer or
resubmitting existing generations. Unknown outcomes and failed/canceled/expired
jobs require operator reconciliation. Adds setup, UI, CLI and MCP integration
and a reproducible operator procedure in [COMFY_SDK.md](COMFY_SDK.md).

The direct local renderer remains the default. Real GPU verification through
the proxy remains outstanding.

## 1.0.10 — Reviewed integration

Integrates the fork’s draft persistence, diagnostics, Windows launcher, prompt
reuse, cache clearing and seed controls while retaining the original H3 workflow.
Restores the public actor metadata adapter. Passage reuse now requires matching
system instructions and job data; only saved validated prompts are recovered.
A new cache namespace avoids reusing entries created by the earlier fallback.

## 1.0.9 — Prompt cache clearing & variation seed reroll

- **Clear prompt cache**: Added `POST /api/cache/clear` endpoint and a `#clear-cache` button in the UI under *Timing, credits & content*, allowing instant deletion of cached passage and ident prompts and recording `cache_cleared.json` so previous runs are not picked up on subsequent generations.
- **Reroll variation seed**: Added a `🎲 Reroll seed` button (`#reroll-seed`) next to the variation seed input to quickly generate a new random seed, rerolling shot cut points, grammars, and camera movement.
- **Cache invalidation integration**: `find_cached_passage_prompt` now respects `cache_cleared.json` timestamps, ensuring runs after a cache clear always regenerate cleanly with new settings.

## 1.0.8 — Instrumental track lip-sync suppression & rigging auto-injection

- **Instrumental tracks / no lyrics**: When no lyrics are provided in the production request, lip-sync suppression is automatically disabled so prompt validation does not fail with "Subject Rigging block is missing (lip-sync suppression)".
- **Rigging tail auto-injection**: When lyrics are present and silent mouths is enabled, any missing boilerplate rigging tail is automatically injected into the detailed description before validation, preventing writer omissions from failing the run.
- **UI clarifications**: Updated the facial movement settings description to make clear that lip-sync suppression is applied when lyrics are present and skipped on instrumental tracks.

## 1.0.7 — Passage prompt caching, progressive saving & production resumption

Introduces progressive prompt disk persistence and persistent hash-keyed passage caching
in `store.home / 'cache' / 'prompts'`. When a production is restarted or resumed, completed
and Laya-validated passage prompts are retrieved instantly without re-invoking the writer
LLM or prompt reviewer. Recovers completed segments across prior interrupted runs and adds a
"Reuse validated passage prompts" UI toggle to force full regeneration when desired.

## 1.0.6 — User-friendly upload validation & contextual studio error logs

Enhances input validation in `mmv/pipeline.py` to check for missing audio files, invalid
reference image paths, harvest references, and ident paths prior to directory traversal,
replacing cryptic sandbox errors ("Path is outside its data directory") with clear,
actionable messages ("Upload a song first"). Enriches studio event logs with production
kind context (`Preview failed (video)`, `Start preparation failed (video)`).

## 1.0.5 — One-click operation log clearing & suppression

Adds a dedicated "Clear log" button (`#clear-log`) to the studio header alongside
"View log" and "Copy log", resetting the live diagnostic log display, clearing client
session records, wiping `studio.log`, and suppressing historical runs prior to the clear
timestamp (`POST /api/log/clear`).

## 1.0.4 — Windows start script with llama.cpp model selector

Introduces `start.ps1`, an all-in-one PowerShell starter for Windows that automatically
discovers local GGUF models in `C:\llamaCPP\models`, pairs multimodal vision projectors (`mmproj`),
configures the local writer service in Mondo's settings, manages or verifies `llama-server.exe`,
and launches the studio server with automatic browser navigation.

## 1.0.3 — One-click operation log clipboard export

Adds a dedicated "Copy log" button (`#copy-log`) to the studio header next to the log viewer,
allowing operators to copy the full combined diagnostic output (client session notices,
background worker tracebacks, Laya validation reports, writer service output, and server
event logs) to their system clipboard with one click.

## 1.0.2 — Diagnostic operational logs & CSP inline script compatibility

Resolves browser extension inline script blocks by relaxing Content-Security-Policy
script/style directives, expands the `#show-log` diagnostic viewer with unified client session
activity and server event logging (`studio.log`), surfaces validation and writer errors
directly in the UI log pane, and keeps the log toggle accessible at all times.

## 1.0.1 — Project reload persistence, comprehensive UI tooltips & Windows UTF-8 fix

Adds automatic current project draft persistence across page reloads (persisting active
panel, form fields, details expansion, log visibility, and uploaded song/references via
`/api/project` and `localStorage`), accessible WCAG 1.4.13-compliant studio tooltips for
all interface controls, and UTF-8 process encoding for Windows background jobs.

## 1.0.0 — Mondo Music Video

Complete song-to-video workflow with automatic beat/downbeat, energy and section
analysis, seeded musical montage planning, the Mondo LLM writer, GPU Laya prompt
review, standard local H3 and hosted renderer adapters, frame-exact assembly,
OAP actors, styles/harvest, credits/idents and optional Topaz export. Includes
portable setup, verified opt-in Laya downloads, agent CLI, MCP server and skill.


## 0.1.1 — agent operation and first public GitHub release

Optional local stdio MCP server, a bundled Mondo Music Video agent skill, and a
JSON CLI helper. Agent calls use the same preview/consent, single-operation and
OAP paths as the browser. Local-only endpoints, no submission retries, and no
credential-writing or arbitrary shell tools in the MCP server.

The application remains a development preview with the external verification
limits recorded below. Public source includes no models, actors, credentials or
private studio history.

## 0.1.0 — initial development preview

Independent public application with music-video production, automatic final
assembly, reference-image actors and built-in OAP, styles/style harvesting,
credits/idents, output playback/download and optional direct Topaz export.

One active operation, explicit previews/consent, local/API renderer adapters,
platform setup launchers, system doctor and opt-in verified model-download helper.
No private studio implementation, models, actors or production data are bundled.

This is a development preview. See VERIFICATION.md and PLATFORMS.md for the
automated checks and external/platform checks still outstanding.
