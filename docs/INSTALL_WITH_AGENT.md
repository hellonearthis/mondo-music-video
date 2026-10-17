# Install this with an agent

The user-facing instruction is simply:

> Install this: https://github.com/hodgemann/mondo-music-video

This is the installation handoff for an agent with terminal/filesystem access.
Do the work, including choosing and configuring suitable models. Ask the user
only for material choices, credentials and download approval. Do not hand back
a list of commands for them to run when you can run those commands yourself.
This guide directs the agent; the shell installer itself does not automatically
select or download a complete model stack.

## 1. Inspect before downloading

Clone into a new, ordinary checkout if necessary. Read root `AGENTS.md` and the
[platform notes](PLATFORMS.md). Never use another private studio as an installation
source. For an existing installation, inspect its environment and settings before
changing anything; do not overwrite its models, workflows, actors or credentials.

Use read-only system tools to determine:

- OS, architecture, Python 3.11+, Git and FFmpeg/ffprobe availability.
- Physical RAM, GPU model, total and available VRAM, driver/runtime support.
  On NVIDIA, use `nvidia-smi`; on macOS, inspect unified memory. Missing NVIDIA
  detection does not prove that no GPU exists.
- Free space on each intended download volume, including dependency caches,
  temporary files and room for generated video. Do not count RAM as VRAM.
- Existing ComfyUI installations, compatible model files, llama-server and
  OpenAI-compatible writer services, using configured or conventional paths.
  Ask for a location if necessary; do not search unrelated private directories.

Before running pip or an OS package manager, explain the proposed dependencies.
PyTorch and GPU runtime packages can themselves be gigabytes. Obtain download
approval before those downloads too. Use a private virtual environment. Do not
change system Python, GPU drivers or administrator settings without explaining
the specific need. Keep all services on loopback.

## 2. Recommend a complete configuration

First ask whether the user already has a preferred API provider for writing,
vision or video. Follow [bring-your-own-provider setup](API_PROVIDER_SETUP.md)
to inspect supported interfaces and configure them, or scope a local adapter
for a new video API. Reuse their account where compatible rather than assuming
WaveSpeed is their only hosted choice. Offer multiple named API profiles and
independent choices for writing, vision and video; adding one account must not
replace another. Do not request keys in shared chat.

A working music-video setup needs **a writer, local Laya review, and a renderer**.
Optional vision/style harvesting and Topaz are separate; do not install them
unless requested. Reuse working components before proposing new downloads.

For the writer, prefer a supported existing service. For a new local writer,
consider official Qwen3 GGUF quantizations with llama.cpp. Qwen3-4B Q4_K_M is
about 2.50 GB of weights; Qwen3-8B Q4_K_M is about 5.03 GB. These are starting
options, not guarantees of quality or fit. Account for context/KV cache, runtime
overhead, Laya and other running applications. Prefer the smaller option when
resources are limited; use a modest context such as 8192 initially. Configure
non-thinking output (`--reasoning off --jinja` with a compatible llama-server),
and choose GPU offload for the actual hardware. Do not copy the interactive
configurator's 65536-token/all-layers launch settings onto a small machine.
If local resources are inadequate, explain a hosted writer's costs and privacy
implications and ask before selecting it.

Laya's pinned files total about 0.85 GB. Keep the real reviewer; do not disable
it to make an installation appear successful. Choose CPU explicitly if CUDA/MPS
is unavailable or GPU memory is needed elsewhere. CPU operation can be slower.
See [local models](LOCAL_MODELS.md) and the bundled
[`laya-download.json`](../mmv/engine/config/laya-download.json).

For rendering, local H3 requires ComfyUI, compatible nodes/runtime and substantial
memory and disk. Its weights alone are tens of gigabytes. Inspect the current
[official H3 guide](https://docs.comfy.org/tutorials/video/minimax/minimax-h3),
[native workflow](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-native)
and [publisher model card](https://huggingface.co/Comfy-Org/MiniMax-H3).
Choose matching diffusion, text encoder, video VAE and audio VAE files together.
The publisher prefers int8_convrot with a compatible cu130 runtime and fp8_scaled
otherwise; verify the actual ComfyUI environment, not just the driver version.
Do not infer inference memory from compressed download sizes or claim a GPU
will fit without evidence. If uncertain, explain the uncertainty and recommend
hosted rendering as a choice rather than silently downloading a huge stack.
macOS and weak/unknown hardware should not receive an assumed NVIDIA setup.

Use official licensed models for a fresh setup. The bundled graph contains
example filenames, including a custom text encoder name; these are not a
download shopping list. Put selected filenames in a private workflow copy,
leaving shipped graphs and existing user workflows unchanged. Review the
[MiniMax license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE),
including its commercial-use conditions. Do not promise a commercial license.

Supported hosted renderer choices are listed in the README. Explain provider
costs, account/key requirements and media upload implications before choosing
one. A hosted renderer still needs the writer and local Laya setup.

## 3. Obtain one clear download approval

Present a compact proposal listing each new model/runtime, source, exact bytes
where published (otherwise an explicit estimate/unknown), local destination,
license/terms link, aggregate download and free disk space with headroom. Separate
existing/reused files from downloads. Include dependency downloads. Explain why
the proposed configuration suits the detected machine and any remaining risks.

Ask once for approval of that plan. Approval covers only the listed downloads
and configuration; do not ask again for each routine command. If a dependency
size cannot be established, state that uncertainty before approval. A material
increase, model/provider change or new paid service needs a revised proposal.
The original “install this” is not permission for silent multi-gigabyte downloads
or paid generation. While waiting, continue only independent preparation.

Include the four bundled starter actors and six bundled styles in the setup
plan by default, unless the user declines. They are already in the checkout and
need no separate model download. Explain the starter-cast signer and OAP riders
as part of setup; obtain explicit signer acceptance before importing signed
actors, unless the user has already authorized that signer. Do not silently
set an unknown-signer acceptance flag. Keep existing actors/styles on collisions.

## 4. Install, download and configure

After the applicable download approval, use the provided installer without its
interactive questionnaire so the agent can handle configuration:

```sh
# Linux, macOS, or WSL; from the checkout
bash install.sh --non-interactive
.venv/bin/mondo-music-video doctor
```

```powershell
# Native Windows; from the checkout
.\install.ps1 -NonInteractive
.\.venv\Scripts\mondo-music-video.exe doctor
```

These commands install the app, not ComfyUI, llama.cpp, FFmpeg or model weights.
Install missing approved prerequisites from their official sources. Respect the
platform verification limits in `PLATFORMS.md`. Install the optional `.[comfy]`
extra only if choosing the SDK/proxy renderer; follow [COMFY_SDK.md](COMFY_SDK.md).

Download every selected component after approval. Pin model revisions and verify
published SHA-256 hashes and byte sizes before activation. Write into temporary
files first; never overwrite existing models or treat a partial file as usable.
Record selected versions and destinations in the user's private data directory.
Do not automatically retry paid requests or resolve a failure by switching providers.

The existing `download-laya` and `download-models MANIFEST` commands provide
HTTPS, path and integrity checks and prompt for each manifest entry. An agent
may answer these prompts only for files covered by the user's approved plan.
Custom manifests require name, HTTPS URL, HTTPS license URL, lowercase SHA-256,
relative destination and preferably `size_bytes`; destinations are beneath the
application's `models/` directory. For ComfyUI model locations, use a verified
download into the intended ComfyUI model folder instead. Do not change the
download helper's path boundary to write elsewhere.

Configure using the app's Settings UI/API or the supported configurator. See
[LOCAL_MODELS.md](LOCAL_MODELS.md) and [MODEL_SETTINGS.md](MODEL_SETTINGS.md).
Set actual writer model ID/URL, Laya folder/device, renderer paths and launch
commands. Use a private workflow copy for fresh H3 selections. Stop the app
before offline settings edits; preserve unrelated settings. Avoid concurrent
GPU residency where possible: managed writer/render services can be sequenced
by the app. Leave automatic updates off unless the user requests them.

Credentials belong in the application's private credential storage, never Git,
shell history, shared reports or committed settings. Ask the user to enter
secrets through the Settings UI when practical. Do not create accounts or spend
money as part of an installation request.

### Install and verify the bundled starters

Both platform installers now run `install-starter-assets` as part of setup.
The command verifies the full allowlisted bundle and imports only the four
signed public actors and six public styles. Existing IDs/files are preserved.
Deliberately deleted assets stay deleted on subsequent installs, unless the user
explicitly asks to restore them. No assets are imported merely by starting the app.

Interactive installation shows the starter-cast public key and asks for signer
acceptance. For agent-assisted/noninteractive setup, obtain that acceptance as
part of the setup plan, then run:

```sh
bash install.sh --non-interactive --accept-starter-signer
```

```powershell
.\install.ps1 -NonInteractive -AcceptStarterSigner
```

Without the acceptance flag, noninteractive setup installs styles and reports
actors as `pending_signer`. Do not claim a full starter cast is installed while
acceptance is pending. To complete it after approval, or when the application
was installed directly with pip, stop the app and run:

```sh
.venv/bin/mondo-music-video install-starter-assets --non-interactive --accept-starter-signer
```

Use the same `MMV_HOME` or `--data-dir` as the intended app. The command reports
`installed`, `preserved`, `removed`, and `pending_signer` entries. To deliberately
restore starter assets removed through the GUI, add `--restore`; never add that
flag as routine setup/update behavior. Source checkouts and installed wheels
both include exactly the public starter assets.
If the user explicitly declines all starter assets, use the installer's
`--skip-starter-assets` option (PowerShell: `-SkipStarterAssets`).

The actor IDs are `animal_pig`, `robobabe1`, `henchman_1`, and
`human_female_casual_01`. The style IDs are `sun_bleach`, `nature_doc`,
`industrial_decay`, `noir_bw`, `gel_wash_psych`, and `crt_1990s`. See the
[starter cast](../examples/starter-cast/README.md) and
[style preset](../examples/style-presets/README.md) descriptions and manifests.
Never copy from another checkout or use a private roster as an install source.

## 5. Launch and give an honest readiness report

Start with `.venv/bin/mondo-music-video serve` (Windows:
`.\.venv\Scripts\mondo-music-video.exe serve`). Open or provide
`http://127.0.0.1:8091`. Inspect `/api/version`, `/api/status`, `doctor`, service
health and advertised model IDs. Confirm configured paths and required files.
Check that the active ComfyUI graph's nodes and selected model names are available.
An open web page or a green doctor report alone does not establish inference.

### Verify starters and local collection controls

Inspect `actors` and `styles` through the app and refresh the browser. Confirm
that the four actor IDs and six preset IDs are available in the cast/style
selectors, except for entries explicitly declined or previously deleted.
Report installed, preserved, removed and pending assets separately. No generation
is needed for this check. Explain that **Delete actor** and **Delete style** on
library cards remove unwanted local assets after confirmation. Deletion keeps
completed videos and exports and is blocked during production. Actors can be
exported through OAP before deletion. The app remembers deletions across restarts
and installer reruns, including deletion of the built-in Daylight style.

Report the URL, chosen models/services, private data location, how to start/stop
the app, and any blockers. Distinguish **installed**, **configured**, and
**generation verified**. Ask for a deliberate operator-approved small generation
only if needed to prove inference; do not run GPU or paid tests automatically.
If keys, hardware or runtime support are missing, say exactly what remains.
Do not leave the user believing a partially configured installation can generate.

## Reference writer downloads

These publisher metadata snapshots help form a reproducible proposal. Recheck
availability and terms before use; they do not override hardware inspection or
an existing user's choices. Sizes are bytes, not runtime memory requirements.

| Official repository / revision | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| [Qwen/Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/bc640142c66e1fdd12af0bd68f40445458f3869b) / `bc640142c66e1fdd12af0bd68f40445458f3869b` | `Qwen3-4B-Q4_K_M.gguf` | 2497280256 | `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5` |
| [Qwen/Qwen3-8B-GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF/tree/7c41481f57cb95916b40956ab2f0b139b296d974) / `7c41481f57cb95916b40956ab2f0b139b296d974` | `Qwen3-8B-Q4_K_M.gguf` | 5027783488 | `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785` |

Both Qwen models declare Apache-2.0 in their official model cards. Resolve URLs
use `https://huggingface.co/REPOSITORY/resolve/REVISION/FILENAME`.
For writer runtime configuration, consult the official
[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server).
