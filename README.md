# Mondo Music Video

A community music-video application from MAXIMUM GOOSE LABORATORIES.

Version: **0.1.0** — development preview, not a broadly verified release.

The application turns a song into a music video using your own local
generation setup or supported API providers. Open Actor Protocol (OAP) will be
built into actor import/export and reference-image workflows.

Included features:

- Music-video creation, one operation at a time, with progress and cancellation.
- Actors and reference images, with built-in OAP support.
- Styles and style harvesting from reference images.
- Animated credits and idents.
- Finished-video playback and download.
- Optional Topaz upscale export with a compatible user-owned installation.
- Guided system configuration and optional downloads of supported models.

No actors, AI model weights, songs, API keys, or Topaz software are bundled.
You supply your own media and provider accounts. Model downloads will require
review of the relevant upstream terms and access requirements.

## Install and start

Install Python 3.11 or newer, Git, and FFmpeg (including ffprobe) first.

Linux, macOS, or Windows/WSL2:

```sh
bash install.sh
.venv/bin/mondo-music-video serve
```

Native Windows, from PowerShell:

```powershell
.\install.ps1
& .\.venv\Scripts\mondo-music-video.exe serve
```

Open **http://127.0.0.1:8091**. The launcher serves only on localhost and prevents
two launched instances from sharing the same data directory. Keep this a local
application; it is not a multi-user hosted service. Do not launch it with several
workers or use a reverse proxy to expose it publicly.

Setup creates an isolated environment and asks for renderer settings. It does
not install ComfyUI, launch AI services, or download models automatically.
`--non-interactive` installs dependencies and prints checks instead of running the
setup questions. Existing user data and models are not overwritten.

The settings screen also accepts your own keys. They are stored in a local
secrets file with owner-only permissions where supported; they are not encrypted
at rest. Environment variables `WAVESPEED_API_KEY` and `MMV_VISION_API_KEY` override
saved keys. Model/service requests go directly to the provider you configure.

Default data locations are the user's XDG data directory on Linux, Application
Support on macOS, and LocalAppData on Windows. Set `MMV_HOME` or run
`mondo-music-video --data-dir /your/path configure` / `serve` to choose another
location. Back up that data directory to preserve actors, signing identity,
styles and productions. Do not publish it.

## Your first production

1. Configure a renderer in Settings. Hosted H3 requires a reference image;
   Seedance supports generation without one. Local H3 requires your installed
   ComfyUI, models, exported API workflow and binding map.
2. Upload a song, describe the visuals, select a style and optionally add actors
   or reference images. An optional BPM aligns passages to bars.
3. Preview the production and estimated provider charges, then explicitly accept
   and start. Progress and cancellation remain available.
4. Play/download the finished video. Generate an ident in Credits & Idents to
   use it as opening/closing credits on a later production.

The public prompt builder uses your direction, style, cast descriptions and a
small rotating shot vocabulary. It does not contain the full studio's narrative
writer, casting system or advanced music planner. Song timing uses duration and
optional user-supplied BPM, rather than automatic beat detection.

See [local model setup](docs/LOCAL_MODELS.md), [platform support](docs/PLATFORMS.md)
and [verification](docs/VERIFICATION.md). Cross-platform launchers are included;
real GPU, paid-provider and Topaz productions still need operator verification.

## Model download helper

```sh
.venv/bin/mondo-music-video download-models /path/to/reviewed-manifest.json
```

The helper shows source/license/destination, asks before each download and checks
SHA-256 before activation. This preview has no curated model catalog; use a
reviewed manifest as described in [local model setup](docs/LOCAL_MODELS.md).

See [the roadmap](docs/ROADMAP.md), [project scope](docs/SCOPE.md), and
[third-party dependencies](docs/THIRD_PARTY.md).

## License

Application code and documentation authored for this repository are licensed
under [Apache License 2.0](LICENSE). Third-party dependencies retain their own
licenses. [Open Actor Protocol](https://github.com/hodgemann/oap) is a separate
MIT-licensed project.

Copyright 2026 MAXIMUM GOOSE LABORATORIES.
