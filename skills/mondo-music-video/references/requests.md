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
  "seed": 0,
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

Use actual returned upload/actor/style/output IDs. Actors and additional image
references share a maximum of nine images. WaveSpeed H3 requires at least one
image. Read catalog for each backend's resolution menu. Supported renderers are
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
