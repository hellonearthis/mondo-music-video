# Releases

## 1.8.9 — Fix operation log clearing and active session log reset

- Resolved an issue where clicking "Clear log" failed to clear the diagnostic log view:
  - Corrected `active_id` detection in `GET /api/log/{run_id}` to only treat actively running or cancelling operations as active, properly honoring `cleared_at` timestamps for historical runs.
  - Implemented active run log offset tracking in `POST /api/log/clear`, ensuring that clearing the log during an active production resets the view and only displays lines generated after the clear action.
  - Fixed client-side notice feedback in `webapp/js/core.js` and `webapp/js/production.js` so "Diagnostic log cleared" flashes without inserting a notice record back into the newly cleared session log array or triggering a premature redraw.
  - Reset `state.currentRun` to `null` on clear log click to prevent immediate refetching of completed or interrupted runs.
- Bumped application version to `1.8.9`.

## 1.8.8 — Style export, import, duplication and validation

- Full portability for harvested and custom visual styles: download style cards as clean JSON and import styles into any Mondo Music Video studio library.
- Four-layer import validation:
  1. Strict structural schema checking via Pydantic `StrictModel` (`StyleImportRequest`) rejecting unknown keys.
  2. ID and path sanitization via regex `^[a-z0-9][a-z0-9_-]{0,63}$` preventing path traversal.
  3. Collision protection: rejects existing style IDs by default unless explicit `overwrite=true` is set.
  4. Content and boundary constraints: non-empty directions (up to 8,000 chars), display name bounds (up to 160 chars), and preservation of 11-axis forensic breakdown cards (`style_card` up to 16,000 chars).
- Visual Styles UI additions:
  - Download JSON and Duplicate action buttons on every style card.
  - Collapsible 11-Axis Forensic Card preview on styles harvested with the Multimodal Vision agent.
  - Dedicated Import Style JSON card with file picker and overwrite checkbox.
- Agent client and MCP tools extended:
  - Added `export_style` and `import_style` methods to `AgentClient`, along with `export-style` and `import-style` CLI subcommands.
  - Added `export_style` and `import_style` tools to the MCP server (bringing the suite to 35 tools).

## 1.8.7 — Fix LocalH3 backend timeout evaluation

- Fixed a `TypeError: '>' not supported between instances of 'float' and 'NoneType'` bug during segment rendering with the `local_h3` backend when `timeout_s` is omitted or `None`.
- Ensured `LocalH3Backend` and `mmv/worker.py` default `timeout_s` safely to `7200.0` seconds instead of passing `None` to `ComfyClient.wait()`.
- Added regression test `test_local_h3_timeout_none_defaults_to_float` verifying safe float default evaluation.

## 1.8.6 — Service probing concurrency & functional component optimizations

- Parallelized service health checking in `mmv/services.py` across ComfyUI, Writer, and Multimodal Vision using concurrent thread pools, cutting probe latency by up to 65%.
- Implemented state memoization in `webapp/js/production.js` to skip redundant DOM repaints during SSE status polling.
- Refactored filesystem picker in `webapp/js/settings.js` to use pure template rendering (`pickerEntryHtml`) and delegated event handlers.
- Decoupled tooltip geometry calculations into pure `computeTooltipPosition` in `webapp/js/tooltips.js` and eliminated attribute thrashing.
- Extracted pure CLI flag parsing and tuning transformer `tuneLlamaCommand` in `webapp/js/guides.js`.

## 1.8.5 — Collaborator integration: upstream 1.8.2 review fixes

- Integrates hodgemann's upstream release 1.8.2 improvements: restores the vocabulary guide dialog (`#vocab-helper-dialog`) connected to the sidebar workspace, restores category-specific accessible names for overflow actions, dark-mode overflow button hover contrast, independent fold persistence (`details_sections`), and updated browser test coverage.
- Maintains full compatibility with 1.8.4 offline engine guards and 1.8.3 functional architecture.

## 1.8.4 — Required engine offline protection & operator warnings

- Pre-flight engine availability checks in `POST /api/quote` and `POST /api/start`: halts production and warns the operator with actionable instructions when Prompt Writer (`llama.cpp`), Video Renderer (`ComfyUI`), Reviewer (`Laya`), or Multimodal (`Vision`) is offline and has no launch command configured.
- UI service alert banners, disabled consent and start controls, and pulsing status card indicators on offline failure.

## 1.8.3 — Functional UI refactoring & incomplete runs manager

- Refactored `vocabulary.js`, `library.js`, and `outputs.js` into modular functional template engines.
- Added incomplete runs management table with resume/clean controls and confirmation modal for video deletion.


## 1.8.2 — Vocabulary guide and accessibility review fixes

- Addresses Antigravity’s UI review: restores the missing vocabulary guide dialog and connects its navigation to the workspace.
- Gives overflow buttons readable dark-mode hover colors and category-specific accessible names; explains when unapplied workspace edits are discarded.
- Protected prompts and generation defaults are unchanged. Both Claude Code and Antigravity reviews are received and triaged in the [review record](COLLABORATOR_REVIEW.md).

## 1.8.1 — Vocabulary workspace and faster editing

- Integrates hellonearthis’s fork contributions through `1704454`: a dedicated Visual vocabulary workspace, updates limited to the edited summary card, and bounded summary chips with access to the full category.
- Groups advanced production controls into pacing, camera and render folds, each remembering its open state. Existing generation defaults are preserved.
- Fixes workspace navigation recursion and restores saved vocabulary before opening the workspace. Updates browser regression coverage and navigation labels.
- Windows launcher uses Python UTF-8 mode; protected prompts and fingerprints are unchanged. See [integration review](COLLABORATOR_REVIEW.md).

## 1.8.0 — BONK: dancing actors

- **Dance mode** (opt-in `dance_mode: group`, off by default; music videos): the cast dances in time with the song. The app reads the song's
  tempo and beats and tells the writer, per shot, how many beats it holds and where the downbeat falls; intensity comes from the song's
  energy (calm, medium, high). Up to three dancers per passage, chosen from whoever is cast there; an optional lead is followed by the
  others and is ignored in shots where the lead is off screen. Deliberate stillness, held poses and slowed movement are welcome
  choreography. The direction field (`dance_direction`) chooses the style of movement only.
- **Singing and dancing together**: a singer can also dance. Everyone who is not singing stays sealed while dancing; dancing never
  changes a mouth rule. Verified on real renders (a singing henchman with a dancing robot and pig, sealed).
- Dance planning is made once at preview and replayed on resume (a versioned, digest-bound plan, with the prompts bound to it), so a
  resumed production keeps the same choreography. A bounded wording check rejects prompts that leave a visible dancer without a body
  action or describe one as merely standing; style advice (follow the lead, downbeat accent, calm wording) is kept on the last try and
  recorded in `dance-advice-kept.json` instead of failing the run. The sealed-lips sentences are never treated as dancing.
- **Local renders are no longer limited by a one-hour wait**, and one status check that times out while a render is still running no
  longer ends the production (the render was already submitted; a hung proxy is retried, never resubmitted).
- Preview, API, agent client, MCP tools, skill and export package (`passage-plan-prompts.json` receipt, dance line in the README) cover it.
- Work shared with Codex, which built the passage-plan binding and resume prerequisites and adversarially reviewed the design and
  integration. Requests that do not use dancing produce byte-identical prompts, job files and fingerprints to 1.7.2 (golden fixtures).
- **Exceptions to the protected prompting scheme:** the writer, ident and sealed-lips text, the singing wording and the quality rules
  are unchanged. The owner-approved dance rules are an extra block appended outside the original engine, as the singing rules are.

## 1.7.2 — Subliminal message mode and sturdier Suno lyric parsing

- **Subliminal message mode** (opt-in, off by default; music videos): flash a chosen picture, or a few words rendered full-frame, for 1 to 12
  frames at times you give or spread over the song's downbeats. Applied after assembly with FFmpeg, outside the engine: frame count,
  duration and audio (copied, never re-encoded) are unchanged, and the untouched video is kept as `music-video-clean.mp4`. Photosensitivity
  guards: flashes are at least a second apart and stay clear of the first and last second. The quote shows the planned times; a failed flash
  leaves the finished video exactly as it was and records a warning. The export package notes it. Available in the app, API, agent client and
  MCP tools.
- **Suno lyric parsing and timing hardened** after an adversarial review: stray words heard far away no longer stretch a line across the song,
  lines never heard are placed in the gap beside the singing instead of at zero, curly apostrophes, accents and other scripts match, stage
  directions such as `[laughs]` are ignored, several markers on one line combine, `(x2)` and `(Chorus)` are ignored, real short shouts are
  kept while recognizer blips are dropped, and input sizes are capped. Regression tests cover each case.
- The prompting scheme, writer, ident and singing wording are unchanged.

## 1.7.1 — Studio-quality clips, prompting-scheme protection, rented-GPU guide

- **Studio-quality raw clips** (opt-in `clip_quality`: `standard` default, `prores`, `lossless`; Comfy SDK renderer, music videos only). The
  SDK path used to keep ComfyUI's built-in SaveVideo output (ordinary H.264, about 1.4 Mbps for a 736x416 clip) and the final video was
  rebuilt from it. Studio mode switches the workflow's VideoHelperSuite save node to ProRes 4444 (near-lossless, editor-friendly) or FFV1
  (mathematically lossless) with the audio inside, and takes that file as the passage clip; the final video is still encoded from it by
  ffmpeg at assembly. Files are much larger, so it is off by default. Clips are now named by what they really are (`video.mov`,
  `video.mkv`, `audio.flac`): the renderer's audio used to be FLAC data under a `.wav` name that many editors cannot open. If the job does
  not return the studio file, the standard clip is used and the run records a note. The shipped workflow and engine are unchanged.
- **Export package for editors**: raw clips keep their real extension; ProRes and FFV1 clips also get exact-length `_studio_trimmed` copies
  cut without re-encoding, and the timeline (`.edl`) points at them; audio files are true PCM WAV; the README has a media-format guide and
  says whether the prompting scheme is unmodified. Folders are named by title and date-time.
- **Prompting-scheme protection** (`docs/PROMPT_SCHEME_PROTECTION.md`): the writer and ident prompts, the sealed-lips scheme, the schema,
  validators, plan code, the singing wording and the quality rules are pinned in `mmv/protected_scheme.py` (line endings ignored). A fork
  that changes them sees an orange banner in the app (`GET /api/integrity`), exports say so, tests fail with a message that tells an agent
  to warn the person in plain words, offer an opt-in alternative and never edit the pins; `AGENTS.md`, `mmv/engine/PROTECTED.md`, the
  skill and `.github/CODEOWNERS` carry the same rule. `tools/update_protected_pins.py` refuses to run without an explicit owner flag.
- **Install guides**: `docs/GPU_CLOUD.md` for other rented GPU hosts (Vast.ai, Lambda, TensorDock, Paperspace, the big clouds), derived from
  the RunPod guide and reviewed by Codex; **not tested on any of them**. `PLATFORMS.md` refreshed. A rule that internal lab names are
  never published.

## 1.7.0 — Lip-sync mode and optional lyrics detection

Designed with Codex (read-only design review, `docs/LIPSYNC_DESIGN.md`). The owner approved the direction.

- **Third Facial movement mode, "Lip sync to vocals"** (`mouth_mode`: `sealed` default, `natural`,
  `lip_sync`; the old `silent_mouths` flag still works). Every passage stays sealed (rule, rigging tail
  and validators unchanged) except those whose audible slice carries about 0.75 s or more of sung lyric
  lines. Singing passages use a second prompt set: the natural-mouths system text, a new `SINGING_RULES`
  block, a cast block without sealed-lips rules, the singer's `lines` in the job, no rigging tail, the
  singer's picture tag and quoted words required in the shots that overlap singing (a deterministic
  shot-level check, since Laya has no singing question), and the audio sentence replaced outside the
  engine. Everything is outside `mmv/engine/`. The singing wording was approved by the owner.
- **Lyrics and singing in the score editor**: editable lyric lines with times, a main-singer choice (or a
  seeded pick; only the main singer sings: a passage where they are not on screen, or with no cast,
  stays sealed), and a per-passage summary of who sings. Plans resolve at preview and are stored in
  `prepared.json`, so resume replays them. Cached prompts are not reused for singing passages.
- **Optional lyrics detection** (Whisper, MIT, an optional add-on): detect timed lines from the vocals
  stem (when the stems add-on is ready; on the full mix otherwise), or paste lyrics and have them timed
  against what was heard (matching with uncertainty flags; unmatched lines get guessed times and are
  marked). Reuses an existing Whisper environment (`MMV_LYRICS_PYTHON`) and model files
  (`MMV_WHISPER_DIR`, default `~/.cache/whisper`); nothing installs or downloads without approval. Measured
  with large-v3: about 10.2 GB of VRAM and 46 s on a GPU or 164 s on a CPU for a 60 s clip, so the GPU is
  used only when the model fits in free memory. Smaller models are untested on singing.
- **Suno lyric format**: pasted lyrics may use section markers (`[Verse 1]`, `[Chorus]`, inline `[Chorus] la la`)
  and `(backing vocals)`. Markers never become lines or lower the match; each sung line keeps its section label (shown
  in the editor and passed to the writer), blocks marked instrumental, solo, interlude, break, drop or beat are not
  timed (a voice word such as "Vocal Solo" keeps a block sung), and repeated choruses stay in order. Detection also
  drops hallucinated blips under 0.25 s (Whisper invented "We'll be right back." at the end of a real clip). Tested on
  the owner's 57 s song "halp fren": 12 of 13 lines heard almost word for word, all 13 pasted lines timed.
  Parser written by Codex in a separate worktree and reviewed and merged by Claude Code.
- **Export production package** (owner request for the demo video, owner's friend edits it): an "Export package" button
  on each finished video, `POST /api/outputs/{run}/package` and the `export_production_package` tool copy the production
  into `MMV_HOME/exports/<title>_<date>_<time>/` (plus a zip; for example `halp_fren_lip_sync_test_2026-10-19_0409`): the finished video, every raw per-passage clip, the song, one prompt file
  per passage, the receipts (request, consent, render request IDs, quality and vision checks, plan, score, casting, logs),
  one still per passage, a README with a per-passage table (who sings, lyric lines used) and a checksum manifest. Keys and
  secrets are never copied (the stored keys are also redacted by value), home paths are shortened, only the four public
  starter actors' reference pictures are included, and a run with other actors needs an explicit confirmation and carries a
  warning not to publish it. Pure file copying; a first version written by a Claude helper and adapted by Claude Code.
- **Agents**: `detect_lyrics` and `align_lyrics` tools (32 tools; 33 with the package export below), `inspect_studio` kind `lyrics` (status,
  hardware, recommendation), and `mouth_mode`, `lyric_lines` and `singers` on `preview_production`.
- **Verified once on real H3 output** (operator GPU run, 2026-10-19): the owner's 57 s song "halp fren" at 0.3 MP with three public
  starter actors, Henchman #1 as singer and 13 lyric lines in Suno format. All six passages validated, rendered and passed the
  automatic motion/framing checks on the first render with no warnings (34 min including writing prompts); frames show the singer
  with his mouth open in the sung close-ups. Whether the lip movement matches the words is the owner's judgement from watching the
  video; stills cannot show it. It took four prompt-writer attempts per passage under the singing check. Backup singers are pinned on the roadmap.

## 1.6.14 — Stem quality option and hardware-aware agent guidance

- **Stem quality** (`stem_quality`: `standard` default, or `high`): high uses the fine-tuned
  Demucs model (`htdemucs_ft`, about 324 MB, 2 to 3 times slower). On the owner's songs it left far
  less stray sound in the vocals stem on one song (2% vs 23% of frames with quiet bleed),
  made no difference on two, and was slightly worse on one, so it is opt-in. The editor offers it
  with its own one-time download approval; guitar and piano always use the 6-stem model, which was
  noisier on vocals and is never used for them. Plans from the two settings were nearly identical
  on the tested song (19 shots each).
- **Hardware-aware recommendation**: `GET /api/stems` (and `inspect_studio` kind `stems`) now
  reports the GPU, free VRAM and RAM, per-model download sizes and a plain-language
  recommendation from measured figures; the editor shows the first line.
- **Agent installation**: the install guide, AGENTS.md, the skill and `AGENT_SETUP.md` now tell
  agents to mention instrument analysis, ask whether the user wants it, recommend a model quality
  for the detected hardware, include the add-on and model sizes in the single download proposal,
  and never install or download without approval.

## 1.6.13 — Stem separation on smaller GPUs

Measured with the real models on a 4-minute track: 4-stem, fine-tuned and 6-stem Demucs models
each need about 1.2 GB of VRAM (they work in chunks) and take 8 to 17 s on a GPU or about 71 s on
CPU (4-stem). Stem separation now uses the GPU when about 3 GB is free (Demucs documents 3 GB as
its minimum; it was 6 GB) and otherwise falls back to CPU. The editor's download approval states
the measured sizes (about 81 MB for the 4-stem model, about 53 MB for the 6-stem model). On real
songs the models agree on drums and bass but differ on vocals, so the default 4-stem model is kept
and the fine-tuned one is not added until listening shows a benefit. The editor test no longer
depends on whether Demucs is installed.

## 1.6.12 — Edit the score before generating, and follow an instrument

"Watch the song conduct" now happens before generation. Idea from a musician friend
of the owner; designed with Codex (read-only design review, `docs/SCORE_EDITOR_DESIGN.md`).

- **Score editor in Preview production**: a waveform (wavesurfer.js 7.10.1, vendored,
  BSD-3-Clause), the detected beat grid, energy curve and planned cuts, playback, and
  edits that cost nothing: shift the grid, choose which beat starts a bar, mute beats
  as cut candidates, and drag, split, merge and relabel sections. Press Re-plan to
  rebuild the cuts and cost; Start production stays disabled while edits are unplanned.
- **`score_edits` request field** (also for agents): applied to a copy of the cached
  analysis between analysis and planning, validated and quantized to frames. The
  original engine sources and the analysis cache are unchanged; edits enter the quote
  fingerprint, `request.json` and the approved `prepared.json` that resume replays.
  Previews now return `score` and `detected` (the unedited analysis), and
  `GET /api/waveform` returns bounded peaks computed with ffmpeg.
- **Instrument driver (optional add-on)**: `analysis_driver` (mix, drums, bass, vocals,
  other, guitar, piano) takes per-beat energy and section ranking from one stem while
  the beat grid stays from the whole mix. It needs the optional Demucs add-on (MIT,
  `pip install demucs`) and a one-time model download that is never automatic: it is
  approved with a checkbox in the editor (`POST /api/stems/prepare`). Separation runs in
  a subprocess, is cached per song and model, uses the GPU only if about 6 GB is free,
  and the stems are analysis input only; the video keeps the original audio.
  `inspect_studio` kind `stems` reports availability.
- **Limits**: the driver changes energy (cut density, camera, scale, montage style), not
  where cuts land; following an off-beat attack would need engine changes. Muted beats
  are not cut candidates but still count in bar counting. Hearing a single stem in the
  editor and a stem waveform are not built yet.
- Defaults unchanged: no edits and driver `mix` plan exactly as before.
- **Review fixes (Codex, read-only)**: edited section boundaries just after a downbeat could
  make the planner silently drop a sliver of the song (shifting picture against music), so
  edited plans must now cover the song contiguously or the preview is rejected with a plain
  message, and the editor snaps section edges to downbeats; beat 0 is now a valid bar-one
  choice; bar phase follows each beat's original index when a nudge drops edge beats. The
  editor also shows the first section at 0 s like the planner. Each has a regression test.

## 1.6.11 — Pseudo-random vocabulary keys

Integrates hellonearthis's fork commit `dc71556` (fork 1.6.11). Credit: hellonearthis.

- **Pseudo-random vocabulary generator**: a `seed:count` key deterministically
  keeps `count` entries per category and excludes the rest; quick bar (roll,
  apply, reroll, save, edit, clear) in the main panel, matching tools in the
  vocabulary dialog, saved keys kept in the browser, and the key stored with the
  project (`vocab_random_key`). Typed custom entries are preserved when a key is
  applied.
- Integration: draft-replacing paths use `showVocabCategory` (the earlier
  stale-text fix) so a replaced draft cannot be overwritten by editor text. The
  largest vocabulary category (269 entries) fits the 500-entry exclude limit. A key
  reproduces the same selection only while the built-in vocabulary lists are
  unchanged.

## 1.6.10 — Collaborator integration, part 2: module split, guide dialog, preview feedback

Integrates hellonearthis's fork changes after `3365943` up to reviewed head
`4e1cbb0` (fork releases 1.6.5 to 1.6.10). This delivery is the single version
bump covering both integration passes (the 1.6.4 notes below are part of it).
Credit: hellonearthis authored the changes below; the integration review fixed
the defects listed.

- **`app.js` split into ES modules** under `webapp/js/` (core, guides, library,
  outputs, production, project, settings, tooltips, vocabulary); the page loads
  `app.js` as a module and the server serves `/js/<module>`. Package data now
  includes `js/*.js`. This repository's two front-end changes (the
  `compact_prompts` request flag and the vocabulary-editor stale-text fix) were
  carried into the modules.
- **Preview/Start feedback**: spinners, busy state and status banners while the
  audio is analysed and the plan is built.
- **Accessibility**: light and dark theme contrast adjustments; sticky sidebar.
- **Vocabulary guide dialog** and `/api/vocabulary/guide`.
- **Local writer hint** when prompt validation fails with a local writer (context
  size `-c` or token limit may be too small).
- **Operation log** is cleared when a production starts; the log view keeps the
  active run.
- Configurable video encoders were added and reverted by the fork; nothing to adopt.
- **Silent mouths (owner decision):** the sealed-lips rule no longer depends on
  lyrics text being empty; it applies to every production unless Natural
  expressions is selected. The planned lyrics and lip-sync mode must switch it off
  itself. The rule text, rigging tail and validators are unchanged.

Integration fixes: the fork's module split broke its own browser tests (they read
module-private state as page globals), so tests now import the modules
(`isSseConnected` and `getSseSource` are exported read-only accessors). Codex found
that reopening a project dropped a saved custom vocabulary preset (the project was
restored before the preset list loaded); the catalog now loads first, with a browser
regression test that fails on the original order.

## 1.6.4 — Collaborator integration: vocabulary presets, service dock, token savings

Integrates hellonearthis's fork (reviewed head `3365943`, fork releases 1.6.2 to
1.6.4, including the previously deferred hardware dock `180b237`). Credit:
hellonearthis authored all of the changes below; the integration review fixed two
defects and adjusted one behaviour.

- **Visual vocabulary customizer**: `custom_vocabulary` per-video overrides,
  reusable presets in `MMV_HOME/vocabularies` (`/api/vocabularies`), a
  Customize vocabulary dialog, `docs/VOCABULARY_GUIDE.md`, agent client and two new
  MCP tools (30 total).
- **Live engine status dock**: `mmv/services.py`, `/api/services/status`, and
  `/api/events?once=true`. Probes only URLs from the user's own settings, with no
  proxy and short timeouts; results are cached per store.
- **Compact prompts (opt-in, off by default)**: a "Compact prompts (low VRAM/RAM)"
  checkbox and `compact_prompts` request field. Off, the writer and ident prompts and
  job messages are exactly the original full ones. On, it uses compact job JSON, keeps
  the system prompt stable across retries (feedback goes in the user message), and
  leaves out ident sections that do not apply to the chosen mode (about 62% of the
  ident prompt in standard mode, 44% in harvest, 8% in scenographic), and the vision
  check sees frames scaled to 512 px wide with replies capped at 160 tokens. Prompt
  files on disk are never modified.
- **Runtime savings (always on)**: single-pass multi-frame
  ffmpeg extraction, streaming hashes, parallel `/object_info` probes, and
  `--image-min-tokens 1024` in the Windows launcher `start.ps1` (not yet gated; it
  forces at least 1024 tokens per image for vision models).
- **Silent mouths no longer depends on lyrics (behaviour change)**: before, a request
  without lyrics text silently turned the sealed-lips protection off and the writer was
  told to describe lip and tongue articulation; found when a no-lyrics test run produced
  talking mouths. Silent mouths now follows the setting (default on) for every
  production; "Natural expressions" stays the explicit opt-out, for the planned lyrics
  and lip-sync mode to use.
- **Fixes made during integration**: stale text in the vocabulary editor could
  overwrite a loaded or reset preset (found by Codex review; browser regression test
  added); the initial SSE status probe ran on the event loop and now runs in a thread.
  The fork's own browser test expected a stale version string.
- The fork's rewritten release and verification history was not taken; this
  repository's records are kept. A real GPU comparison of full and compact settings
  is recorded in `docs/VERIFICATION.md`.

## 1.6.1 — Agent installation on RunPod and selected H3 workflows

Agent installation now includes a RunPod handoff for fresh, partial and existing
setups: discover/reuse components, persist private data and models, configure
SSH browser access, record restart steps and explain cloud rental charges.

For local H3, the installing agent must adapt and activate a private graph/map
for the selected model stack, checking loaders, precision, nodes, reference/audio
connections and runtime overrides. Filename-only model changes are not treated
as compatibility verification. These are agent procedures using existing workflow
support, not automatic conversion of arbitrary H3 variants by the shell installer.

RunPod and variant-specific end-to-end verification remain pending; installation
readiness must reflect the actual operator-approved test result. No Pod was
rented and no GPU generation was run for this release. The included skill,
installation entry points and platform notes link the procedures.

Codex prepared the guidance and release. The collaborator fork check found HEAD
unchanged at `78f31ae33f50a9578043d2af33ce05158603ab86`; existing substantive
review findings remain in [COLLABORATOR_REVIEW](COLLABORATOR_REVIEW.md).

## 1.6.0 — Batched pixel and optional vision quality checks

All passages render before pixel checks and one batch of free local retries.
The optional **Vision quality check (slower)** is off by default and judges
sampled single frames with a local vision-capable writer model and mmproj.
Pixel measurements remain authoritative for motion. Vision mostly warns;
unrequested framing devices in at least two sampled frames may use the same
single retry budget. Paid renderers are never automatically resubmitted.

Mondo swaps only services it owns: on direct H3 and SDK H3, close ComfyUI before
preview and configure its launch command. The SDK proxy stays operator-managed.
External ComfyUI is never stopped. Vision startup failure continues on pixel
checks with a visible warning. Per-attempt judgments and hashes in `quality.json`
support checkpoint reuse; `vision.json` records service notes.

SDK recovery now validates a saved local completion before querying the proxy,
so valid local media can survive proxy expiry without another submission.
Fingerprints, receipt bindings, path confinement, hashes, decoding and frame
counts guard that fast path; ambiguous submissions still require reconciliation.

Codex implemented phase 1 SDK local-completion recovery and the phase 3 vision
module with their tests, and completed orchestration tests, fixes and agent/docs
coverage. Claude Code implemented batched quality orchestration, service swaps,
preview diagnostics and UI wiring. The final fork check found HEAD unchanged at
`78f31ae33f50a9578043d2af33ce05158603ab86`; previously recorded review findings
remain unchanged. Final validation: 240 tests and 53 subtests passed, plus a $0
RTX 4090 production with both passages passing pixel and vision checks, no
retries or warnings, and a verified 11.5-second output. Hardware retry-path and
platform limits are recorded in [VERIFICATION](VERIFICATION.md).


## 1.5.0 — Motion and framing quality gates

A real Comfy SDK render produced a passage that was effectively a still image
inside a white pillarbox frame. The plan asked for a static camera, the writer
then described a motionless subject and static composition, and nothing checked
the rendered clip beyond its frame count. Production now guards both ends.

Before rendering, the music-video writer receives motion and framing rules, and
a deterministic check returns prompts that declare a still image, describe a
motionless subject under a static camera with nothing else moving, or use a
framing device such as a projected film or letterbox. Negations ("no motion
blur", "without black bars") are ignored, and framing devices the director asks
for are allowed. Cached prompts that fail the check are not reused. Laya is
unchanged: tested on the failing prompt, it could not judge motion confidently.

After each passage renders, Mondo measures frame-to-frame motion within each
planned shot, skipping cuts, and looks for uniform borders with a detailed
interior. Flat black edges are reported as inconclusive rather than failed. On
the free local renderers (`local_h3`, `comfy_sdk_h3`), a failing passage is
re-rendered once with a fixed new seed under its own segment ID, so SDK
receipts and resume stay exact; the better attempt is kept and the original
wins ties. Paid renderers are never resubmitted. Remaining problems are
assembled with a warning on the output card, in `/api/outputs` and for agents;
`quality.json` in the run records every measurement. Idents are not gated.
Original engine sources remain byte-identical.

Codex reviewed the design before integration; its findings on resume safety,
renderer allowlisting, per-shot measurement, dark-scene false positives,
negated phrases, creative intent and inspection errors were adopted. A
vision-model check with Qwen 3.8 27B judged single frames correctly in testing
but needs VRAM orchestration with ComfyUI, so it is not yet in production.

## 1.4.0 — Watch the song conduct

Every finished music video now has a synchronized musical score under its
player. It draws the per-beat energy curve, beat and downbeat ticks, each
passage colored by montage grammar, and the planner's cuts, with a playhead that
follows playback and click-or-drag seeking. A caption names the current
decision: section energy, grammar, shot scale, and whether the cut lands on a
downbeat, a beat, or splits a long hold. Opening idents shift the score onto
the video's clock. The view reads only saved run artifacts; it starts no
generation and costs nothing.

`/api/outputs/{run}/score`, the agent client and a new read-only MCP tool,
`read_music_score` (28 tools), expose the same data without local paths,
prompts or provider details. Cuts inside a passage are labelled as planned:
assembly guarantees passage boundaries, but a generated clip may not follow
every internal cut.

The idea came from collaborative ideation between Claude Code and Codex: Codex
independently ranked it first of three proposals for making the beat-driven
montage visible in a short demo.

## 1.3.0 — Open Actor Protocol 0.3

MMV now pins Open Actor Protocol 0.3.0 (`35902b1`), which adds the `jsonschema`
runtime dependency. Imported manifests are validated against OAP's bundled
offline schemas before signature checks; errors name the JSON path. The four
0.2 starter packages still validate, verify and import unchanged. New exports
declare OAP 0.3.0; older OAP readers may reject them.

Local actors can be exported as audition packages. Cast-only assets are listed
by hash but left out; a reference can be marked audition-cleared when it is a
prepared take. Imported actors still export only their preserved original.
Importing a portfolio or audition package now reports a clear "no reference
sheet" error instead of an internal failure when listed sheets are absent.

Role agreements cast an actor with this studio as Director. A draft binds the
actor's exact signed manifest and a generated casting call, and refuses rider
conflicts. The Director key is stored separately from the export signing key.
The studio can also sign as Agent for actors it exported. For outside actors, a
bundle goes to the Agent and their returned `agreement.json` is imported; only
valid signatures on unchanged terms are merged. The Actors tab, agent client,
five new MCP tools (27 in total) and the skill cover the workflow. Agent and MCP
signing requires explicit `confirm=true`. Agreements do not move money,
approve rider exceptions or establish signer trust.

The collaborator fork was checked at task start: its new revision `78f31ae`
merges this repository's 1.2.1 into the fork's pending hardware dock and labels
the result 1.2.2. Its dock and related changes were not part of this release and
remain pending a focused review (see COLLABORATOR_REVIEW.md).

## 1.2.1 — Starter installation and local library deletion

The Linux/WSL/macOS and PowerShell installers install the six public styles and
include a verified, signer-approved import of the four public starter actors.
The same step is available as `install-starter-assets`, including from wheels.
Noninteractive actor import requires explicit starter-signer acceptance; pending
actors are reported. Existing assets are preserved and the complete bundle is
checked before import. Only the authorized public assets are packaged.

Actor and style cards now offer confirmed local deletion. Active production
blocks deletion and stale previews are invalidated. Completed videos and exports
remain. Deletions survive restarts and setup reruns, including Daylight; starter
restoration is an explicit `--restore` action. Agent setup and public asset guides
now describe the integrated installation and library controls.

MCP now exposes 22 tools, including actor/style deletion, API profile creation,
selection/removal, bounded settings updates, public starter installation and
read-only API model discovery. Explicit confirmations protect destructive tools;
credentials can be imported from a designated process environment variable and
never appear in results. Active-profile removal restores manual configuration.
Existing stdio clients need reconnecting to load the new tool list.

## 1.2.0 — Agent installation and multiple API profiles

A repository installation handoff guides agents through hardware inspection,
model choices, explicit large-download approval, configuration and readiness.
Setup asks about existing API providers and documents how to configure compatible
writer/vision APIs or implement a reviewed video adapter. The new `inspect-api`
command performs a bounded, read-only model listing without generating, changing
settings, or following redirects. It does not establish inference compatibility.
Named private API profiles retain multiple accounts/models, with independent
writer, vision and supported hosted-video selectors in Settings and agent CLI
commands. Each selection uses its own credential; returning to manual settings
restores the previous configuration. No account/provider is used as an automatic
paid fallback. Keys from inactive profiles are also redacted from operation logs.
Existing providers, model/workflow defaults and paid-consent rules are preserved.
The collaborator fork remains at reviewed revision `764ca66`.

Thanks to Abandoned Muse for her inspiration and patience.

## 1.1.3 — Optional startup updates

Launch-time checks follow the installation's own tracked remote and branch.
Automatic installation is **off by default**; the UI reports available versions
with a repository link. A saved Settings switch enables installation at the next
launch, with clean fast-forward checks, staged wheel builds, preservation of
installed Comfy/MCP extras, ignored-file collision protection and re-exec into
the new code. Failures during installation attempt application-package recovery
and stop startup for environment repair. Active/interrupted work and local
changes prevent automatic replacement.

A checkout-wide runtime lease prevents another launcher updating a live app.
Source-only/wheel-only and native-platform limits are documented in `UPDATES.md`.
The collaborator fork was checked through `764ca66`; its separate hardware dock
is recorded for focused follow-up in `COLLABORATOR_REVIEW.md`.

## 1.1.2 — Additional aspect ratios

Music-video and ident shape selectors add 5:4, 4:5, 2:1, 1:2, 9:21, 3:1 and
1:3. The 9:21 option sits immediately after 21:9. Local H3 and its SDK path
use the selected shape with the existing model-grid dimension snapping.
This publication also includes the reviewed fork improvements listed below.
The launcher bounds shutdown time while live browser event streams are open.

## 1.1.1 — Reviewed fork usability and diagnostics

Reviewed hellonearthis's updates through `132c3d3` and integrated inline song
playback (including saved-project reload), bounded live operation events with
polling recovery, component-aware startup/worker errors and ComfyUI service logs.
Logs redact configured API keys. Single-operation enforcement, paid consent,
SDK receipt recovery and upstream OAP checks remain intact.

Settings adds a Laya device selector and a writer setup/tuning guide. Existing
model/workflow defaults remain in place. Optional hellonearthis presets preserve
16k context/batch/image-token tuning and CUDA/MPS CPU fallback, and the optional
reduced-flashing vocabulary retains the fork's smaller lighting/effects pools
without changing the default vocabulary or its golden fixture. The Windows
launcher exposes the alternate tuning and passes settings as UTF-8 JSON.

The fork's prompting guide is adapted to this public engine's actual controls.
Native Windows, real device fallback and GPU/paid generation require separate
operator verification. See `LOCAL_WRITER_TUNING.md` for preset behavior.

## 1.1.0 — Studio usability release

The browser tab now starts with the goose emoji: **🪿 Mondo Music Video**.
This minor release follows the SDK rendering integration, expanded vocabulary,
model controls, dark mode and resizable casting improvements delivered across
1.0.x. Six owner-reviewed styles are now available as optional presets in
`examples/style-presets`, with installation instructions and integrity hashes.
This asset-only addition leaves the application at 1.1.0.

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
