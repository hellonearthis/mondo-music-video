# Comfy SDK H3 — 1.6.0

Mondo can run its existing H3 workflow through the official Comfy Python SDK
and the official Comfy API v2 proxy. Select **H3 / Comfy SDK (local proxy)** in
the music-video or ident renderer menu. The direct local renderer remains the
default. Planning, reference tags, prompt review, sampler settings and final
assembly use the existing engine.

## Install and connect

From this repository, in your Mondo virtual environment:

```sh
python -m pip install '.[comfy]'
```

This extra pins both official packages to inspected commits:

| Component | Source revision |
| --- | --- |
| [Python SDK](https://github.com/Comfy-Org/comfy-python-sdk) | `6d2dd7233dfa0a1abdf199beada55b2282e26b44` |
| [API proxy](https://github.com/Comfy-Org/comfy-api-proxy) | `1569dc17ec0dd293d4b9a0723e142204dacedb85` |

Start your existing ComfyUI with its installed H3 models and nodes. In another
terminal, start the proxy with a persistent state directory outside the repo:

```sh
comfy-api-proxy --comfyui http://127.0.0.1:8188 --port 8189 --state-dir /path/to/private/comfy-proxy-state
```

On Windows, use a user-owned native path for `--state-dir`. Keep that directory
between launches: it holds job records, asset mappings and the output signing
secret needed for recovery. ComfyUI's own history and output files must also
remain available.

In Mondo Settings, set **Local Comfy API proxy URL** to
`http://127.0.0.1:8189`. If you started the proxy with `--token`, save that token
under **MMV_COMFY_API_KEY** in Provider keys. The app stores it in its private
credential file and returns only whether it is configured. Ambient
`COMFY_API_KEY` and `COMFY_BASE_URL` do not override Mondo's explicit settings.

Choose the SDK renderer in the production form. Mondo uploads ordered reference
images and a WAV slice of each passage through the SDK's asset interface, submits
the injected graph, polls the job, and downloads outputs into its run directory.
Mondo needs no shared ComfyUI input/output folder for this path. The proxy itself
forwards media to your ComfyUI installation.

This release accepts only loopback proxy URLs. It does not connect to Comfy
Cloud, managed deployments or Router. The SDK renderer has no platform API
charge; a separately configured API writer still appears in the production
quote and requires consent. With the vision check off, start both ComfyUI and
the proxy yourself.

With **Vision quality check (slower)** enabled (`vision_quality_check: true`,
off by default), configure `comfy_launch` and close ComfyUI before preview.
Mondo launches ComfyUI even on the SDK path, then stops its own ComfyUI process
to load the local vision-capable writer model with mmproj. If a vision-triggered
free retry is needed, it restarts ComfyUI and then judges the retry batch.
The proxy on 8189 can stay running and remains operator-managed. External
ComfyUI is never stopped; preview rejects it, and a startup race produces a
visible skip note. This adds model loading and judging time. Vision startup
failure leaves pixel checks active and reports a warning. No paid retry occurs.

## Workflow and environment

The bundled workflow is unchanged from the original repository. Its SHA-256 is
`183464728c108a17f0205519cf3340d76118c6a8e9d58313ceb47664e16acc88`.
The injection map remains `mmv/engine/config/injection_map.json`; a custom
`workflow_map_path` configured through setup is supported and included in quote
invalidation and per-segment recovery fingerprints.

Use an installation that can run that graph, including `MiniMaxH3ReferenceToVideo`,
`ComfyMathExpression`, the core video/audio nodes and `VHS_VideoCombine`.
Model filenames remain those in your existing workflow. No models, third-party
nodes or GPU runtime are installed by the SDK extra. The built-in graph also
saves VHS video output; the pinned proxy exposes its `gifs` output as a video
asset. A custom graph must expose a video asset through the proxy's supported
output mappings. `SaveVideo` alone with an unrecognized native output key is
insufficient for this proxy revision.

For reproducible real rendering, record your ComfyUI commit, each installed
custom-node commit, model filenames and hashes, and any private workflow-map
changes alongside your operator notes. Those GPU environment versions have not
been verified for this integration; the SDK/proxy pins do not pin your ComfyUI
installation. Obtain models from their original sources under their terms.

## Receipts, cancellation and recovery

Each passage has `runs/RUN_ID/renders/segNNN/comfy-request.json` containing the
endpoint, SDK revision, input fingerprint, idempotency key, state and job ID.
Its neighboring `workflow.json` records the submitted graph with asset IDs.
Credentials are not written into either record. Output filenames are chosen
locally; filenames returned by the service are never used as filesystem paths.

The official SDK's high-level `Comfy.submit()` retries some 429 responses
independently of its model retry policy. Mondo instead uses the official SDK's
`ComfyLow.post_jobs()` once, together with its `AssetFactory`, `JobFactory`,
`Job` and output downloads. There is no submission retry or provider fallback.
A receipt is saved **before** the POST so an interrupted process cannot silently
submit that passage again.

If a connection drops before a usable job ID is saved, the receipt is marked
`unknown` (or remains `submitting` after process termination). Check the proxy's
job list/history and idempotency key before doing anything else. Mondo refuses
automatic resubmission. A rejected 429 is also retained conservatively rather
than retried. Keep the receipt; do not delete it to force generation.

For a known running/completed job or a failed download, select **Review resume**
in Mondo's operation controls, review the new preview, accept it and start.
A validated local completion can now recover even when the proxy's job expired,
without querying or submitting to the proxy. This requires matching input and
receipt bindings, confined local paths, a matching media hash, decodable media
and enough frames. Invalid local completions fall back to the receipt recovery
rules below.

Original media, settings, workflow and actor permissions are rechecked. The
writer and Laya are not rerun: recovery uses the already validated prompts.
Existing job IDs are polled/downloaded; only passages never submitted may start
new local generations. Completed media downloads can be repeated without
regenerating their clips. Failed, canceled or expired jobs are never silently
replaced. A fully completed production cannot be resumed.

The same preview/consent flow is available via CLI:

```sh
mondo-music-video-agent preview-resume RUN_ID
mondo-music-video-agent start RETURNED_QUOTE_ID --consent
```

MCP exposes `preview_resume`; use its quote with `start_production` only after
operator authorization. The studio continues to allow one active operation and
has no production queue.

Cancel stops the Mondo worker and requests cancellation only for its recorded
Comfy job IDs. If the proxy cannot confirm cancellation, its receipt retains
`cancellation_unconfirmed`. A submission whose response was lost has no known
job ID and requires operator reconciliation. Cancellation is a request, not a
guarantee that ComfyUI has stopped.

## Verification

```sh
python -m pip install '.[comfy,mcp,test]'
python -m unittest discover -s tests -v
node --check webapp/app.js
bash -n install.sh
```

The Linux development check passed all 56 tests, including cached Chromium
and the actual SDK/proxy transport test. The 1.0.11 wheel also built successfully.
Tests use temporary data, synthetic media and fake credentials. They exercise
the actual official SDK over HTTP, including reference/audio upload, graph
injection, assembly, receipt recovery, response loss, no hidden 429 retry,
cancellation, OAP rejection before upload, stale settings and credential
redaction. A separate test runs the actual official proxy against a synthetic
native ComfyUI server. When Playwright and cached Chromium are available, a
browser test covers renderer selection, upload, preview, consent, failed-download
recovery and playback at desktop/mobile widths. No test performs paid, GPU or
Topaz generation.

## Operator render verification

For a deliberate real check, start your compatible ComfyUI and proxy, use a
short song and permitted reference, select the SDK renderer at a small
megapixel size, review the quote and start from the UI. Confirm that Laya
finishes before rendering, a receipt records the proxy's job ID, the proxy shows
that job, and the final video plays with the original song and planned duration.
Save the run's receipt and workflow plus a screen recording of the SDK renderer
selection, proxy job and final output. Keep media and private state outside Git.

Earlier SDK GPU runs are recorded in [verification](VERIFICATION.md). The 1.6.0
vision swap/retry path still needs a deliberate operator GPU check; automated
transport/assembly checks do not establish model quality or GPU compatibility.

The [Comfy announcement](https://blog.comfy.org/p/comfy-api-is-live-deploy-comfyui)
and [official proxy guide](https://docs.comfy.org/development/comfyui-server/api-proxy)
document SDK access to self-hosted ComfyUI. This implementation uses that SDK
for workflow execution, asset uploads, job status and output downloads.
