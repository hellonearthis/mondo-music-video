# Product scope

Mondo Music Video is a focused community application, independently developed
and versioned. It is not the complete Mondo studio with hidden controls.

## Included

Music-video generation uses song analysis, visual direction, styles, optional
actor references, prompt writing, rendering, and automatic assembly into a final
video. Laya reviews the writer’s prompts before rendering. Internal assembly is essential; individual clip redo/recast and manual
reassembly controls are outside this edition's scope.

Actors have visual identity records and reference images. OAP is a required part
of the actor workflow: import/export, package verification, identity signing and
applicable actor-boundary checks. There is no mandatory account, reporting,
public actor sharing, or bundled cast. Voice synthesis and audition systems are
outside this edition's scope.

Styles include a general-purpose default. Style harvesting uses
the user's reference images and configured vision service. Credits/idents can
be generated and attached to music videos.

Supported local renderers and API providers use explicitly configured endpoints
and user-supplied models/credentials. Paid generations require a cost preview
and user consent before submission. No automatic provider substitution.

## One operation at a time

Generation, harvesting, idents, and upscale exports share a single-operation
guard. Within one music-video production, a passage that fails the automatic
motion/framing check may be re-rendered once with a new seed, only on free local
renderers; paid renderers are never resubmitted automatically. This is a quality
gate inside the operation, not a manual clip redo control. If busy, the application asks the user to wait; it does not enqueue work.
An optional `vision_quality_check` (off by default) judges sampled single frames
in a batch with a local vision model. It adds model loading/judging time and
mostly reports warnings; repeated unrequested framing devices can use the same
one-retry budget. Pixels remain authoritative for motion. Mondo stops/restarts
only ComfyUI that this production launched, including on the SDK path; an
external ComfyUI service remains operator-owned. Vision startup failure falls
back to pixel checks with a visible warning.
Progress, logs, and cancellation remain available. Cancellation cannot undo a
remote submission or guarantee that a provider will waive its charge.

Completed outputs remain available for playback/download. Optional Topaz export
starts directly from a completed video's controls, preserves the original, and
requires a compatible installed copy. It is unavailable when detection fails.

## Full studio notices

Film, Micro Drama, Hodge TV, Vault, cutting-room tools, and scheduling are not
implemented in this edition. Static teaser tabs may explain full-studio features.
They contain no inactive implementation or private API endpoints.

## Installation goals

One setup engine with shell and PowerShell launchers detects the host and saves
the user's paths/backend choices. API-only setup avoids GPU dependencies and
model downloads. Local setup checks hardware and runtime compatibility.

Optional model downloads use a reviewed source/revision/integrity manifest and
explicit user choice. Existing models can be selected instead. Upstream access
and license requirements apply to each model independently.

Support levels must distinguish installer detection, API-mode verification,
local-renderer verification and optional Topaz verification. A detected OS alone
does not establish support.
