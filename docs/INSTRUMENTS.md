# Instrument-playing actors and OPP props

Choose **Instrument performance → Actors play assigned instruments** in the video
form and assign drums, bass, guitar or keyboards to selected actors. The mode is
off by default. **Consistent instrument references** is checked by default within
this opt-in mode. Open **Cast & OAP → Instrument reference library** to inspect
the sheets or import a local one with its license and provenance. Imports do not
overwrite existing local sheets; they override the bundled design on that machine.

The owner approved this extension using the BONK pattern: additional rules are
inserted outside the original engine, before the existing quality rules. The
original writer, singing, sealed-mouth, ident, planner and validator sources and
their protection pins are unchanged. Validation status is tracked in developer
documentation. The original integrity banner remains unchanged.

Each passage keeps its original actor cast and picture tags. Instrument sheets
are appended in first-player order, sharing one slot when two players use the
same design. Only instruments with players cast in that passage and at least one
playing/unknown-activity shot receive references. Fully paused players receive
rest cues and no instrument sheet for that passage. Actor and instrument slots
are counted together against the selected renderer's declared maximum; overflow
stops preview with advice to reduce the cast or disable instrument references.
The quote includes the renderer's reference-image cost. Backend tag computation
supplies picture/audio labels; H3 numbers audio separately from pictures.

Activity follows existing stem analyses or CPU analysis of already-cached stem
audio. This option never starts separation, downloads models, or switches a
provider. Drums/bass use the chosen standard/high cache; guitar and piano use the
six-stem cache. Keyboards follow piano as a proxy, which does not detect all synth
parts. A missing part explicitly falls back to mix rhythm. Quiet mix energy and
shots without stem beat samples have **unknown** activity; they never establish
an instrument pause. Measured low stem energy supplies a rest cue. These energy
cues do not identify notes, fingering or exact audible silence.

Players are excluded from dance choreography; other selected actors can still
dance. A player cannot be an explicit dance lead. Approved singers can sing while
playing, under the existing singing rules. Other mouths keep their existing mode.
A player does not have to play in every shot: they may stand, move or react. When a
player is shown playing, the prompt should give concrete action/contact ("strikes the
guitar" alone is weak), avoid another instrument's gesture, and rest in a paused shot;
these are advice to Laya's review, not rewrite triggers. Each player appears in at least one shot per cast passage;
object-only shots are allowed. Only integrity problems (every shot described, the
player present, the instrument reference cited) force a rewrite; wording findings
are saved as advice in `segNNN.advice.json` and the prompt goes to Laya. The same
integrity checks run on cached prompts. This is
a prompt guard, not a measurement of rendered hands, object identity or timing.

Instrument plans, references and cues are bound to saved prompts for resume.
Asset bytes participate in consent fingerprints, and changed sheets stop replay
and rendering. Old runs without instruments preserve their original fingerprints
and prompt/cache behavior. Start a new production to add instruments to an old run.

## Assets and OAP

Props use a small `mmv.instrument` version 1 record, separate from the Open Actor
Protocol. They do not become actors, consume actor cast positions or bypass OAP
rider/signature verification. Metadata contains instrument ID, design description,
PNG dimensions, SHA-256, original-image SHA-256, license and provenance. A future
OAP prop extension can adapt this format without relabeling props as people now.

Bundled public assets live under `mmv/assets/instruments/`. Local imports live
under the application's private `instruments/` folder. Original local import bytes
are preserved as `original.image`; the reference PNG is cleaned of embedded
metadata. The sheet's created resolution is preserved up to the existing 4096 px
reference-image limit. No upscaling is performed.

Initial public sheets supplied by the owner: guitar (1360×2048) and keyboards
(1664×2496), accepted at their created resolution, distributed under the project's
Apache-2.0 license. The generation model is not independently verified. Drums and
bass sheets are pending; their text-only assignments work with
`instrument_references: false`. With references enabled, a missing required sheet
stops preview rather than silently promising consistency.

Panel review found some hardware-count differences within the supplied sheets.
The references are usable initial assets; neither precise cross-panel construction
nor rendered consistency is claimed verified. Same-song, same-seed before/after
operator renders remain required before the prompting feature's visual quality is
considered validated. Automated tests use synthetic media and mock services only.

The writer receives reference hashes and the generic design description, never
private import paths or provenance. Demo-package receipts omit instrument paths, provenance
and original-source hashes; instrument sheet/original files are not copied into those packages.
Public source/wheel packages include only the explicitly bundled public sheets.

## Open Prop Protocol packages (1.9.7)

MMV accepts Open Prop Protocol v0.1 `.opp` bundles. Open **Cast & OAP → Open
Prop Protocol library**, inspect a package, review its owner, sheets, clearance,
hash and signature report, then import it. Signed packages require an explicit
signer acceptance using the inspected public key; unsigned local drafts require the separate unsigned choice.
The original package and cleaned visual sheets stay in the private application
`props/` folder. Existing IDs are never overwritten. OPP imports do not become
actors or change OAP rider checks. The protocol itself has no fixed prop or
action vocabulary; MMV stores any prop, while this first production workflow
uses imported props as optional references for the four musical roles.

In **Instrument performance**, choose an imported prop under the corresponding
instrument role. The optional free-form **use** text selects a matching OPP
interaction sheet by the protocol's tag/label matcher, with a base-sheet
fallback. Preview names the chosen sheet, counts it in the same reference slot
budget as existing instrument sheets, and binds its cleaned bytes and original
package hash into the quote and saved replay plan. The selected role remains
drums, bass, guitar or keyboards for stem activity and physical-action checks;
the OPP prop ID and interaction tags are never restricted to those four names.
Leaving the selector blank keeps the existing bundled/local instrument sheet.
Only one sheet per musical role is selected for a production. The source
`prompt_modifier` stays in the preserved OPP bundle and is not sent to the
writer; package-authored text does not override Mondo's instrument directions.
Per-shot switching and use of OPP props outside instrument performance are
future host workflows.

The importer caps a bundle at 128 MB, expanded members at 256 MB, and each
included image sheet at 25 MB before protocol verification. It rejects unsafe
ZIP paths and symlinks, verifies all listed hashes and any signature using the
pinned OPP verifier, and cleans renderable images without changing the preserved
source bundle. A verified signature proves key control, not a license grant;
review the package's license and clearance before using it.

## API and agent use

`GET /api/instruments` lists all four designs and availability;
`GET /api/instruments/{id}/reference` serves the selected sheet.
`POST /api/instruments/{id}` accepts multipart `reference`, `license`, `provenance`
while the app is idle. This imports locally and never publishes anything.

Use `AgentClient.import_instrument(id, path, license, provenance)` or the MCP
`import_instrument` tool, and `inspect_studio(kind="instruments")` for discovery.
MCP exposes 42 tools. The shell supports `mondo-music-video-agent instruments`
and `props`, plus `upload opp`, `inspect-opp`, `import-opp`, and
`select-opp-sheet`. `inspect_studio(kind="props")`, `inspect_opp`, `import_opp`,
and `select_opp_sheet` cover the same workflow over MCP. API equivalents are
`GET /api/props`, `POST /api/upload/opp`, `GET /api/opp/inspect/{upload}`,
`POST /api/opp/import`, and `GET /api/props/{id}/selection?use=...`.
For a failed prompt-only production, status offers `can_retry_prompts`; the GUI
and agents can request a fresh preview from that run, then approve a new start.
During writing, a narrowly identified vague guitar action may be corrected to
string and fret contact before the normal prompt and Laya checks. The writer's
original JSON and a per-shot repair receipt stay in the private run directory;
the operation log names corrected shots. Keyboard gestures attributed to the
guitarist, ambiguous actors, pauses and quoted lyrics are left for writer
correction. This does not add paid writer calls or change passage planning.

Example `preview_production` request (use your existing actor and uploaded song IDs):

```json
{
  "song": "uploaded-song.wav",
  "actors": ["actor_one", "actor_two"],
  "instrument_mode": "perform",
  "instrument_assignments": {"actor_one": "guitar", "actor_two": "keyboards"},
  "instrument_references": true,
  "on_screen": 2,
  "ensemble_mode": "always"
}
```

Preview returns `instruments` with assignments, per-passage performers, reference
IDs, per-shot activity and source/fallback notes. Review the
quote before starting once with existing consent. No paid retry or extra active
operation is authorized by instrument selection.

Existing `mmv.instrument` v1 sheets remain an independent local format. They
are not silently relabeled or exported as OPP packages.
