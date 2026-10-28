# Production requests

`preview_production` accepts a `request` object. With the CLI, write that object
to a JSON file and run `mondo-music-video-agent preview request.json`.

## Music video

```json
{
  "kind": "video",
  "song": "UPLOAD_ID.wav",
  "title": "Coastline",
  "direction": "A sunlit coast, rhythmic waves and a slow moving camera.",
  "style_id": "daylight",
  "backend": "local_h3",
  "resolution": "768p",
  "aspect": "16:9",
  "actors": [],
  "references": [],
  "megapixels": 0.6,
  "beats_per_bar": 4,
  "bars_per_phrase": 8,
  "vision_quality_check": false,
  "conceptual_theme": "",
  "lyrics": "",
  "ref_policy": "all",
  "casting_policy": "random",
  "ensemble_mode": "off",
  "on_screen": 1,
  "start_ident": "",
  "end_ident": ""
}
```

`seed` (default 0) is the variation seed: shot plan, vocabulary and casting.
Leave out `render_seed` so each video renders with its own random seed; the quote
returns both. Pass `render_seed` only to repeat an earlier video exactly or when
the user gives one. A new variation seed changes the plan, so its prompts are
written again; a new render seed alone keeps the same prompts.

Use actual returned upload/actor/style/output IDs. Actors and additional image
references share a maximum of nine images. WaveSpeed H3 requires at least one
image. To remove an image before preview, omit its uploaded ID from the next
`references` array; inspect the returned quote before explicit start consent.
Read catalog for each backend's resolution menu. Supported renderers are
`local_h3`, `comfy_sdk_h3`, `wavespeed`, `seedance_2` and `seedance_2_5`. Hosted providers send the
selected images and song passages to the configured provider.

Content defaults to `none` in all four OAP categories. If the user requests
different ratings, pass all categories with valid catalog values:

```json
{
  "content": {
    "nudity": "none",
    "sexual_content": "none",
    "blood_gore": "none",
    "violence": "none"
  }
}
```

Actor riders must permit the selected ratings. Do not relax them to force a run.
The original analyzer detects beats, downbeats, energy and musical sections.
The original planner places passages and shots on that structure. Inspect the
analysis and segments returned by the production preview. The LLM writer creates
the visual prompts; Laya reviews them before rendering. Local rendering uses
`megapixels`; hosted rendering uses the provider's named `resolution`.

Music-video generation requires the configured writer and Laya model. Do not
bypass a failed Laya review or promise a completed production before rendering
and automatic frame-exact assembly have succeeded.

To use an imported OPP prop for an actor's instrument, first inspect/import the
package and preview sheet selection. Then add `instrument_mode: "perform"`,
`instrument_assignments: {"actor_id": "guitar"}`,
`instrument_props: {"guitar": "prop-id"}` and optionally
`instrument_prop_uses: {"guitar": "strumming strings"}`. Prop IDs and use tags
are free-form. Omit `instrument_props` to keep the existing instrument sheet.
The quote shows the selected sheet and slot count; start still needs consent.

## Ident

```json
{
  "kind": "ident",
  "title": "My Studio",
  "direction": "Brushed chrome letters emerge from soft light.",
  "style_id": "daylight",
  "backend": "local_h3",
  "resolution": "768p",
  "ident_seconds": 5,
  "aspect": "16:9",
  "references": []
}
```

Idents last 4–12 seconds. Generated lettering is not guaranteed to spell the
title correctly. A completed `RUN_ID/ident.mp4` can become `start_ident` and/or
`end_ident` in a later video request.

## Style harvest

```json
{
  "kind": "harvest",
  "style_id": "teal-light",
  "title": "Teal Light",
  "references": ["UPLOADED_IMAGE.png"]
}
```

Requires a configured vision service/model and one or more image upload IDs.
The new style ID must not already exist. The preview's estimate comes from the
configured vision per-call estimate; it is not a provider spending cap.

## World harvest

```json
{
  "kind": "world_harvest",
  "world_mode": "create",
  "world_id": "salt-archive",
  "title": "Salt Archive",
  "direction": "optional notes for the reading",
  "world_images": ["UPLOADED_IMAGE.png"],
  "world_videos": ["UPLOADED_VIDEO.mp4"],
  "world_lore": ["UPLOADED_TEXT.md"],
  "world_runs": ["FINISHED_RUN_ID"]
}
```

Upload images with kind `reference`, clips with `video` and text with `lore`.
`world_mode` is `create` (the ID must be new) or `grow` (the world must exist).
At least one source is required; a harvest reads at most 24 images (8 per video,
4 per finished run), 3 videos and 5 lore files of 60 KB. It needs the configured
vision service. Starting it only writes a **proposal**: call
`inspect_world_proposal` to read its field-level changes, show them to the user,
and call `accept_world_proposal(confirm=true)` only after the user has reviewed
them (or `reject_world_proposal`). Growing is reviewed the same way; a stale
proposal must be harvested again. `rollback_world` restores an earlier version as
a new one.

To change a world by hand (remove or reword entries, edit subjects, adjust the
vocabulary pools), call `get_world`, edit the ledger, and call
`preview_world_edit(world_id, world)`; show the user its field-level changes and
call `edit_world(world_id, world, confirm=true)` only after they have reviewed
them. The edit starts from the ledger's own `version` (or `base_version`) and
fails if the world changed since; it is saved as a new version, so
`rollback_world` undoes it. CLI: `world-edit-preview ID FILE`,
`edit-world ID FILE --confirm`.

To use a world in a video, add `"world_id": "salt-archive"` and optionally
`"world_pool_mode": "replace"` (only the world's terms, the default) or
`"append"` (add to the standard pools) to a video request.

Optional contrast worlds: `"world_contrast": {"mirror": "id", "opposite": "id", "tangent": "id"}` (any subset) and
`"world_contrast_strength": 0-100` (default 50). High-energy shots then take settings, lighting, mechanisms and tonal
registers from those worlds; cast, wardrobe and subject slots are never changed. Requires `world_id`. Off by default.
The preview reports `world_contrast` (shots that depart and the roles used).

## Start, observe, export

The preview returns `id`, `estimate_usd`, `paid`, clip count, duration and notes.
Use its actual `id` with `start_production(quote_id=..., consent=true)` after
authorization, or `mondo-music-video-agent start QUOTE_ID --consent`. Poll status;
read logs with the returned run ID if needed. Output records include `file` and
`play_url`. Download to a user-selected new path; do not overwrite existing files.

## Comfy SDK recovery

`comfy_sdk_h3` runs the existing H3 workflow using the official Python SDK and
a local Comfy API v2 proxy. Configure `comfy_sdk_url` and, if required,
`MMV_COMFY_API_KEY` in the app. It uses `megapixels`, like `local_h3`.

For an interrupted render or failed download, call `preview_resume(run_id)`
(or `mondo-music-video-agent preview-resume RUN_ID`), review the returned quote,
and obtain consent before passing its ID to `start_production`. Recovery reuses
validated prompts and known generation IDs. It never resubmits an ambiguous,
failed, canceled or expired job. Do not delete receipts to force a retry.

If prompt validation exhausted its attempts before any rendering, status exposes
`can_retry_prompts`. Call `preview_retry_prompts(run_id)` (CLI:
`mondo-music-video-agent preview-retry-prompts RUN_ID`) for a new quote from the
saved request. Review that quote and obtain fresh start consent, including paid
consent where applicable. This creates a new run; it does not resume or restart
the failed run automatically.

Independent dancing: `dance_mode: "independent"`, `dance_parts: {"actor_id": "bass"}`. Parts: auto, beat, drums, bass, vocals. Preview includes stable part/movement-family assignments, per-shot cues and explicit overall-beat fallbacks. No lead, separation or downloads. Version-3 plans add contrasting bounce/step/rotation actions; a fresh preview is required to use the repair, while old productions resume their saved plan. Existing group/off behavior is preserved. Prompt checks do not prove distinct rendered movement.

## Instrument performance (1.9.0)

Use `instrument_mode: "perform"` only when requested (default off), with `instrument_assignments` mapping selected actor IDs to `drums`, `bass`, `guitar` or `keyboards`. `instrument_references: true` uses OPP props; inspect `instruments` and `props` first. Guitar/keyboard props are bundled; import missing ones (drums, bass) as `.opp` with `upload_media(kind="opp")`, `inspect_opp` and `import_opp`, or use `instrument_references: false` for text guidance. Local imports never overwrite or publish.

Inspect preview `instruments` for per-shot cues, mix/unknown fallbacks and per-passage reference counts. Players do not dance; other actors may. Approved singers may sing while playing. Only existing stem caches/audio are used (CPU analysis may run); no separation or downloads start. Keyboards use piano as a proxy. Slot overflow stops preview. Saved plans and sheet hashes are checked on resume. Same-song/seed operator comparison is still pending; do not promise precise finger/note sync or verified visual consistency. Existing OAP, single-operation, quote consent and no paid retry rules apply.

In v1.9.5, an unambiguous vague guitar action may be corrected to explicit
string/fret contact before normal schema, motion, instrument and Laya checks.
The private operation log and `segNNN.instrument-repair-N.json` identify edited
shots; the original writer JSON is preserved. Wrong-instrument gestures and
ambiguous clauses still fail validation. No extra paid writer call is made.

## Storyboarding

Storyboards are optional for music videos and idents. Upload source images as
`reference`, preview `kind: "storyboard"` with `storyboard: {mode: "narrative", images: [UPLOAD_ID]}`,
review cost and start only with authorization. Poll status, list `storyboards`, then
read `inspect_storyboard(run_id)` (CLI `storyboard-result RUN_ID`). Edit/reorder
`panels: [{image, direction}]` before adding the result as `storyboard` with
`enabled: true` to a video/ident preview. Modes are `narrative` (default) and `visual`.
Text-only panels use empty image IDs. Inspect returned `storyboard.passages` timing
before start. No automatic interpretation retry; recover completed results by run ID,
and inspect logs before making another call. Inspect raw model output with
`inspect_storyboard(run_id, raw_response=true)` or CLI `storyboard-result RUN_ID --raw-response`. Existing video resume binds the saved
alignment to prompts. Ident `ident_all_references: true` uses all attached references
within renderer limits; false preserves one-reference casting. Source storyboards
remain private. See docs/STORYBOARDS.md in the checkout for the full workflow.

Final export quality: each clean, subliminal and captioned version is independently
assembled from original clips in one FFmpeg video encode (H.264 CRF 6, slow).
Flashes and captions share that assembly pass. `caption_video` / the existing caption
API rebuilds from saved original sources, retaining flashes and replacing caption
filters. Missing originals cause an error; restore the clips, song and saved run
metadata, then submit the caption job again. It never regenerates clips or makes paid
calls. Inspect job status and `output.json` for warnings and download names; production
preview/start/resume and consent remain unchanged. Keep `assembly-source.json`,
`assembly-assets/`, original clips and the song for later reconstruction. Topaz
upscaling is the explicit user-requested exception and still uses the selected final.
