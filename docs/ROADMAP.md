# Development

Mondo Music Video 1.0.0 includes the song-to-video production pipeline, OAP actors,
styles and harvest, credits/idents, local/API generation and agent operation.

Future work can expand the tested hardware/OS matrix, model setup presets and
provider coverage while preserving musical analysis and the one-production flow.
Feature requests should stay within the music-video scope.

## To investigate

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
