# Local services and model setup

The app contains no AI weights, actor library, bundled ComfyUI, or private studio
workflows. Install and configure your chosen services independently, then point
Mondo Music Video at them. API-only operation needs no GPU or local model files.

## Local H3

Use an installed ComfyUI with a compatible H3 reference-to-video workflow and
its model files/custom nodes. Export the workflow in **API format**, not the UI
layout format. Configure the following in Settings:

- ComfyUI URL, normally `http://127.0.0.1:8188`.
- ComfyUI input directory, writable from this machine. Audio and actor references
  are copied there with production-specific filenames. A remote service requires
  an explicitly shared input directory; arbitrary remote ComfyUI is not supported.
- Your exported API workflow JSON path.
- A binding map JSON path describing that workflow's node inputs and output.

Example binding map (replace every node ID/input name to match your own graph):

```json
{
  "inputs": {
    "prompt": ["10", "value"],
    "duration": ["11", "value"],
    "width": ["12", "width"],
    "height": ["12", "height"],
    "seed": ["13", "noise_seed"],
    "video_prefix": ["14", "filename_prefix"]
  },
  "reference_node": "12",
  "output_node": "14"
}
```

The reference node must accept H3 sockets `ref_images.ref_image_0`, etc., and
`ref_audios.ref_audio_0`. New LoadImage/LoadAudio nodes are attached per clip.
The output node must report a downloadable video in ComfyUI history. Configure
sampler settings in your workflow; the app does not expose sampling internals.

Music passages are rendered at 24 fps, rounded up to H3's 17n+5 frame lattice,
then trimmed to the planned span. Local output uses a modest 720p-class canvas
(other picture shapes have corresponding dimensions), regardless of the hosted
resolution menu. This preview does not install custom nodes or choose hardware
settings for you. Confirm model/runtime requirements with their maintainers.

Cancellation removes this application's pending ComfyUI task. It deliberately
does not issue a global interrupt that might stop another client's task. An
already running local task can continue; inspect ComfyUI before starting again.

## Style harvesting

Set a vision-capable OpenAI-compatible `/v1` endpoint and its served model name.
The app sends cleaned reference images to `/chat/completions` and stores the
returned style description. No service is silently launched. Use an estimate
of zero only for a free/local service; enter an expected per-call charge for a
paid one. Harvesting uses at most 700 completion tokens but the configured cost
is an estimate, not a provider spending cap.

## Opt-in model downloads

Create a reviewed JSON manifest with entries like:

```json
{
  "models": [{
    "name": "Your selected model",
    "url": "https://model-publisher.example/pinned-revision/model.gguf",
    "license_url": "https://model-publisher.example/license",
    "sha256": "REPLACE_WITH_THE_PUBLISHERS_64_CHARACTER_LOWERCASE_SHA256",
    "destination": "writer/model.gguf",
    "size_bytes": 123456789
  }]
}
```

This is a format example, not a working model source. Use the publisher's real
URL, revision, checksum, size and terms. The installer does not infer permission
from a download URL. Gated/authenticated sources are not supported by this
preview's helper: download those through the publisher's normal process.

Verified files go under the configured data directory's `models/` tree. Configure
your AI service to load them there, or move them into that service's expected
location. The helper does not edit an unrelated service's configuration. Existing
destinations and partial downloads are preserved rather than overwritten.
