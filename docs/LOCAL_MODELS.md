# Local models and services

Mondo Music Video does not distribute model weights. Select existing files or
use the download helper after reviewing the model publisher's terms.

## Writer

Configure an OpenAI-compatible `/v1` service URL and model name. A local
llama-server can be launched by Mondo using the JSON argument list saved by
setup. The writer receives the composed Mondo music-video system prompt and a
structured job for each planned passage. It writes visual content; the planner
owns timing, shot counts and reference slots.

A local production can make up to two corrective writer passes after the first
response. Laya's notes feed that loop. API writers make one call per passage;
a rejection stops production before rendering and is recorded for inspection.
There is no automatic paid retry or provider substitution.

## Laya

The original Laya semantic reviewer checks visual density, cinematic
completeness, style and content restrictions. CUDA is the default device.
CPU and MPS can be selected explicitly for other hardware. A missing or failed
Laya model stops music-video production; it is never silently bypassed.

The configured folder must contain:

```text
laya/
  model.safetensors
  rl_agent_config.json
  tokenizer/tokenizer.json
  tokenizer/tokenizer_config.json
  encoder/config.json
```

Download the pinned English checkpoint with `mondo-music-video download-laya`.
Its manifest pins the upstream revision and SHA-256 for each file. Existing
files are preserved. Set the model directory in Settings when using another
location. Torch, Transformers and Safetensors are application dependencies.

## Standard H3 / ComfyUI

Install ComfyUI, the MiniMax H3 nodes, ComfyMathExpression and VideoHelperSuite,
and compatible H3 weights separately. The included graph is
`mmv/engine/workflows/h3_ref2video_audionodeadded.json`; its original injection map
is `mmv/engine/config/injection_map.json`. It uses the H3 video/audio VAEs, an H3
reference-to-video diffusion model and its compatible text encoder.

Setup copies this standard graph into your private data directory and asks for
your installed model filenames. It writes an injection map pointing to that
copy. The application preserves the original graph injection, audio slicing,
17n+5 frame lattice, reference tags and 20-step sampler. It does not include an
NSFW workflow or LoRA selector.

Configure ComfyUI's input and output directories as paths accessible to this
app. The adapter uses ComfyUI's direct HTTP host and port. ComfyUI's filesystem
and this app must share those directories. A ComfyUI launch command is optional
when you manage the service yourself. Automatic launches stop only processes
started for this production; they do not terminate other applications.

For a local llama-server and H3 sharing a GPU, let Mondo launch both services.
It writes and reviews all prompts, stops its writer, and then starts ComfyUI.

## Download other models

`mondo-music-video download-models manifest.json` accepts a manifest with a
nonempty `models` array. Each entry needs `name`, `url`, `license_url`, `sha256`,
and `destination`; `size_bytes` is optional. URLs must be HTTPS and destinations
are relative to your private data directory's `models/` folder. The helper
asks before each download and checks integrity before activation. It does not
bypass gated access, grant licenses, overwrite files, or infer compatibility.
