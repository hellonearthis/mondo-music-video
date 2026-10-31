# Pre-generation score editor and instrument driver (design)

Status: implemented in release 1.6.12. Requested by the owner on the advice of a
musician friend: show the "watch the song conduct" view before generation so
the plan can be adjusted, and let an instrument drive what the video syncs to.

## Today

`production.prepare()` analyses the song once (cached by audio hash and meter in
`analysis/<hash>.json`, a `ScoreMap`), then calls the unmodified engine
`plan(score, ...)`. Preview production (`POST /api/quote`) returns only counts
and segments. The score view (`mmv/score_view.py`, 1.4.0) reads saved run
artifacts of a finished video, so it cannot be used before generation. The beat
grid, bar-1 guess, sections and per-beat energy all come from the mixed signal.

## Stage 1 (release 1.6.12): editable score before generation

- `ScoreMap` stays the contract; engine sources stay byte-identical. A new
  `mmv/score_edit.py` applies a validated `score_edits` object to the cached
  `ScoreMap` between load and `plan()`:
  - `downbeat_shift` (0..beats_per_bar-1): which beat is bar 1.
  - `beat_nudge_ms` (bounded): shift the whole grid for tracker latency.
  - `muted_beats`: beat times the planner must ignore.
  - `sections`: replacement boundaries and energy labels (low/mid/high/peak),
    contiguous, covering the song, snapped to frames.
  Every edit is bounded, quantized to frames and rejected if it would leave no
  planable passage. Edits never touch the cached analysis file.
- `ProductionRequest.score_edits` (strict, default empty). It is part of the
  request, so it enters the quote fingerprint, `request.json` and resume. An
  edit changes the plan, so the user must re-preview; a stale quote cannot start.
- `POST /api/score/preview` (free, read-only, no job): audio + meter + edits ->
  beats, downbeats, sections, energy, planned passages/cuts and waveform peaks.
  Peaks are computed server-side with ffmpeg (bounded sample count) so browsers
  need not decode large files.
- UI: after Preview production the plan opens in an editor panel: waveform
  (wavesurfer.js, vendored, plus Regions for draggable section boundaries), beat
  and downbeat ticks, energy curve, planned cuts, playback, a "bar 1 starts here"
  control, and "Re-plan" which re-runs preview. Keyboard accessible, as 1.4.0.
- Agent client + MCP: `preview_production` accepts `score_edits`; a read-only
  `preview_music_score` tool returns the same structure (tool count +1).
- No paid or GPU work occurs in this stage.

## Stage 2 (release 1.6.13): instrument driver via stem separation

- Optional `[stems]` extra (Demucs, torch already present). Opt-in; the model
  download needs explicit approval with size, destination and licence shown
  first; never automatic, never during tests.
- `mmv/stems.py`: separation runs in a subprocess worker (like analysis), cached
  by audio hash and model under `analysis/stems/`, CPU fallback, never while
  ComfyUI holds the GPU. Stems are analysis input only; the video keeps the
  original audio.
- `ProductionRequest.analysis_driver`: `mix` (default, identical to today) or a
  stem (drums, bass, vocals, other; guitar/piano with the six-stem model). The
  beat grid still comes from the mix (robust); the driver stem supplies per-beat
  energy and accent strength, which the planner already reads through
  `beat_energy`. The editor lets the user solo/mute stems to hear and see them.
- Stage 1 ships without stems; the driver control shows "needs the stems add-on"
  until it is installed and approved.

## Constraints

Default behaviour unchanged. One active operation. Temp data and mock
services in tests. Third-party notice and licence check before vendoring
wavesurfer.js and before adding Demucs.

## Review findings adopted (Codex, read-only, 2026-10-19)

1. The driver stem feeds `beat_energy` only (`energy_at`, plan.py:396): that
   changes cut density, camera and scale, not which instant a cut lands on. Cuts
   still use the mixed grid. Syncing to an off-beat instrument attack needs
   alternate cut candidates (`ScoreMap` has no onset field), which would be an
   engine change; out of scope, recorded as a limitation. Section energy is
   recomputed from the driver; section labels stay user-controlled.
2. Irregular grids are tolerated mechanically but change rhythmic density
   (stride counts retained beats; partitioning counts downbeats). Bar phase is
   fixed before muting. A muted downbeat can still be a seam, so "mute" means
   "not a cut candidate", not "removed from bar counting". Beats stay sorted,
   unique, bounded and paired with their energies.
3. Peaks are computed server-side, streamed into bounded min/max buckets, with
   output and execution limits.
4. Validation inspects the resulting plan: ordered positive boundaries, full
   frame coverage, spans of at least 12 frames (plan.py:498 silently skips
   shorter), finite energies, supported labels. Edits that yield oversized
   passages or unsplittable holds (plan.py:335/369/412) are rejected by the
   existing post-plan checks with a plain message, never silently coerced.
5. Edits are deep-copied (`plan()` mutates the first section start,
   plan.py:489) and never enter the analysis cache. Stem model/version/options
   and an analysis algorithm version identify stem caches separately.
6. Normalized edits and the effective driver reach request, fingerprint and
   `prepared.json` through one transformation. Resume replays the approved
   snapshot in `prepared.json` and never re-edits or re-analyses.

