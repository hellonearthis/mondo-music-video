# Mondo Music Video

**Version 1.0.10** · MAXIMUM GOOSE LABORATORIES · Apache License 2.0

Turn your song into a complete music video. Mondo listens to the track, detects
beats and downbeats, measures energy, and identifies musical sections. Its
seeded planner turns that musical structure into montage passages and timed
shots. An LLM writer develops the visuals from your direction, style and cast;
Laya reviews the prompts before the video renderer runs. Mondo then trims every
passage to its planned frames, joins the picture, and restores your original song.

## What you can make

- Music videos with beat-driven cuts and energy-aware montage grammar.
- Consistent reference-image actors with Open Actor Protocol built in.
- Your own visual styles, including styles harvested from reference images.
- Animated production idents and opening or closing credits.
- Finished videos to play, download, or upscale with your installed Topaz tools.

Use local models or supported API providers. One production runs at a time,
with progress, logs and cancellation. You provide your media, models and API
keys. No actors, model weights or third-party commercial software are bundled.

## Four montage grammars, driven by your music

Mondo uses four distinct visual grammars. The analyzer detects the track's
beats, downbeats, energy and musical sections; the planner uses that structure
to select a grammar and place the shots and cuts.

| Musical section energy | Montage grammar | Visual structure |
| --- | --- | --- |
| Low | **Standard** | One subject, sustained observation, fewer and longer shots. |
| Mid | **Thematic multi-scene** | New subjects and settings connected by one thematic anchor. |
| High | **Chaotic multi-scene** | New subjects, settings and actions in discontinuous collisions. |
| Peak | **Single-subject fragmentation** | A recurring subject seen through many angles and shot scales. |

These are the default energy-to-grammar assignments. The song's detected
sections determine which grammars a production uses. Shot density, camera motion
and shot scale respond to the musical energy; passage boundaries follow detected
downbeats. Timing is detected from the uploaded audio automatically.

The LLM writer receives the selected grammar, planned shots, camera instructions,
visual vocabulary and reference bindings. It writes the visual content while
the planner owns timing. GPU Laya reviews the prompts before rendering, and
Mondo assembles the rendered passages against the original song.

## Install

Install **Python 3.11+**, **Git**, and **FFmpeg/ffprobe**, then:

```sh
git clone https://github.com/hodgemann/mondo-music-video.git
cd mondo-music-video
```

Linux, macOS, or Windows through WSL:

```sh
bash install.sh
.venv/bin/mondo-music-video serve
```

Windows PowerShell:

```powershell
.\install.ps1
.\start.ps1            # Starts Mondo and connects to local llama-server
.\start.ps1 -SelectModel # Select or switch your llama.cpp GGUF model interactively
```

Open **http://127.0.0.1:8091**. Setup saves paths and model/service choices for
your machine. The app runs on localhost and uses a single worker.

## Configure your models

The music-video writer accepts an OpenAI-compatible chat service, either local
or API-based. Local H3 uses ComfyUI and the included standard H3 workflow and
injection map. Setup can configure launch commands so the local writer stops
before the renderer starts, freeing GPU memory. Existing externally managed
services stay under your control.

Laya reviews music-video prompts locally and uses CUDA by default. Select your
Laya model folder in Settings, or download the pinned model files yourself with:

```sh
.venv/bin/mondo-music-video download-laya
```

The helper displays the source, terms and destination and verifies checksums.
You can also select existing model files. See [model setup](docs/LOCAL_MODELS.md)
for the required files, renderer setup, and download manifests.

Hosted rendering supports WaveSpeed H3, Seedance 2.0 and Seedance 2.5. Supply your
own provider key. Charges are shown before you accept a production. An API
writer has a separately configured estimate; paid submissions are not retried
automatically. Uploaded references and song passages go to your chosen provider.

## Make a video

1. Upload your song and choose a style and visual direction.
2. Optionally choose actors or reference images, a conceptual theme, or lyrics
   to inform the visuals. Musical timing comes from the track analysis.
3. Review the detected musical structure, planned shots and estimated charges.
4. Start production. Mondo writes and reviews the prompts, renders the passages,
   and assembles the finished music video automatically.
5. Play or download your video. Create an ident in Credits & Idents to attach
   to another production, or use the optional Topaz export on a finished video.

The Actors tab imports and exports OAP packages, verifies their signatures and
checks actor riders. No account, reporting or public actor sharing is required.

## Agent operation

The included skill and optional MCP server let an agent operate the same app,
including its OAP, review and production workflow:

```sh
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/mondo-music-video-mcp
```

Run the app separately. See [agent setup](docs/AGENT_SETUP.md) and the bundled
[skill](skills/mondo-music-video/SKILL.md). A CLI client is also included:
`mondo-music-video-agent --help`.

## Your data

Data lives in your user data directory: XDG data on Linux, Application Support
on macOS, or LocalAppData on Windows. `MMV_HOME` or `--data-dir` selects another
location. Back it up to preserve actors, styles, signing identity and productions.
Keys stay in a local secrets file; environment variables `WAVESPEED_API_KEY`,
`MMV_WRITER_API_KEY`, and `MMV_VISION_API_KEY` override saved values. Keep that
directory private.

See [platform support](docs/PLATFORMS.md), [verification](docs/VERIFICATION.md),
[scope](docs/SCOPE.md), and [third-party notices](docs/THIRD_PARTY.md).

## License

Mondo Music Video is licensed under [Apache License 2.0](LICENSE). Third-party
components retain their own licenses. [Open Actor Protocol](https://github.com/hodgemann/oap)
is MIT-licensed. Laya inference code is attributed in [its vendor notice](mmv/engine/validators/laya/VENDOR.md).

Copyright 2026 MAXIMUM GOOSE LABORATORIES.
