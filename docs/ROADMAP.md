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

- BONK (actor dancing): let selected actors dance to the song, with movement guided by
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
  implementation has not started.
- Instrument-playing actors: assign each actor an instrument (drums, bass, guitar, piano, keys, vocals) and
  show them playing it. The stem separation already behind the instrument driver could decide, per passage,
  which assigned instruments are audibly playing (a drummer idles through a drum-free break) and tie a
  passage's energy to that actor's stem. Limits to design around: the models give four stems (drums, bass,
  vocals, other) or six with guitar and piano (piano is the least reliable), so "other" lumps keys, strings
  and synths and specific instruments such as violin versus saxophone cannot be told apart automatically;
  the owner would assign the instrument. H3 hears the audio but has no notion of notes, so convincing hand
  and finger sync is unproven and needs a real GPU test. The writer prompt would need an instrument rule
  alongside the sealed-lips and singing rules (wording for the owner to approve), plus the same shot-level
  deterministic check used for lip sync. Builds on the lip-sync singer assignment.
- Instrument reference pictures (owner idea): let each actor's instrument carry a reference picture so the
  guitar, drum kit or keyboard looks the same in every passage, the way actor sheets keep faces consistent.
  The renderers accept up to 9 reference images per passage (30 for Seedance 2.5; local H3 and WaveSpeed
  report 9), and each actor already uses one, so instruments compete for the same slots: a passage with three
  actors and three instruments needs six. The planner and casting code (original engine sources) allocate
  those slots, so a first version would have to either fit pictures inside the existing limit per passage
  (drop the instruments of actors not on screen) or extend slot allocation outside the engine. Needs a
  way to store instrument pictures (an actor-like asset, probably separate from OAP actor packages), the
  prompt tags for them, and a real GPU test that the renderer keeps the instrument consistent.
  Owner direction: load only the reference images each passage needs. That matches how actors already
  work (every passage is its own generation with its own reference list), so the slot budget is per
  passage: the actors on screen plus their instruments, and an instrument is only attached where its
  player is cast and audibly playing.

- Suggest the singer from the voice: estimate whether the vocals stem sounds male or female and
  match it to the cast (the owner would pick a male actor for male vocals). Needs a reliable pitch
  or voice-type estimate and cast metadata, and must stay a suggestion the user can override.

## To investigate

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
