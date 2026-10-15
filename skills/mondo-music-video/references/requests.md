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
  "segment_seconds": 8,
  "bpm": null,
  "start_ident": "",
  "end_ident": ""
}
```

Use actual returned upload/actor/style/output IDs. Actors and additional image
references share a maximum of nine images. WaveSpeed H3 requires at least one
image. Read catalog for each backend's resolution menu. This preview supports
`local_h3`, `wavespeed`, `seedance_2` and `seedance_2_5`. Hosted providers send the
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
An optional BPM is 30–300; passages are 4–14 seconds. Automatic final assembly
is internal. The public prompt builder and duration/BPM planner are intentionally
simple; do not promise automatic beat detection or the full studio writer.

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
