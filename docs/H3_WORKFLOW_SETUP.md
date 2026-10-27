# Configure the selected H3 workflow during agent installation

This is a required part of [agent installation](INSTALL_WITH_AGENT.md) whenever
local H3 is selected, on RunPod or any other machine. **The installing agent
must adapt and activate the workflow for the user's chosen model stack.** Do
not ask the user to edit JSON or assume they use the developer's models. Apply
this procedure to existing models as well as fresh downloads.

The shell installer installs the app. It does not detect model compatibility or
convert arbitrary H3 workflows. The agent performs the adaptation below using
the existing private workflow/injection-map support. No particular alternative
H3 variant is certified merely by following these instructions.

## Establish the selected stack

1. Discover existing ComfyUI/runtime/model paths and the active MMV workflow map.
   Read the current graph and model choices. Ask which H3 variant the user wants
   if they have not selected one; offer hardware-appropriate choices. Preserve
   the owner's defaults and all unrelated workflows.
2. Identify the exact model family, revision, precision and format, not just a
   filename containing `h3`. Read the publisher's model card and matching
   [official ComfyUI H3 workflow guidance](https://docs.comfy.org/tutorials/video/minimax/minimax-h3).
   Record the required diffusion loader, text encoder, video/audio VAEs, runtime
   versions, attention/quantization support and any required additional nodes.
   Check reference-image and song-audio conditioning, output FPS and frame lattice.
   A text-to-video or image-to-video checkpoint/workflow is not automatically a
   replacement for MMV's reference-to-video path.
3. Read the actual ComfyUI `/object_info` schema, installed model lists and node
   startup errors. Establish which required loader classes, model names and
   input options this installation supports. A model listing proves discovery,
   not that the weights load or the model supports the workflow. If a runtime,
   node or weight is missing, include it in the combined download/terms approval;
   install the approved missing components and inspect again.

Quantization may be encoded in the checkpoint and handled by the same loader;
do not invent a precision override based on a filename. Conversely, a different
format may need a different loader/node package. Use the documented loader and
options for the exact checkpoint and installed runtime. Never rename a model
to the developer's filename or silently substitute a different variant.

## Derive and activate a private graph and map

For a same-structure selection, use Settings or `PUT /api/settings` with the
chosen `h3_models` entries. The roles are `diffusion_model`, `text_encoder`,
`video_vae` and `audio_vae`; submit exact installed model names. Read current
Settings first and preserve unrelated values. The API creates a private graph
and map under `MMV_HOME/config` and updates `workflow_map_path`. See
[MODEL_SETTINGS](MODEL_SETTINGS.md). This mechanism changes filenames only;
it deliberately preserves existing precision options and custom nodes. The exception
is a bundled diffusion model whose preset has a different step count from the saved
workflow: its own bundled workflow is used instead, keeping the other chosen models.

When the selected variant needs other changes, the agent must make them too:

1. Work while the app is stopped, or use its idle-only Settings API for
   activation. Never edit an active production's graph. Copy the selected graph
   and map to uniquely named files under the intended `MMV_HOME/config`; keep
   the originals. Use API-format graph JSON, not a UI canvas export.
2. Set all four selected model roles in the copy. Adapt documented loader class
   and input names, encoder type/device, precision, attention nodes and required
   graph connections. Preserve unrelated operator customizations. Do not import
   private models or metadata from a sibling studio checkout.
3. If nodes or sockets change, update the private injection map as well. Trace
   every target to its real node/input: prompt, duration, seed, dimensions,
   steps/sampler/scheduler and output prefixes. Trace `reference_node`, image
   and audio reference socket prefixes, loader templates, limits, pruning and
   generated-node ID range. Node IDs from the bundled graph are not universal.
   Maintain reference-tag numbering and the image/audio conditioning path
   through the actual sampler. Ensure both video and audio output nodes remain
   usable by the selected direct or SDK backend.
4. Put the private graph's absolute path in the map's `workflow` field and
   activate the map's absolute path as `workflow_map_path`. On an offline edit,
   preserve all other settings and use the same persistent `MMV_HOME` as the app.
   Restart the app and read Settings back. Do not merely leave a corrected graph
   on disk while MMV still points at its old map.
5. Record original and derived paths, selected model revisions/hashes, runtime
   and node versions, and a short parameter/connection diff in private setup
   notes. Keep a rollback path. Recheck any model dropdowns against the newly
   activated graph; ambiguous/custom loaders may not appear in those controls.

Keep MMV's musical timing, actor references, song slicing and output assembly
contract intact. The ordinary local H3 and SDK paths currently inject **20
steps** (`LocalH3Backend.capabilities` and `ComfySdkH3Backend.render_segment`).
Changing only a graph's saved step value will not override that. If a selected
variant needs a different sampling schedule, frame lattice, conditioning or
output contract, explain and implement the necessary scoped adapter/runtime
change with mock tests before claiming compatibility. Do not silently fall
back to another checkpoint or strip the unsupported feature. Preserve explicit
paid consent, no automatic paid resubmissions and OAP verification.

## Validate the workflow MMV will actually submit

Before GPU work, load the activated map with
`mmv.engine.comfy.WorkflowBuilder.load(map_path, engine_root)` and build a graph
using synthetic filenames, a representative prompt/seed/duration/resolution,
one image reference, one song-audio reference and the backend's effective step
value. Building a graph does not submit it. Inspect the result, not only the
saved base graph:

- Every mapped target exists and receives the intended value; model names,
  loader options and required node classes match this ComfyUI's schema.
- Image and song references remain connected to the conditioning used by the
  sampler, with correct resolved `<Picture N>`/`<Audio N>` tags. Repeat for
  the actual selected reference count and any no-image mode the install will use.
- Links point at existing nodes and the expected output sockets; pruned template
  nodes and dynamically generated reference loaders leave no dangling links.
- Selected models and precision options survive graph building, and the selected
  backend can discover/download both video and audio outputs. The SDK/proxy has
  additional output requirements described in [COMFY_SDK](COMFY_SDK.md).

These are structural checks, not proof of inference. Do not call ComfyUI's
`POST /prompt` as a validation probe: it queues real GPU work. Obtain deliberate
operator approval (and a RunPod rental budget where applicable), then run a
small complete MMV production via normal preview/consent. Check model loading,
actual renderer graph/receipt, references, frame count, final video/audio and
quality warnings. Report the selected stack and what passed. If real inference
was not approved or failed, say exactly what remains unverified and fix the
specific compatibility issue before calling the installation ready.
