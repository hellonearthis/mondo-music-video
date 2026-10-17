# Visual vocabulary — 1.0.13

Mondo Music Video uses the expanded SFW subset of the vocabulary data explicitly
supplied by the owner. The public extraction originally kept the sampler but
shipped a small selection of entries. This release expands the default data file
at `mmv/engine/config/vocab.json`; there is no connection to a private checkout
at runtime.

| Table | Previous entries | Expanded entries |
| --- | ---: | ---: |
| Settings | 8 | 269 |
| Subject types | 4 | 233 |
| Mechanisms | 5 | 256 |
| Costume | 3 | 31 |
| Tonal registers | 4 | 185 |
| Lighting | 4 | 227 |
| Footage anchors | 3 | 70 |
| Practical effects | 2 | 111 |
| Shot scales | 20 | 20 |
| Camera choices across energy bands | 22 | 22 |
| Mouth-rigging clauses | 1 | 1 |

The source extraction manifest records the owner's authorization, the supplied
file's hash, the published file's hash and per-table counts. Only that data file
was read from the private project. No private code, actors, credentials, models,
production artifacts or Git objects are imported.

## How the existing sampler uses it

`VocabSampler` in `mmv/engine/plan.py` is unchanged. It uses a seeded random
stream and rotates each vocabulary table without repeating a draw until that
table's pool is exhausted. Tone duplicates are removed so repeated strings do
not masquerade as additional choices.

Camera selection is separate: energy selects a camera band and the sampler
chooses within it. Shot scale selection favors close/macro shots at high energy.
Those lists remain unchanged. Because the sampler shares a random stream,
enlarging other pools can still change the camera/shot-scale choices made by
an existing seed.

Thematic montage holds one mechanism as a section's anchor. Standard and
single-subject fragmentation passages share their setting, subject, mechanism,
tone and costume across shots. Other grammars draw more per-shot vocabulary.
These intentional shared choices can repeat on screen even though successive
table draws rotate without repetition.

The writer receives the sampled vocabulary with each planned shot and expands
it into visual prose. The planner still owns cuts and durations. A mechanism
that names a visual/editing effect does not authorize the writer to change
planned timestamps, shot count or musical passage boundaries. Actor appearance
and wardrobe contracts still take precedence over generic vocabulary.

## SFW and rigging adaptations

Two suggestive footage anchors, two potentially revealing costume entries, one
suggestive tone and four suggestive gesture entries are omitted from default
sampling. Four mouth-opening/breath actions are also omitted because they can
conflict with the public sealed-mouth rigging contract. The existing public
rigging clause is retained instead of importing the private mouth-open variants.
Other neutral, romantic, surreal, industrial and theatrical vocabulary remains.

This is vocabulary curation, not a guarantee about model output. Existing content
restrictions, upstream OAP actor checks and Laya review continue to apply.

## Seeds and regression checks

The same seed now selects from much larger tables, so visual vocabulary and
camera framing can differ from earlier releases. Musical timing, montage grammar,
frame counts, reference slots and actor assignments remain unchanged. Tests
verify this across four backends and three seeds.

`tests/fixtures/vocab-legacy.json` preserves the previous small vocabulary for
comparison with the unchanged historical `plan.json`. A separate
`plan-expanded.json` records the new default's seeded result. This keeps the
original parity check useful without pretending that the visual output stayed
identical.
