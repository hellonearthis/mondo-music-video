# Install Mondo Music Video on another rented GPU machine

For GPU hosts other than RunPod: container-style marketplaces such as **Vast.ai**, and full-VM hosts such as **Lambda
Cloud, TensorDock, Paperspace, Hetzner or OVH GPU servers, AWS, Google Cloud and Azure**. Give an agent with terminal access to
the machine this instruction:

> Install this: https://github.com/hodgemann/mondo-music-video on this rented GPU machine. Follow
> docs/INSTALL_WITH_AGENT.md and docs/GPU_CLOUD.md (and docs/RUNPOD.md for the shared Pod rules). Discover and reuse
> compatible existing components; install and configure what is missing. Put models and private data on storage that
> survives my stop/delete plan, set up private browser access and a restart recipe, and report what is needed for a
> verified first video.

**This procedure is derived from the RunPod guide and general Linux practice. This project has not tested a clean
installation on any of these hosts.** Provider details change often: read the provider's current documentation and the
machine's own connection information instead of trusting remembered steps, and say what you could not verify. All rules
of [INSTALL_WITH_AGENT.md](INSTALL_WITH_AGENT.md) apply (tiers, single approval, no secrets in chat, starter-cast signer
acceptance) as do the Pod rules in [RUNPOD.md](RUNPOD.md): persistent GPU machine, loopback services, SSH-forwarded browser
access, private data under `MMV_HOME`, `installed` / `configured` / `generation verified` reported separately.

## What kind of machine is this?

Find out before deciding anything, and tell the user which kind it is. **The columns below are tendencies, not promises:** the
product, image and access mode each host sells decide storage, supervision, SSH and pricing, and the same provider can offer both
kinds. Confirm every cell for the actual product from its current documentation and by inspecting the machine; where you cannot,
say so.

| Question | Container-style host (Vast.ai and similar) | Full VM (Lambda, TensorDock, Paperspace, cloud VMs) |
| --- | --- | --- |
| What survives a stop or restart? | May be only the volume attached to the instance | The VM disk often survives stop; instance-local NVMe may not |
| What survives deletion? | Possibly nothing unless a separate volume was attached | Boot-disk deletion policy, snapshots and attached volumes differ by provider: check the exact setting |
| Process supervisor | Possibly none, or the template's supervisor | systemd is common |
| GPU driver / CUDA | Usually provided by the image or host | May need installing (see the rule below) |
| Interruptible / spot pricing | Offered by some hosts: the instance can be taken away mid-production | Offered by some. An interruption loses the run in progress |
| Access | SSH, possibly to a mapped port, possibly as root | SSH to the VM's address, with a user such as `ubuntu` |

**Drivers and system software.** On a fresh VM the user created for this purpose, installing a missing GPU driver may be necessary:
explain the exact need and get approval first. On any machine built from a template or image that already provides a working driver,
Python or CUDA, do not replace them (see RUNPOD.md); add an isolated environment instead.

Prefer **non-interruptible** capacity for a production, but do not promise that any capacity is immune from loss: say what the
provider documents. If the user chooses an interruptible instance, warn that a reclaim can destroy the run in progress and
anything not on persistent storage.

## Discover, then choose a configuration

Follow the discovery and decision table in [RUNPOD.md](RUNPOD.md) ("Discover, then choose a configuration"): inspect the GPU,
free VRAM, host RAM, free disk, Python 3.11+, FFmpeg/ffprobe, CUDA from the Python environment that will run it, mounted
volumes, listening ports and existing ComfyUI, models, llama.cpp and saved MMV settings. Reuse working components (see "Use what
the user already has" in the install guide). A generic image or template is not evidence of H3 compatibility: check the real graph
and injection map against ComfyUI's node list ([H3 workflow setup](H3_WORKFLOW_SETUP.md)). Read `nvidia-smi` and Torch's runtime
report; a driver advertising CUDA is not proof that the installed Torch build works.

Rented GPU time is paid whether or not a video is being made, and stopping Mondo or closing the tunnel does not stop it. Get a
budget before provisioning, installing or testing, and include GPU time (also while idle, downloading and testing), storage,
any data-transfer charges and API provider charges. A budget is a spending limit, not authorization for every action: do not
create, resize, stop-and-keep or destroy an instance, change a payment setting, or pick a more expensive GPU without explicit
authorization for that action. Name the exact way to stop and to delete, and what keeps billing afterwards (disks and reserved
volumes often do). Large clouds often have GPU quotas that block a new account: say so rather than retrying or switching region
or provider on your own.

## Persist the installation and private data

Verify which path survives the user's plan before downloading anything, then use the RunPod layout with that path instead of
`/workspace`:

```text
<persistent>/mondo-music-video/   checkout and app .venv
<persistent>/mmv-data/            private MMV settings, credentials, actors, runs   (export MMV_HOME=...)
<persistent>/ComfyUI/             existing or approved new ComfyUI and its models
<persistent>/mmv-runtime/         writer binaries/models and optional proxy state
```

Set `MMV_HOME` before installation, starter import, configuration, doctor and every launch. Keep private directories owner-only.
Include caches, temporary downloads, Python/Torch, Comfy outputs and generated video in the disk budget. Pin and record the image or
OS, Python, ComfyUI and node revisions and model hashes in private notes so a replacement machine can be rebuilt. Back up
anything irreplaceable (the actors, `MMV_HOME`, finished videos and their packages) off the machine before stopping or deleting it,
verify the copy completed, and confirm the provider's exact deletion policy before any destructive step.

## Private browser access

MMV binds to `127.0.0.1:8091` and has no public mode; do not remove its Host and same-origin guards or expose it. Use SSH local
forwarding from the user's own computer, with the address, port and login the provider's connection panel shows:

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:8091:127.0.0.1:8091 \
  -p SSH_PORT -i /path/to/private-key SSH_USER@MACHINE_ADDRESS
```

Then open **http://127.0.0.1:8091** on that computer while the tunnel runs. Verify that the machine really offers full SSH
forwarding (an SSH daemon the user can reach with a key, and the expected host identity) before declaring browser access ready; a web
terminal alone is not enough. If local port 8091 is taken, forward `127.0.0.1:18091` instead and set a local agent's `MMV_URL` to match
(an agent running on the machine still uses 8091). Never ask for the private key in shared chat.
Do not open port 8091 in a firewall, security group or the provider's HTTP proxy: those make the unauthenticated studio public.
Keep the writer, ComfyUI, vision and proxy on the machine's loopback too.

## Start, restart and prove readiness

Run the app under what the machine really offers: a `systemd` service on a VM (ask before creating one), or a persistent terminal
session or the template's supervisor on a container host. Write a private restart recipe with the actual paths, interpreters and
startup order, and how to stop each process you own. Preserve the image's own entrypoint and any supervisor already running, and never
start a second app over an active production. After a reboot or replacement, restore prerequisites, rebuild incompatible
environments, restart the services and recheck the tunnel.

Prove it in the same order as the RunPod guide: live `/api/version`, idle status, Settings, song upload, actor and style
selectors and a production preview; writer health, Laya, ComfyUI graph and model compatibility; then, with deliberate operator approval,
one small excerpt through the normal preview and consent flow with an authorised starter actor. Inspect the prompt review, renderer
receipt, final video and audio, quality warnings and playback through the tunnel. A model listing is not a generation test.
Check the frame count, that the video downloads and plays through the tunnel, and record the versions and results. If the optional
vision quality check is wanted, Mondo must own ComfyUI for that production, so arrange an approved supervisor change that will not
respawn it; if the Comfy SDK path is used, check the proxy's health and persistent state. Keep the app's own safeguards in view: one
active operation at a time, explicit consent before any paid work, and no automatic paid retries or provider switching after a
failure. If no real test was authorised, report that generation remains unverified.

## Poor fits (explain, do not force)

- **Google Colab, Kaggle and similar notebooks.** Sessions are time-limited and shared, and running a long-lived web service is often
  restricted by their terms. They are not a good home for an interactive studio.
- **Serverless GPU functions** (Modal, Replicate and similar). Mondo keeps a model resident across passages and runs one stateful
  operation at a time; it is not a request-per-call function.
- **Comfy's hosted platform.** That is a renderer choice (the Comfy SDK and Router), not a place to install this app. Treat it as a
  provider option under [API_PROVIDER_SETUP.md](API_PROVIDER_SETUP.md) and say what has and has not been verified.
