# Local writer tuning and device choices

The Settings panel's **Local writer setup guide** shows the configured launch
command and lets you preview alternate tuning. Opening the guide or selecting a
preset does not save settings or launch anything.

## Preserve the model, choose tuning

- **Keep current configuration** leaves the command as configured.
- **16k context / vision batches** adjusts the existing command to
  `-c 16384 -b 2048 -ub 1024`. It adds `--image-min-tokens 1024` only when the
  command already contains a `--mmproj` projector argument. The executable,
  model, alias and projector paths are preserved. The preset replaces the
  corresponding long-form flags too, so duplicate context/batch settings do
  not accumulate.

Inspect the preview, choose **Apply tuning to launch field**; Settings
save automatically, so it is persisted at once. Your installed model and llama.cpp version must
support the selected options. Larger contexts and batches use more memory;
this preset is an option, not a claim that it suits every model or machine.
A local writer must expose OpenAI-compatible `/models` and `/chat/completions`
endpoints under its configured base URL, commonly `http://127.0.0.1:8080/v1`.

The guide does not replace model filenames with those from a different user's
machine. H3 model choices continue to come from the configured workflow and
installed models in Settings.

## Windows launcher

Existing defaults remain an 8,192-token context with server-default batch and
image-token settings. Select the alternate tuning in Settings, use `-TuningPreset context_16k`, or supply individual values:

```powershell
.\start.ps1 -ContextSize 16384 -BatchSize 2048 -MicroBatchSize 1024 -ImageMinTokens 1024
```

Explicit individual arguments take precedence over preset values. Zero for a
batch/image-token parameter omits that flag. Image-token tuning is used only
for a model with a detected vision projector. Settings are transferred to the
Python helper as UTF-8 JSON, so paths and model aliases are data rather than
interpolated Python code. Native Windows/PowerShell execution remains an
operator verification step; Linux tests do not establish Windows support.

## Laya device selection

The default remains **CUDA**. Explicit **CPU**, **CUDA** and **MPS** retain their
selected device; they do not silently switch when unavailable.

Optional choices preserve the fork's fallback behavior:

- **CUDA with CPU fallback:** CUDA when available, otherwise CPU.
- **MPS with CPU fallback:** MPS when available, otherwise CPU.
- **Auto:** prefer CUDA, then MPS, then CPU.

The production status records the device Laya actually loads. Fallback does not
bypass Laya or substitute a heuristic reviewer. Missing models and failed loads
still stop production before rendering.

## Visual vocabulary profiles

Under the music-video form's **Timing, credits & content**, choose:

- **Full vocabulary:** current default, with the original expanded pool intact.
- **Reduced flash/strobe cues:** excludes seven selected lighting
  cues and two practical-effect cues, matching the reviewed fork's reduced pool.

The optional profile changes only those vocabulary pools. It does not change
musical timing, planner logic, model selections or workflows. Removing cues
is not a guarantee that a generated video contains no flashing; review actual
output. Profile choice is part of the production request and consent fingerprint.
