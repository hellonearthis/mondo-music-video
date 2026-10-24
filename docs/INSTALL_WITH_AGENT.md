# Install this with an agent

The user-facing instruction is simply:

> Install this: https://github.com/hodgemann/mondo-music-video

This is the installation handoff for an agent with terminal/filesystem access.
Do the work, including choosing and configuring suitable models. Ask the user
only for material choices, credentials and download approval. Do not hand back
a list of commands for them to run when you can run those commands yourself.
This guide directs the agent; the shell installer itself does not automatically
select or download a complete model stack.

For RunPod installations, also follow [the RunPod handoff](RUNPOD.md); for other rented GPU machines (Vast.ai, Lambda, TensorDock, Paperspace and
the big clouds) also follow [the rented GPU machine guide](GPU_CLOUD.md), and for RunPod too where it applies. Discover
and handle both fresh Pods and existing stacks; do not require the user to
inventory them. Set persistent data/model locations before installing, arrange
SSH browser forwarding, and account for cloud rental charges even when the
local-renderer quote is $0. A Pod-specific end-to-end test is still required
before claiming generation is verified.

## Install tiers

Early on, ask which install the user wants. Offer these three by name:

| Tier | What it installs |
| --- | --- |
| **MINIMUM GOOSE** | Bare bones: the app, one writer, local Laya review and one renderer. None of the optional parts: no stem separation, lyrics detection, vision quality check, starter cast or style presets. Choosing it counts as declining the starter cast and styles; they can be added later. |
| **CHOOSE-YOUR-GOOSE** | The default when the user does not pick. Go through the optional parts one at a time (the starter cast and styles, stem separation, lyrics detection, the vision quality check), explain each in plain words, recommend a choice from the detected hardware, and install only what they pick. |
| **MAXIMUM GOOSE** | Every optional part the machine can run: starter cast and styles, stem separation with all its models, lyrics detection and the vision quality check. Still check the hardware: skip or warn about anything the machine cannot run well, and say why. |

Every tier still needs the single download approval described below, with sizes,
destinations and terms listed for everything that would be downloaded, including
MAXIMUM GOOSE. Approval is never implied by the tier name. No tier installs Topaz
(user-owned) or starts paid work. Say which tier was installed in the readiness
report, and tell the user they can add skipped parts later.

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

### Use what the user already has

Many users, including friends of the project, already run their own H3 and their own language models. Look for these
first and build the plan around them; the answer to "what should I download?" is often "nothing".

- **H3 / ComfyUI.** Find existing ComfyUI folders (ask where; check conventional locations and any path the user gives), the
  H3 model and text-encoder files they use, and the custom nodes their graph needs. Keep their files and workflows untouched and
  adapt a private copy of the Mondo graph to what they have ([H3 workflow setup](H3_WORKFLOW_SETUP.md)); a different quantisation,
  loader or node pack is normal, not a reason to download a second copy. Confirm with a built submission graph before any inference.
- **Writer and vision language models.** Ask which tools they already run. Anything that serves an OpenAI-compatible
  `/v1` API works as a writer or vision service: llama.cpp's `llama-server`, Ollama, LM Studio, vLLM, KoboldCpp, text-generation-webui
  and similar, each with its own conventional port. With the user's consent, check loopback addresses only, ask the service for
  its model list (`/v1/models`) and report what you found; do not assume a default port is theirs. A model listing is not a
  generation test: send one real request and check the JSON the writer returns before calling it ready. Also reuse model files already
  on disk (for example a GGUF in another tool's folder) instead of downloading again, and tell the user the vision-capable ones.
- **Whisper and other add-ons.** Reuse an existing Whisper environment and model files before proposing anything (see lyrics detection).
- **Say it in the plan.** The single approval proposal lists what is being reused, with its location, separately from anything to be
  downloaded, so the user sees that their existing setup is being respected.

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

### Optional: instrument analysis (stems)

Music-video planning can follow one instrument instead of the whole mix. This is
an optional add-on; **do not install it unless the user wants it**, but do tell
them it exists and ask. Explain it plainly: "Mondo can plan the cuts from just the
drums, bass, vocals or other instruments, and it lets you fix the beat grid and
sections before generating. Following an instrument needs a small add-on (Demucs,
MIT) that separates the song into parts. Want me to set it up?"

Recommend by what the machine can do. Read `inspect_studio` kind `stems` (after the
app is running) or the hardware you already inspected: it reports the GPU, free
VRAM and RAM and a ready-made `recommendation`. Measured figures (RTX 4090 and CPU):

| Model | Download | When to offer it |
| --- | --- | --- |
| Standard 4-stem (`htdemucs`) | 81 MB | Recommended to everyone. Drums, bass, vocals, other. About 8 s per 4-minute song on a GPU, about 70 s on CPU. |
| High-quality 4-stem (`htdemucs_ft`) | 324 MB | Optional. 2 to 3 times slower; cleaner (less stray sound in a stem) on some songs, no better on others. Worth offering when a GPU with about 3 GB free is present; on a CPU-only machine offer it only if the user hears stray sounds. |
| 6-stem (`htdemucs_6s`) | 53 MB | Only if the user wants guitar or piano. Piano is the least reliable. It was noisier than the 4-stem model on vocals, so it is never used for them. |

Separation needs about 1.2 GB of VRAM (any model, any song length) and uses the GPU
only when about 3 GB is free, otherwise the CPU (no VRAM, 2 to 3.5 GB of RAM). Warn
below about 6 GB of system RAM. Stems are analysis input only: the video keeps the
original audio. If the user has a small GPU that ComfyUI already fills, expect CPU.

Install and download only after the user approves, and list them in the single
download proposal with the other items: `pip install demucs` (about 20 MB; it
reuses the installed torch) plus the chosen model sizes above. Never start the
model download for the user without that approval; the app's editor and
`POST /api/stems/prepare` need `consent: true` that only the user gives. After
approval, verify with `inspect_studio` kind `stems` that the chosen models show
`ready: true`. Do not equate a successful install with tested separation: preview
a real song with an `analysis_driver` (see AGENT_SETUP.md) before saying it works.

### Optional: lyrics detection (for lip-sync mode)

Lip-sync mode needs the sung lines and their times. Detecting them automatically is an optional
add-on (Whisper, MIT); the user can always type or paste lyrics and set times by hand. Ask: "Do you want
automatic lyrics detection? It listens to the song, writes down the words with their times, and
you can fix any line." Recommend from the hardware (`inspect_studio` kind `lyrics` reports the GPU,
free VRAM, RAM, which models are already on disk and a recommendation). Measured with the existing
large-v3 (3.1 GB): about 10.2 GB of VRAM and 46 s per minute of song on a GPU, or about 164 s per minute on
a CPU, so it uses the GPU only when it fits in free memory. Smaller models (tiny about 75 MB, base about
145 MB, small about 470 MB, medium about 1.5 GB) are faster and fit smaller GPUs, but their accuracy on
singing has not been measured: do not claim they are as good. Detection is best on the isolated vocals,
so offer it together with stem separation. Reuse an existing Whisper environment and model files when
the machine has them (`MMV_LYRICS_PYTHON`, `MMV_WHISPER_DIR`) before proposing any download. Install and
model downloads follow the single approval and are listed with sizes, like every other optional part.

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
leaving shipped graphs and existing user workflows unchanged. **The agent must
adapt and activate that graph for the selected H3 stack**, including required
loader, precision, node and injection-map changes; follow
[H3 workflow setup](H3_WORKFLOW_SETUP.md). A filename change alone is not a
compatibility check. Review the
[MiniMax license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE),
including its commercial-use conditions. Do not promise a commercial license.

Supported hosted renderer choices are listed in the README. Explain provider
costs, account/key requirements and media upload implications before choosing
one. A hosted renderer still needs the writer and local Laya setup.

## 3. Obtain one clear download approval

Present a compact proposal listing each new model/runtime, source, exact bytes
where published (otherwise an explicit estimate/unknown), local destination,
license/terms link, aggregate download and free disk space with headroom. Separate
existing/reused files from downloads. Include dependency downloads and, if the
user chose instrument analysis, the Demucs add-on and each stem model with its size. Explain why
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
commands. For every local H3 installation, complete
[H3 workflow setup](H3_WORKFLOW_SETUP.md) for the chosen stack, whether existing
or newly downloaded. Activate its private map and inspect a built submission
graph before the operator-approved inference test. Stop the app
before offline settings edits; preserve unrelated settings. Avoid concurrent
GPU residency where possible: managed writer/render services can be sequenced
by the app. Leave automatic updates off unless the user requests them.

Credentials belong in the application's private credential storage, never Git,
shell history, shared reports or committed settings. Ask the user to enter
secrets through the Settings UI when practical. Do not create accounts or spend
money as part of an installation request.

### Open Prop Protocol

Open Prop Protocol v0.2 support (v0.1 packages also import) is part of the application dependency set. It
does not require model weights or automatic prop downloads. Verify that the app
catalog reports `opp_version` and that `GET /api/props` works. The owner may
later choose a `.opp` file; inspect its manifest, hashes and signer, obtain
explicit acceptance of that exact signer key (or the separate unsigned-draft
choice), then import it into the private prop library. Do not import sibling
project examples or local/private props merely because they are available.

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

Start with `bash start.sh --background` (stop with `bash stop.sh`; it runs this checkout's code, which `.venv/bin/mondo-music-video serve` alone may not) (Windows:
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
