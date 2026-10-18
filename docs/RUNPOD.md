# Install Mondo Music Video on a RunPod Pod

Give an agent with terminal access to the Pod this instruction:

> Install this: https://github.com/hodgemann/mondo-music-video on this RunPod
> Pod. Follow docs/INSTALL_WITH_AGENT.md and docs/RUNPOD.md. Discover and reuse
> compatible existing components; install and configure what is missing. Put
> models and private data on persistent storage, set up private browser access
> and a restart recipe, and report what is needed for a verified first video.

The agent handles both a fresh Pod and an existing ComfyUI/PyTorch installation.
The user need not know which components are installed. Follow the main
[agent installation guide](INSTALL_WITH_AGENT.md), including combined download
approval, provider choices, starter signer acceptance and OAP verification.

This is a deployment procedure derived from the Linux implementation and current
RunPod documentation, checked 2026-10-18. **A clean RunPod installation has not
been tested by this project.** Linux RTX 4090 rendering and optional vision
judging were verified elsewhere; that does not certify an arbitrary Pod template.

## Discover, then choose a configuration

Use a persistent **GPU Pod** for the interactive studio. The application is not
a RunPod Serverless handler. An agent running on the user's laptop needs SSH
access to the Pod; one installed inside the Pod can work there directly. Never
request a private SSH key or provider secret in shared chat. Creating/renting a
Pod, resizing storage or selecting a more expensive GPU requires authorization.

Inspect the actual GPU/VRAM, host RAM, free disk, Python, FFmpeg/ffprobe, CUDA
availability in each relevant Python environment, mounted volumes, listening
ports and template startup processes. Read `nvidia-smi` and Torch's runtime
information; a driver advertising CUDA support is not proof that the selected
Torch build works. Python must be 3.11+ even if the template supplies an older
Python. Do not replace the template's system Python or driver.

Look in configured paths and conventional locations such as `/workspace` for
ComfyUI, model files, llama.cpp and saved MMV settings. Do not inspect unrelated
private collections. Inventory only the required components and ask for a path
if discovery cannot locate them. Then act on the findings:

| State found | Agent action |
| --- | --- |
| Working MMV and compatible services | Preserve data/configuration; verify the intended stack and browser access. |
| Existing ComfyUI or writer, incomplete MMV stack | Reuse working runtimes/models, install MMV in its own venv, add only missing approved components. |
| Fresh Pod | Select a compatible Python/CUDA environment, install approved prerequisites, ComfyUI/H3, writer and Laya, then configure MMV. |
| Incompatible existing runtime/models | Explain the mismatch; propose an isolated compatible environment/private workflow without replacing the existing installation. |

A generic ComfyUI template is not evidence of H3 compatibility. Check MMV's
actual graph and injection map, required node classes, model names and output
nodes against `/object_info`. Follow [LOCAL_MODELS](LOCAL_MODELS.md) and
[COMFY_SDK](COMFY_SDK.md); a stock image-generation workflow is insufficient.
Use matching reference-to-video H3 weights, text encoder and video/audio VAEs
from official sources. **Adapting and activating the workflow is the
agent's job**: follow [H3 workflow setup](H3_WORKFLOW_SETUP.md) for every chosen
variant, including model filenames, loader/precision options, required nodes
and any changed injection-map bindings. Validate the graph MMV builds, rather
than assuming the developer's graph matches the selected checkpoint. Do not copy example custom filenames as download URLs
or substitute a different graph without checking MMV's bindings.

Choose GPU, host RAM and disk together from the selected model inventory,
precision, offload strategy, passage length and resolution. Our 24 GiB RTX 4090
check used 736×416 output and a specific configured stack; it is not a guarantee
for full-resolution H3 on every 24 GiB Pod. More VRAM can reduce offloading but
does not remove host RAM/disk requirements. Reuse a compatible small writer or
select an API writer with consent; keep real Laya review. Consult current
[Comfy H3 guidance](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
and model terms before recommending downloads. Do not force an expensive writer
or optional vision stack just to reproduce the developer's machine.

## Persist the installation and private data

Inspect the mount before using `/workspace`: it is the default persistent path,
not a guarantee for every template. According to RunPod's
[storage documentation](https://docs.runpod.io/pods/storage/types), container disk
is ephemeral, a Pod volume survives stop/restart but is deleted on termination,
and a network volume persists independently. Choose storage before downloading;
network volumes must be attached when creating the Pod. Confirm the user's
intended stop/delete lifecycle and back up irreplaceable data separately.

Use a layout such as this on the verified persistent mount:

```text
/workspace/mondo-music-video/   checkout and app .venv
/workspace/mmv-data/           private MMV settings, credentials, actors, runs
/workspace/ComfyUI/            existing or approved new ComfyUI and its models
/workspace/mmv-runtime/        writer binaries/models and optional proxy state
/workspace/mmv-cache/          approved dependency/model caches
```

These are example destinations; preserve existing paths. Set `MMV_HOME` **before
installation**, starter import, configuration, doctor and every app/MCP launch:

```sh
export MMV_HOME=/workspace/mmv-data
```

Keep private directories owner-only on a private volume. Do not put credentials
or signing identities on a shared public mount. Include caches, temporary model
downloads, Python/Torch dependencies, Comfy outputs and generated videos in the
disk budget; model weights are only part of it. Record exact selected file sizes
and hashes, aggregate downloads, free-space headroom and terms in the approval
proposal. Configure persistent cache paths where useful, without overwriting
existing environment choices. Do not assume preinstalled Torch is visible in
MMV's isolated venv or skip its dependencies to save space.

Follow the main guide's noninteractive installer after approval. Install the
four authorized actors and six styles by default, with explicit signer
acceptance, and verify them in this same `MMV_HOME`. Keep ComfyUI's runtime
separate; preserve its existing nodes and model files. Pin and record the
chosen container image, Python/runtime versions, ComfyUI/node revisions and
model hashes in private installation notes so a replacement Pod is reproducible.
A persisted venv may require rebuilding if the replacement image/Python changes.

## Private browser access

MMV's supported launcher binds to `127.0.0.1:8091`; it has no `--host` option.
The app also checks localhost Host headers and same-origin mutations. Merely
adding `8091` to RunPod's HTTP ports does not make this installation accessible.
Do not remove these guards or expose the unauthenticated studio publicly.

Use **full SSH over exposed TCP**, with a public IP, SSH daemon and SSH key,
as described in [RunPod's SSH guide](https://docs.runpod.io/pods/configuration/use-ssh).
Use the current endpoint from the Pod's Connect panel. On the user's computer,
add local forwarding to that command (replace the uppercase placeholders):

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:8091:127.0.0.1:8091 \
  -p SSH_PUBLIC_PORT -i /path/to/private-key root@POD_PUBLIC_IP
```

Then open **http://127.0.0.1:8091** on that computer while the tunnel is running.
If local port 8091 is occupied, use `-L 127.0.0.1:18091:127.0.0.1:8091` and open
`http://127.0.0.1:18091`. Update a local agent's `MMV_URL` accordingly; an agent
inside the Pod still uses port 8091. Verify forwarding works; do not assume the
basic `ssh.runpod.io` terminal gateway provides full forwarding capabilities.
If the Pod lacks full SSH, arrange authorized full SSH access before declaring
browser access ready.

Only SSH needs public exposure for this route. Keep writer, ComfyUI, optional
vision and SDK proxy on Pod loopback too. RunPod's
[HTTP proxy documentation](https://docs.runpod.io/pods/configuration/expose-ports)
states that exposed services are public and have a 100-second timeout; its HTTPS
URL is not application authentication. A public proxy deployment would require
a separately reviewed authenticated access design.

## Start, restart and prove readiness

Run the app with the approved environment in a persistent terminal session or
an explicitly configured process supervisor; do not rely on the web terminal
staying open. For example, inside a persistent session on the Pod:

```sh
cd /workspace/mondo-music-video
export MMV_HOME=/workspace/mmv-data
.venv/bin/mondo-music-video serve
```

Create a private restart script/record using the actual paths. Record app and
service log locations, interpreter paths, working directories, startup order,
and how to stop each owned process. Do not replace the template's entrypoint or
start a second app over an active production. Container services usually do not
use systemd; inspect the template's supervisor before choosing one. After a Pod
reset, restore required OS prerequisites, recreate incompatible environments,
start services and recheck the current SSH endpoint/tunnel.

Configure managed writer and ComfyUI launch commands with their own absolute
interpreters and working directories to avoid simultaneous GPU residency.
If a template automatically starts/restarts ComfyUI, preserve that behavior for
ordinary rendering. Optional **Vision quality check** is off by default; leave
it off for initial setup unless requested. Enabling it requires a compatible
local vision model/projector and Mondo ownership of ComfyUI. Arrange an approved
supervisor change so it will not respawn ComfyUI during the vision swap; never
silently kill external services. The SDK path additionally needs the approved
SDK extra and a separately running proxy with persistent state; direct local
H3 does not require that proxy.

Before handoff, verify through the tunnel: live `/api/version`, idle status,
Settings, song upload, actor/style selectors and a production preview. Check
writer health/model, Laya files/device, ComfyUI graph/node/model compatibility,
and proxy health if selected. Verify the startup recipe uses the same data
volume and does not import duplicate starters. A provider model listing is not
a generation test.

With deliberate operator approval, run a small song excerpt through MMV's
normal preview/consent flow using an authorized starter actor. Inspect prompt
review, renderer receipt, final video/audio, frame count, quality warnings and
playback/download through the tunnel. Record the result and versions. Report
**installed**, **configured**, and **generation verified** separately; if no real
test was authorized, say generation remains unverified. Do not substitute a
ComfyUI-only test for the complete MMV path.

**Cloud compute is paid even when MMV's local-renderer quote says $0.** Include
Pod GPU time during installation, downloads, testing and idle time, plus storage
and any API provider charges in the handoff. Get a budget before provisioning
or testing, consult current RunPod pricing, and explain the approved shutdown
procedure and which storage survives it. Stopping MMV or closing the tunnel
does not stop Pod billing. Do not terminate a Pod or delete a volume without
explicit authorization and a backup check.
