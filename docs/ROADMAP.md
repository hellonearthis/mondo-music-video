# Development

Mondo Music Video 1.0.0 includes the song-to-video production pipeline, OAP actors,
styles and harvest, credits/idents, local/API generation and agent operation.

Future work can expand the tested hardware/OS matrix, model setup presets and
provider coverage while preserving musical analysis and the one-production flow.
Feature requests should stay within the music-video scope.

## Pinned (lower priority)

- Backup and chorus singers for the planned lip-sync mode: let a passage give
  additional actors a sing-along role next to the main singer. The Demucs models
  in use return one combined vocals stem, so lead and backing voices cannot be
  told apart automatically; a first version would be a manual choice per passage.
  Automatic detection would need a lead/backing separation model, which has not
  been evaluated.

## Built, awaiting verification

- Lip-sync mode (release 1.7.0; wording approved by the owner; operator GPU test pending): a third Facial movement mode where
  passages with singing drop the sealed-lips suppression and use a separate singing
  rule (wording to be approved by the owner), while other passages stay sealed. A
  lyrics box that does more than flavor (lines tied to passages by word timing), with
  optional detection by transcribing the vocals stem (an existing Whisper large-v3 did
  this well on stems in a trial), paste and edit supported; a selectable main singer,
  otherwise a seeded random pick.

## Ideas (not started)

- Fix consecutive repeated camera moves in the shot planner. The independent-dance
  operator test showed two adjacent identical pull-out shots near the end; the
  owner also observed a longer-looking sequence of zoom repetition. The current
  camera sampler does not track its previous choice. Review repetition across
  shot and passage boundaries, preserve deterministic seeds and handle restricted
  camera pools. Owner requested a proper future fix, not an opt-in workaround in
  the dance repair. Follow the protected-scheme review/approval procedure and
  compare real same-song/same-seed renders before delivery. No camera change made.
- Subliminal message mode (built, release 1.7.2, owner-requested): flash a chosen picture or a few words for a handful of frames in the
  finished video, at times the user picks or on bar starts. FFmpeg overlay by frame number after assembly; length, frame count and audio are
  unchanged and the untouched video is kept. Open: a way to preview the flash before rendering, a library of flash pictures, and
  per-flash pictures.
- BONK (built, release 1.8.0; design in `docs/BONK_DESIGN.md`, reviewed by Codex; group and independent per-part dancing implemented in 1.8.3): let selected actors dance to the song, with movement guided by
  its beat and passage energy. Let users choose who dances and optionally enter
  free-text "Dance direction"; default to simply "Dancing" without requiring
  knowledge of dance styles. Example directions: gentle swaying, energetic
  jumping, goofy dancing, or everyone moving together.
  When singing and dancing are both enabled, default the selected singer to
  dance lead, with an override for another actor or no lead.
  Offer group choreography (lead in front, supporting dancers behind or beside
  them attempting the same moves in time) and independent dancing (each actor
  moves individually). For independent dancing, let actors follow different
  musical parts: overall beat, drums, bass or vocals. Assign parts automatically
  with user overrides; use available stem rhythm, accents, pauses and passage
  energy so actors share the song's tempo but emphasize different events.
  Stem analysis can guide per-actor passage instructions; precise beat following
  and matching choreography between actors remain unverified and need operator
  video tests before being promised. Feature requested by the owner;
  independent implementation is available; real visual timing validation remains pending.
- Instrument-playing actors: opt-in implementation in 1.9.0 assigns drums, bass, guitar or keyboards to selected actors, with concrete playing/rest instructions and shot checks. Existing stem energy guides passage cues; missing stems and gaps are explicitly unknown, with overall rhythm fallback. Keyboards follow the six-stem piano part only as a proxy, not automatic identification of all synths. Players can sing under the approved singing rules; other actors may dance. Original prompts/planner/pins stay intact. Real same-song/seed contact, note/finger timing and musical performance validation remain pending; see [instrument design and limits](INSTRUMENTS.md).
- Instrument references: implemented per-passage allocation outside the protected engine. Append only sheets for cast players with playing/unknown activity, deduplicate shared instrument designs, and reject overflow of the selected renderer's reference budget. Props are separate from OAP actors and do not alter actor cast positions or OAP verification. The owner-supplied guitar/keyboard sheets are bundled at their created resolutions; drums/bass public sheets are still pending. Real-render visual identity validation remains pending.

- Suggest the singer from the voice: estimate whether the vocals stem sounds male or female and
  match it to the cast (the owner would pick a male actor for male vocals). Needs a reliable pitch
  or voice-type estimate and cast metadata, and must stay a suggestion the user can override.

- Actors from the oap-actors repository (owner decision, to ship with the voice/gender check): the starter cast stays pinned in
  `examples/starter-cast/manifest.json` (actor IDs, package SHA-256, signer key), but the packages are fetched from
  https://github.com/hodgemann/oap-actors instead of being bundled; fetched files must match the pinned hash, pass the OAP signature
  check and the install guide's signer acceptance. A local clone can stand in when offline (rented GPU hosts). Mondo can also import
  *other* actors from that repository on the user's request: the app lists the catalog (`index.json`) with each rider shown, rider
  restrictions are enforced against the production's content settings (an actor whose rider allows nudity is browsable but not importable
  by default), and each import verifies the hash, the signature and the signer before anything is added. New repository actors are never
  imported automatically and the four-actor public roster rule in AGENTS.md changes only with the owner's explicit say-so.
- Voice/gender check (owner decision, same release): warn in the preview when the vocal sounds clearly male or female and the chosen singer
  is the other, offer the best match in one click, never block a deliberate mismatch, do nothing when unsure (see "Suggest the singer from
  the voice" above).

## To investigate

- A tested install on a second rented-GPU host. `docs/GPU_CLOUD.md` documents Vast.ai, Lambda, TensorDock, Paperspace and the big
  clouds from the RunPod guide but nothing has been run on them. A single Dockerfile (or image recipe) could replace several
  per-host procedures; it is not written. Whether Comfy's hosted platform should be offered as a renderer for people with no GPU is
  a separate provider question, untested.

- Topaz online upscaling through its API (today upscaling uses the user's local Topaz
  Video AI). The owner has a Topaz account, so a real test is possible. Open questions,
  not yet verified: whether Topaz offers a suitable video API and on what terms and
  pricing, how requests are authenticated, and how uploads, results and cancellation
  work. Constraints to keep: explicit paid consent before any submission, no automatic
  paid retries, keys stored privately like the other provider keys, and no media sent
  without the user's approval.

- [wavesurfer.js](https://github.com/katspaugh/wavesurfer.js) for song waveform,
  regions and timeline display beside the audio preview and musical score view.
  Needs a licence check and a local-first (vendored, no CDN) assessment before any
  adoption; not yet evaluated.
- Music-creation pipeline hook: let a DAW or music generator hand a finished song
  (plus optional tempo, bar and section markers, or stems) to the app, and receive
  the finished video path back. The local API, agent client and MCP already accept
  uploaded songs, so the open questions are the contract and the trigger: a watched
  drop folder, a documented webhook/CLI call, or a plugin on the music side.
  Constraints to keep: one active operation, explicit paid consent (an automated
  upstream must never authorise paid renders), loopback-only by default, and no
  new network exposure without a deliberate setting.
- Compare compact and full writer/ident prompts on real output (same song and seed)
  before recommending the compact option to anyone.
