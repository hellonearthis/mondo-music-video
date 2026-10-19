# Lip-sync mode (design)

Status: implemented in release 1.7.0 (not yet verified on real H3 output); owner approved the direction (2026-10-19). Wording of the singing rule
was approved by the owner on 2026-10-19. The sealed-lips scheme (rule text, rigging tail,
validators) is never altered.

## What already exists (read from the code)

- Every H3 passage is sent its own slice of the song as an audio reference (`slice_audio`,
  `LoadAudio`, `ref_audios` in the injection map). H3 therefore lip-syncs by itself when a slice
  contains singing; the sealed-lips scheme exists to stop that on passages without singing.
- `worker.run` builds the writer system prompt and cast block **once** from one flag
  (`effective_silent_mouths`). Inside the per-passage loop the same flag feeds
  `build_writer_request`, the rigging-tail injection, `validate_prompt`, and the Laya
  `run_clipboard` call, so the machinery already supports `silent_mouths=False` per call.
- `style.compose_writer_prompt(silent_mouths=False)` swaps in `NATURAL_MOUTHS_RULE` and
  `actor.cast_writer_block(..., silent_mouths=False)` drops the sealed-lips cast rules.
- Engine sources stay byte-identical; additions live outside `mmv/engine/`.

## Design

**Mode.** `mouth_mode` request field: `sealed` (default, today's behaviour), `natural`, or
`lip_sync`. The existing `silent_mouths` bool still works for agents (true -> sealed,
false -> natural) when `mouth_mode` is absent. The UI's Facial movement select gains a third
option, "Lip sync to vocals".

**Per passage.** A passage *sings* when lyric lines overlap it by at least ~0.75 s. Singing
passages use a second prompt set: the writer system text composed with `silent_mouths=False`
plus a new `SINGING_RULES` block (owner-approved wording), their cast block without sealed-lips
rules, a job `singing` object (singer, picture tag, lines with passage-relative times), no
rigging tail, `validate_prompt(silent_mouths=False)`, and a deterministic `lipsync_problems`
check (singer's picture tag present, at least one sung line quoted). Every other passage runs
the existing sealed path unchanged. Non-singing cast members in a singing passage keep calm closed
mouths by instruction in `SINGING_RULES`.

**Singers.** `singers`: actor ids; the first is the main singer. If empty, one singer is picked
from the roster with the production seed (deterministic, recorded). In a passage where the singer
is not on screen, the passage stays sealed: only the main singer sings (changed on 2026-10-19 from "the first cast actor sings", which made a woman lip-sync a male vocal); this is recorded in the
preview. Backup singers: pinned, manual later.

**Lyrics.** The existing lyrics box stays (flavor text). New `lyric_lines`
(`[{start, end, text}]`, bounded count/length, seconds on the song clock) is what drives singing
passages. Sources: typed or pasted lines with times set by dragging regions in the score editor
(wavesurfer Regions, already vendored); or **optional detection**: transcribe the vocals stem to
words with timestamps, then group into lines. Pasted lyrics without times are aligned by matching
them to the recognised words (sequence alignment); no extra aligner is required. The user can
edit everything before generating.

**Detection engine (optional add-on).** `mmv/lyrics.py`: a subprocess worker like analysis and
stems; the speech model is an add-on installed only with approval (install tiers apply). Candidate:
openai-whisper (MIT); the owner's machine already holds large-v3 (3.1 GB) and trial results on the
owner's vocal clips were correct on stems and wrong on one full mix, so detection runs on the vocals
stem when the stems add-on exists and warns when it must use the mix. Model sizes versus accuracy on
singing are untested and must be measured before recommending a size by hardware.

**State and safety.** New fields enter the request, quote fingerprint, `request.json` and
`prepared.json` (the approved snapshot resume replays; resume never re-detects). The prompt cache key
already includes the system text and job JSON, so singing and sealed passages never share cache
entries. Detection and singer choice are free; nothing here changes paid consent or retries.

## Order of work

1. `mmv/lyrics.py` + request fields + preview (`singing` flag per passage in the quote).
2. Worker: per-passage prompt sets, `SINGING_RULES`, `lipsync_problems`.
3. Editor: lyric lines, singer select, detect button, per-passage singing flags.
4. Agent/MCP/skill/install-guide coverage; tests with mocks.
5. Operator GPU A/B (sealed vs lip-sync on a vocal clip, 0.3 MP) only with the owner's go-ahead.

## Review findings adopted (Codex, read-only, 2026-10-19)

1. **Selection** uses the *audible slice* (`audio_slice_start_s`/`audio_slice_end_s`, which includes
   generation padding) and the union of lyric-line intervals, with the threshold a named constant
   (0.75 s) recorded in the preview. Receiving audio does not prove accurate lip-sync: that needs the
   operator GPU test. A singing passage with **no cast** cannot sing; the preview warns and the
   passage stays sealed. Only the main singer sings; if they are not cast in a passage, it stays sealed.
2. **Singer and tag are resolved after casting**, per passage, from `casting.cast_for`, never assumed
   to be `<Picture 1>`. Natural-mode casting rules already let a cast entry carry `lines`
   (`RESERVED_FIELDS_NATURAL`), so the singer's job entry carries the lyric lines; every other cast
   entry keeps empty lines. `NATURAL_MOUTHS_RULE` says "do not force sealed lips", so `SINGING_RULES`
   explicitly overrides it for non-singers.
3. **Mixed prompt sets**: singing passages use `writer_system_singing.md`; the cache lookup and run
   recovery take the system file per passage kind. **Cache hits are re-checked** by the same
   deterministic singing check (cached singing prompts that fail are regenerated). The resolved plan
   (mode, singers, per-passage lines and timings) is computed at quote time and stored in
   `prepared.json`; resume replays it and never re-detects or re-aligns.
4. **Laya** drops unknown state fields and has no singing question: its state gets the matching
   natural cast digest and the passage's lines through the existing `lyrics_flavor` field; its
   acceptance is never treated as lip-sync validation. The deterministic check is ours.
5. **The audio definition** the engine adds ("rhythmic and tempo reference") would contradict
   singing, so for singing passages the assembled prompt's audio sentence is replaced outside the
   engine with an owner-approved sentence.
6. **Deterministic singing check** works on the writer response's shot bodies (not the whole prompt):
   the singer's picture tag appears in at least one shot body overlapping a sung line, the sung words are
   quoted there, and no non-singer is described as singing. Tests assert on shot bodies and
   intervals, plus mocked alternating sealed/singing/sealed passages, singer or timing changes
   (cache misses), invalid cached singing prompts, zero cast and resume without detection.
7. **Alignment** requires monotonic, finite, bounded timestamps; ambiguous or unmatched spans are
   reported and need user timing before they drive singing; untimed lyrics keep today's sealed behaviour.

## Wording (approved by the owner, 2026-10-19)

`SINGING_RULES`, appended to the writer system text of singing passages only:

> This passage contains singing. The job carries a `singing` object naming the singer (a cast member),
> the picture tag bound to that member, and the sung lines with their times in seconds from the start of
> the passage. The singer sings exactly those words. In every shot where the singer is visible, describe
> their lips, jaw and breath forming the words being sung at that moment, in time with the music, and
> quote the sung words in that shot's action. Never invent, change or omit words. Every other cast
> member keeps lips firmly sealed and jaw relaxed and does not sing, speak or mouth words; this
> overrides any instruction not to force sealed lips. When the singer is not visible in a shot, state
> that no one on screen is singing.

Audio sentence for singing passages (replaces the rhythm-only sentence):

> {music_tag} is the song's audio for this passage: the singer's lip movements follow the sung vocal
> in it, and its beat and pacing guide the visuals.

## Open questions

1. Overlap threshold (0.75 s) and union rule: confirm on a real vocal clip.
2. Smaller speech models on singing: measure before recommending a size by hardware.
