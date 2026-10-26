# Agent and MCP setup

The **MCP server** exposes executable tools. The **skill** explains how an agent
should use those tools. They are complementary; an agent can also use the CLI
helper without MCP. Everything calls the same local app, including its
single-operation guard, OAP verification and preview/consent checks.

## Install optional MCP support

From the checked-out project, with its virtual environment already installed:

```sh
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/mondo-music-video serve   # or: bash start.sh --background (stop: bash stop.sh)
```

On Windows use `.venv\Scripts\python.exe` and the corresponding `.exe` launchers.
Keep the app running; the MCP server does not launch renderers or load models.

Configure a stdio server in your agent client, adapting the example to its config
format and replacing the command with your actual absolute executable path:

```json
{
  "mcpServers": {
    "mondo-music-video": {
      "command": "/absolute/path/to/mondo-music-video/.venv/bin/mondo-music-video-mcp",
      "env": {"MMV_URL": "http://127.0.0.1:8091"}
    }
  }
}
```

On native Windows, the command points to
`C:\\your\\project\\.venv\\Scripts\\mondo-music-video-mcp.exe` (JSON requires
escaped backslashes). This is a configuration example, not an automatically
installed connection. No provider keys belong in the MCP client configuration;
configure them through the local app or its own environment.

The server uses the official MCP Python SDK 2.x and stdio transport. Its tools
inspect the studio, upload selected media, preview/start/cancel productions,
read logs, create/delete actors/styles, inspect/import/export OAP, draft/sign/verify
OAP role agreements, download outputs, price (`estimate_upscale`) and start a requested Topaz export
(installed or cloud; cloud needs `max_credits` from the user's approved estimate).
v1.10.22 exposes **56 tools** and advertises the
application version in MCP initialization. It has no shell or private-studio tools.
App calls permit only a localhost URL and bypass proxy environment variables.
The separate API discovery tool makes a bounded GET to a provider's `/models`
endpoint, with HTTPS required remotely and no redirects or generation.

`update_actor(actor_id, description)` changes only a locally created actor's visual description while idle; imported signed OAP actors require a revised package from the signer. The CLI equivalent is `mondo-music-video-agent update-actor ID DESCRIPTION`. Use `inspect_studio(kind="opp-guide")` or `mondo-music-video-agent opp-guide` for the OPP guide. The `auto_collapse_panels` preference is available through `update_studio_settings`, `AgentClient.update_settings`, and `mondo-music-video-agent update-settings '{"auto_collapse_panels":false}'`. It defaults to true. Panel **Done** means required form inputs are present; agents still request a preview quote and explicit start consent.

To check the public OAP actor collection, call `check_oap_collection` (or
`inspect_studio(kind="oap-collection")`; CLI `oap-collection`). This checks only
the published index and marks actors already installed. For a chosen missing
actor, call `stage_oap_collection(actor_id, index_sha256)` (CLI
`oap-collection-stage ID INDEX_SHA256`). Staging downloads and verifies one
signed package without importing it. Review the returned manifest, signer,
license and rider, then use the existing `import_oap` action only after the
operator explicitly accepts that signer. The original four packages are OAP
v0.2; newer collection packages can be v0.3. This flow does not change the
built-in starter roster or overwrite an installed actor.

Worlds: use `preview_production` with `kind: "world_harvest"` (upload images as `reference`, clips as `video`, text as `lore`), review the proposal with `inspect_world_proposal`, and accept it only after the user has seen its changes. See [Worlds](WORLDS.md).

The browser's file drop areas are a selection shortcut. Agents use the existing
`upload_media`/CLI `upload` for songs, references and packages (including OPP props), or the actor
import tools for their image files. A new selection replaces the
files in that control; upload IDs are passed to the same preview, inspection,
import and recovery calls. Package selection never accepts a signer or imports
anything on its own. There is no separate drag action in the agent interfaces.

When a video fails prompt validation before rendering, `inspect_studio` status
reports `can_retry_prompts`. Use `preview_retry_prompts(run_id)` (CLI:
`mondo-music-video-agent preview-retry-prompts RUN_ID`) to get a new quote from
the saved request, then review and explicitly approve a new start. This does
not restart the failed run or automatically spend money.
Opt-in instrument writing may make a narrow guitar-contact correction before
the ordinary validators run; the operation log and private repair receipt show
which shots changed. Wrong-instrument actions still require writer correction.


## Instrument-playing actors

See [instrument performance](INSTRUMENTS.md). `inspect_studio(kind="instruments")` lists each role and its default OPP prop; instrument sheets are props, so import them with the OPP tools below (`import_instrument` was removed). Preview `instrument_mode: "perform"`, `instrument_assignments: {actor_id: "guitar"}` and optional `instrument_references` (true by default). Mode off preserves original prompts/fingerprints. Review passage activity and reference counts before consent. Private provenance never enters the writer job or demo receipts. Guitar/keyboard sheets are bundled; drums/bass sheets and operator render validation are pending.

OPP v0.1 and v0.2 props are a separate, general local library. Upload a user-selected
`.opp` with `upload_media(kind="opp")`, call `inspect_opp(filename)` to review
the manifest and verification report, then call `import_opp(filename,
accept_signer="PUBLIC_KEY_FROM_INSPECT")` for a signed package whose signer the user accepts. For
an unsigned local draft, explicitly pass `allow_unsigned=true` to inspection
and import. `inspect_studio(kind="props")` lists imported props, and
`select_opp_sheet(prop_id, use)` previews the base or interaction sheet chosen
for free-form use text. The CLI exposes `upload opp`, `inspect-opp`,
`import-opp`, `props`, and `select-opp-sheet` equivalents. The current video
request can use an imported prop for an assigned musical role with
`instrument_props: {"guitar": "prop-id"}` and optional
`instrument_prop_uses: {"guitar": "strumming strings"}`. OPP prop IDs and tags
remain free-form; other prop uses are not wired into production yet. Review
the chosen sheet and slot count in the quote, then use the usual start consent.

## Independent dance

Independent dance previews (`dance_mode: "independent"`) also return each dancer's
movement family alongside musical-part cues. Choreography version 3 adds distinct
bounce/step/rotation actions and prompt checks; start a fresh preview to use the
repair. Resuming an existing production preserves its saved choreography. No new
MCP tool or paid consent exception is introduced; rendered distinctness still
needs operator verification.

## Strict dance and instrument checks

`strict_prompt_checks: true` in a video preview request restores the earlier behaviour in
which every dance or instrument wording finding sends the passage back to the local writer
(up to four attempts). Default `false`: only integrity problems (shot count, missing player,
uncited instrument reference) force a rewrite and wording findings are saved as
`segNNN.advice.json` for Laya's review. Enable it only when the user asks.

## Compact prompts

`compact_prompts: true` in a video or ident preview request switches to shorter
writer instructions, smaller job messages and 512 px vision-check frames for low
VRAM/RAM or small context windows. Default `false` keeps the full prompts and
full-size frames. Do not enable it unless the user asks or memory is the problem.

## Visual vocabulary presets

`inspect_studio` kinds `vocabularies` and `vocabulary` list saved presets and the
built-in pools. `save_vocabulary_preset` stores a reusable preset (per category
`mode` of `append` or `replace`, `add`, `exclude`; base profile `full` or
`reduced_flashing`) and `delete_vocabulary_preset` needs `confirm=true` after user
authorization. A production selects one with `vocabulary_profile` or supplies
one-off `custom_vocabulary` overrides in the preview request. Neither spends money;
saving is refused while an operation is running.

## Optional batched vision quality check

`export_production_package` copies a finished production (video, raw clips, song, prompts, receipts, README) into an
editing folder under the app's data folder; it publishes nothing and never copies keys. If the run used actors outside
the four public starters, ask the user before passing `allow_private_actors`, and tell them not to publish that package.

For a hands-off start, read `inspect_studio` kind `quick-start` (CLI `quick-start`): a random plan (`actors`, `dance_mode`, `dancers`, `direction`, `style_id`; it can choose no cast) to merge into `preview_production`. It never enables instruments, subliminal flashes or captions, and consent is still required.

For dancing, pass `dance_mode: "group"` (optionally `dancers`, `dance_direction`, `dance_lead`) in `preview_production`; the preview returns
the plan. Mouth rules are unchanged by dancing.

For the optional subliminal flash, pass `subliminal` in `preview_production` (see the tool description): a picture or a few words
for 1 to 12 frames at chosen times or on bar starts. The preview resolves the times; flashes are kept a second apart; the finished
video keeps its exact length and audio and the untouched copy is `music-video-clean.mp4`. Tell the user flashing can affect people who
are sensitive to it.

For lip-sync mode, set `mouth_mode: "lip_sync"` and give `lyric_lines` ([{start, end, text}] in seconds on
the song clock) and optionally `singers` (actor ids; the first is the main singer, empty means a seeded
pick) in `preview_production`; the preview's `lipsync` shows which passages sing and who sings, and its advisory `voice` (present only with a cached vocals stem) flags a clear voice/singer gender mismatch with a suggested actor; it never blocks. Pasted lyrics may use Suno section markers such as `[Verse 1]` and `[Chorus]` and
`(backing vocals)`; markers become section labels, not lines. Get lines
with `detect_lyrics` (free, local, needs the optional Whisper add-on and a speech model already on disk;
poll `inspect_studio` status for the result) or `align_lyrics` for pasted lyrics. `inspect_studio` kind
`lyrics` reports availability, hardware and a recommendation: tell the user the option exists, ask whether
they want automatic detection, and never install the add-on or start a model download for them. The
singing wording is owner-approved; do not claim verified lip-sync output before an
operator GPU test.

For music videos, `inspect_studio` kind `stems` reports whether the optional Demucs
add-on and each stem model are ready, the machine's GPU/VRAM/RAM, and a
`recommendation` (device and notes). Explain the options to the user and recommend
one for their hardware: standard quality (81 MB) for everyone; high quality (324 MB,
2 to 3 times slower, cleaner on some songs) when a GPU with about 3 GB free exists;
the 6-stem model (53 MB) only for guitar or piano. Pass `analysis_driver` (`mix`, `drums`, `bass`,
`vocals`, `other`, `guitar`, `piano`) and `stem_quality` (`standard` or `high`) in
`preview_production`. Never install Demucs or start a model download without the user's
approval; the user approves downloads in the app's score editor.

For music videos, pass `vision_quality_check: true` in the `preview_production`
request (CLI: the same field in the preview JSON). It defaults to `false` and
adds model loading and single-frame judging time after all clips render. It
uses the local `writer_launch` model plus its mmproj, not the API profile used
for style harvesting. Configure a compatible local vision launch first. Mondo
starts that model itself on port 8083 and does not need the style-harvest
`vision_url` running; a matching `mmv-vision` server already on 8083 is reused and
never stopped. `offline_engines` in the preview lists only roles Mondo can neither
find running nor launch, each naming the setting to fix.

Status coverage: `inspect_studio` kind `status` (CLI `inspect status`) returns
`services` from `/api/status`, including `vision_quality`. `available` says the
role is running now; `has_launch` says Mondo can start it. An offline role with
`has_launch: true` is fine, because configured engines start automatically when a
production needs them. Report a role only when it is neither running nor launchable.

GPU hand-offs. Mondo sequences the heavy models it launches: it
releases ComfyUI's cached models (or stops a ComfyUI it launched) before the
writer and Laya load, stops its own writer and confirms the process exited and the
GPU memory came back before rendering, and does the same around the vision model.
Laya follows its `laya_device` setting, but falls back to the CPU for
that production when the measured free GPU memory is below Laya's staged-weights
estimate plus an activation reserve, or cannot be measured, including Apple unified memory. A CPU setting stays CPU
and the saved setting is never rewritten. The chosen device is shown in
the progress log. A busy ComfyUI queue, a process that will not exit or memory that is
not released stops the production with a message naming the problem. A vision model
that Mondo did not start stays running; passages it flags are then not re-rendered
(a warning says so) because the renderer would share the GPU with it. Processes
Mondo did not start are never stopped. A known external GPU writer or vision server
blocks local renderer startup until that service releases the GPU; CPU-only writers
can remain online. New local writers are also checked against measured headroom
before launch, using staged model sizes plus a reserve.

For `local_h3` and `comfy_sdk_h3`, an already-running ComfyUI can stay open.
After rendering, Mondo checks that its running/pending queues are empty, requests
model/cache release through `/free`, and waits for reported GPU memory/headroom
before loading vision. It never stops an externally owned process or
interrupts another job. Retry rendering reloads models in the same service.
If ComfyUI is offline, configure `comfy_launch`; a process Mondo launches itself
continues using the existing stop/restart handoff. The SDK proxy stays running.
A busy queue, unsupported memory reporting or failed release records a vision-check
failure while preserving pixel checks and the rendered video.

Read `quality_warnings` on completion, including skipped/failed vision checks.
Vision judgments are mostly warnings; a framing device detected in at least two
sampled frames may trigger a retry unless the director requested that framing.
Pixels determine motion failures. A passage has one retry budget shared by
pixel and vision checks, only on free local renderers. Never start paid
re-renders or another paid production without consent. If the vision server
cannot start, pixel checks still run and the output carries a warning; this is
not proof that vision passed. Run-local `vision.json` records the request and
service note; `quality.json` holds per-attempt judgments.

## v1.4.0 musical score tool

| Tool | Purpose and boundary |
| --- | --- |
| `read_music_score` | Read-only. For a finished music video (`output_file` from `inspect_studio(kind="outputs")`), return tempo, beats, downbeats, per-beat energy, sections and passages with their montage grammar and planned cuts, in seconds on the video's clock. Use it to explain the pacing. Internal cuts are planned; generated clips may not follow every one. |

## v1.3.0 OAP 0.3 tools

| Tool | Purpose and boundary |
| --- | --- |
| `export_oap` | `tier="audition"` writes a signed audition package that lists cast-only assets by hash without including them. Set `reference_clearance="audition"` only when the user confirms the reference is a cleaned or watermarked take. Imported actors export only their original package. |
| `create_role_agreement` | Draft an unsigned agreement casting an actor; this studio is the Director. It binds the actor's exact signed manifest and a generated casting call. Rider conflicts are refused, never approved. Terms cannot change after drafting. |
| `sign_role_agreement` | Sign as `director`, or as `agent` only for actors this studio exported. Requires the user's explicit authorization for that agreement and role, then `confirm=true`. |
| `verify_role_agreement` | Read-only check of both signatures and source bindings. Valid signatures do not prove who holds the keys. |
| `export_role_agreement`, `import_role_agreement` | Save a zip (agreement, manifest, casting call) for the Agent to countersign, then import their returned `agreement.json` after `upload_media(kind="agreement")`. Only valid signatures on unchanged terms are merged. |

Finished outputs may carry `quality_warnings` from the automatic motion and
framing check. Report them to the user; do not start a new paid production to
fix them without authorization.

`inspect_studio(kind="agreements")` lists agreements and their signature status.
Agreements do not move money, approve rider exceptions or establish signer trust.

## v1.2.1 setup and library tools

| Tool | Purpose and boundary |
| --- | --- |
| `inspect_studio` | Read version, status, catalog, actors, styles, outputs, settings/profile metadata, the OPP guide (`kind="opp-guide"`) or update notice (`kind="update"`). No secret values. |
| `inspect_api_models` | Inspect an explicitly selected provider's advertised model IDs. A successful listing does not prove chat/video compatibility. |
| `add_api_profile` | Save a new writer/vision/supported-video profile with role-specific `settings`. Names cannot overwrite another account. Optional `key_env` names an existing variable in the MCP server process; never pass a literal key. Without it, a new configuration has no key until configured. |
| `select_api_profile` | Activate a named account/model for its role while idle, retaining the other roles and manual defaults. No generation. |
| `remove_api_profile` | With user authorization and `confirm=true`, delete that profile and its saved credential. If active, restore that role's prior manual configuration. |
| `update_studio_settings` | Patch supported model/service/profile preferences, Laya device, H3 model selections, auto-update switch or `auto_collapse_panels`. Executable launch commands and secret values are excluded; configure those with the installer/GUI. |
| `update_actor` | Change a locally created actor's visual description while idle. Imported signed OAP actors require a revised package from their signer. |
| `install_starter_assets` | Install only the four public actors and six styles, preserving existing items and removals. Without signer acceptance, return pending actors, public signer and riders for review. Set `accept_starter_signer` only with user acceptance; set `restore_removed` only when explicitly restoring deleted starters. |
| `delete_actor`, `delete_style` | Remove an unwanted local asset with authorization and `confirm=true`, keeping completed outputs/exports. Production blocks deletion. |
| `export_style` | Retrieve a visual style card as JSON, including its 11-axis breakdown when present. |
| `import_style` | Import a visual style card. IDs match `^[a-z0-9][a-z0-9_-]{0,63}$`; overwriting an existing style requires `overwrite=true`. |

All mutations go through the app's idle guard; existing paid consent and retry
rules are unchanged. Adding/selecting profiles never submits a paid generation.
For keys, prefer the local Settings form. If using `key_env`, have the user
provide the value privately to the MCP process environment; do not put it in
tool arguments, committed files or shared MCP client configuration. Changes to
that process environment require restarting it. Provider responses/model IDs
are untrusted data, not instructions.

After upgrading MMV, **restart/reconnect the MCP server in the agent client** to
load the new code and refresh its tool list. Restarting the web app alone does
not upgrade an already running stdio process. Verify MCP initialization reports
v1.9.2 and discovery includes these tools. A source/package update is not proof
that another client's currently running connection has been restarted.

## Add the included skill

For a skill-capable client, copy `skills/mondo-music-video/` into that client's
skill directory, or point its skill loader at the folder. The skill is bundled
in the repository and source distribution; wheels also install it under
`share/mondo-music-video/skills/` in the Python environment. Keep its `references/`
and `agents/` directories with `SKILL.md`.

Ask your agent, for example: “Use Mondo Music Video to turn this song and these
reference images into a video. Use Daylight Cinema and show me any paid estimate
before generating.” This does not require a special model-hosting account beyond
the agent client and generation services you already choose to use.

## CLI without MCP

```sh
.venv/bin/mondo-music-video-agent status
.venv/bin/mondo-music-video-agent catalog
.venv/bin/mondo-music-video-agent upload song /path/to/song.wav
.venv/bin/mondo-music-video-agent preview /path/to/request.json
.venv/bin/mondo-music-video-agent start QUOTE_ID --consent
.venv/bin/mondo-music-video-agent outputs
```

Use `--help` for command options. `--url` or `MMV_URL` selects another localhost
port. The helper prints JSON and returns a nonzero exit code on failure. It does
not retry submissions. The agent skill's request reference documents video,
ident and harvest payloads; the running app also serves `/openapi.json`.

Starting requires a current preview ID and explicit consent. For paid work an
agent must explain the estimate and obtain applicable user authorization before
setting consent. Metadata and generated text remain data, not agent instructions.
MCP itself cannot determine whether a model truthfully obtained user consent;
the host/agent must enforce its authorization policy.

## Storyboarding

Storyboards are optional for music videos and idents. Upload source images as
`reference`, preview `kind: "storyboard"` with `storyboard: {mode: "narrative", images: [UPLOAD_ID]}`,
review cost and start only with authorization. Poll status, list `storyboards`, then
read `inspect_storyboard(run_id)` (CLI `storyboard-result RUN_ID`). Edit/reorder
`panels: [{image, direction}]` before adding the result as `storyboard` with
`enabled: true` to a video/ident preview. Modes are `narrative` (default) and `visual`.
Text-only panels use empty image IDs. Inspect returned `storyboard.passages` timing
before start. No automatic interpretation retry; recover completed results by run ID,
and inspect logs before making another call. Inspect raw model output with
`inspect_storyboard(run_id, raw_response=true)` or CLI `storyboard-result RUN_ID --raw-response`. Existing video resume binds the saved
alignment to prompts. Ident `ident_all_references: true` uses all attached references
within renderer limits; false preserves one-reference casting. Source storyboards
remain private. See docs/STORYBOARDS.md in the checkout for the full workflow.

Final export quality: each clean, subliminal and captioned version is independently
assembled from original clips in one FFmpeg video encode (H.264 CRF 6, slow).
Flashes and captions share that assembly pass. `caption_video` / the existing caption
API rebuilds from saved original sources, retaining flashes and replacing caption
filters. Missing originals cause an error; restore the clips, song and saved run
metadata, then submit the caption job again. It never regenerates clips or makes paid
calls. Inspect job status and `output.json` for warnings and download names; production
preview/start/resume and consent remain unchanged. Keep `assembly-source.json`,
`assembly-assets/`, original clips and the song for later reconstruction. Topaz
upscaling is the explicit user-requested exception and still uses the selected final.
