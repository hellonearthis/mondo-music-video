# Model settings and local path browsing — 1.0.12

Settings offers dropdowns for the active H3 video VAE, audio VAE, diffusion
model and text encoder. The existing workflow's choices remain selected even
when ComfyUI is offline or its model list cannot be retrieved. No alternative
model becomes a default automatically.

The app asks the configured direct ComfyUI URL for its loader model lists.
If a category is unavailable, it looks under the parent of your configured
ComfyUI input folder, in `models/vae`, `models/diffusion_models` or
`models/text_encoders`. The two VAE roles share ComfyUI's VAE inventory.
Current models not found in that inventory are labeled “current; not detected.”
They remain usable as existing selections; new selections must be reported
installed. For the SDK renderer, discovery still uses the direct ComfyUI URL
or the configured local folder, not the proxy's job API.

These are installed filenames, not a guarantee of H3 compatibility. Choose
weights that match your workflow and hardware. In particular, selecting a
quantized file does not automatically change the workflow's precision options.
No weights, model downloads or additional model defaults are bundled.

During agent-assisted installation, the agent must also adapt loader/precision
settings, nodes and injection-map bindings when the selected H3 requires them;
follow [H3 workflow setup](H3_WORKFLOW_SETUP.md). Model dropdowns alone do not
perform that adaptation. The procedure includes activating the private map and
checking the built submission graph, with a real test only after authorization.

Only explicit model changes are submitted by the settings form. Changing the
workflow binding map and saving with untouched model controls uses the new map's
own choices. The UI reloads its selections after saving.

A model change reads the selected workflow/map and derives a private copy under
the app's `config` directory, with an absolute reference to the derived graph.
Only the selected model filename changes. Custom nodes, other node parameters,
reference bindings, injection-map metadata and precision settings remain intact.
The original graph/map are not overwritten, including when they live in the
repository. Keep the original map path if you want to switch back later.

Video/audio VAE loaders are identified through their decoder connections;
diffusion and text-encoder loaders must be unambiguous. A workflow with multiple
ambiguous loaders leaves that control disabled instead of guessing which one to
change. Edit such a workflow directly in ComfyUI. All settings updates require
an idle studio, and changed workflow/settings invalidate earlier production
previews and recovery fingerprints.

Browse buttons choose paths on the machine running Mondo. Folders can be selected
or opened with a double-click; Enter opens the focused entry and Space selects
it. File mode lists matching extensions and enables confirmation only after a
file is selected. Navigation does not upload or execute the selected files.
Filesystem entries remain data, not HTML.

The OAP helper describes the difference between actors and extra references.
Package inspection displays the actual upstream display name, signing public
key, content limits and commercial rider. A valid signature confirms integrity;
it does not establish local trust or imply commercial permission. The raw report
is available beside the summary, and import still requires explicit signer
acknowledgment and upstream verification.

Run the checks with `python -m pytest -q` (four workers), or use
`python -m pytest -q -n 0` for serial execution. The optional test extra installs
both pytest and pytest-xdist. Existing unittest discovery also remains supported.

## Bundled H3 workflows (1.10.5)

Settings has a **Bundled H3 workflow** picker above the workflow path: the
standard 20-step graph, **FastH3 Omni INT8** (8 steps, INT8 ConvRot diffusion
model and text encoder) and **FastH3 Omni BF16** (8 steps, BF16 pair). The FastH3
models come from `FastVideo/FastH3-Omni-Comfy`; their filenames must exist in
ComfyUI's `diffusion_models` and `text_encoders`. Neither has a LoRA option.
Agents choose one with `update_studio_settings({"workflow_preset": "fasth3_int8"})`
(`standard`, `fasth3_int8`, `fasth3_bf16`) while idle; `inspect_studio("settings")`
lists them as `workflow_presets`. A map's `default_steps` sets the sampler steps.
