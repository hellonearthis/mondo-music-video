# Worlds

A world is a persistent, in-universe canon that your videos share. It holds a
seed sentence, core laws, subjects, locations, practices, objects, factions,
ecological rules, moral ambiguities, open threads and a "never contradict" list,
plus a pool of terms for each of seven vocabulary tables: settings, lighting,
mechanisms, wardrobe (costume), practical effects, subject types and tonal
registers. Camera, shot scale, footage and mouth rigging stay with the planner
and the style.

## Building and growing a world

Open **Worlds**, choose *Start a new world* or *Grow an existing world*, and add
any mix of:

- pictures (any image the app can read, up to 24 in all),
- video clips (up to three; eight frames are read from each),
- lore or backstory text (`.txt` or `.md`, up to five files of 60 KB),
- videos you have already made (four frames are read from each, together with
  the vocabulary that video actually used).

Preview shows what will be read; confirm the preview to start. Your vision model
reads the material and writes a **proposal**. A new world shows everything it
would contain; growing a world shows only what would be added, removed or
changed. Accept saves the next version; Reject discards it. Earlier versions are
never overwritten and any can be restored as a new version. A proposal made
against an older version must be made again.

Reading uses your configured vision model, so local models cost nothing. An API
vision profile follows the same preview and consent flow as any paid operation.

## Using a world

Pick a world on the video form. *Only this world's terms* confines each table
the world describes to the world's terms; *Add to the standard pools* adds them
to the standard pools. In both cases the world's "kept out" terms are removed.
Tables the world says nothing about keep their standard pools. Your own custom
vocabulary applies to tables the world does not describe.

## Contrast worlds (optional)

A video that uses a world may also name up to three **contrast worlds**: a
*mirror* (a sister world with the same mood), an *opposite* and a *tangent*. On
intense moments the video borrows places, light, mechanisms and tonal registers
from a contrast world; calm passages stay in the main world. *Departure
strength* (0-100, default 50) sets how readily intense moments leave home. The
choice is deterministic for a given seed, only terms already in a shot are swapped
(cast, wardrobe and subject slots are never touched), a passage whose setting the
planner holds steady departs as a whole so that setting stays steady, and a passage
with a thematic mechanism keeps it. Leave all three empty and the video is made exactly as before.
Agents set `world_contrast` (`{"mirror": id, "opposite": id, "tangent": id}`) and
`world_contrast_strength` on the request; the preview's `world_contrast` entry
reports how many shots depart, and `segments` shows the resulting terms.

## Privacy

Worlds live in `worlds/` and pending proposals in `world-proposals/` inside your
data directory. Neither is packaged, published or committed, and a production
package's shared receipts leave out the world's identity and derived pools.
Export saves a copy of one world's current ledger as `<id>.world.json` for your own backup; the repository's `.gitignore` excludes `*.world.json`, `worlds/` and `world-proposals/` so a world is not committed by accident.

## Agents

Agents can do everything the panel does: `inspect_studio worlds`, `get_world`,
`world_versions`, `create_world` (hand-written), `preview_production` and
`start_production` with `kind: "world_harvest"`, `inspect_world_proposal`,
`accept_world_proposal` (after the user has reviewed the changes),
`reject_world_proposal`, `rollback_world`, `export_world` and `delete_world`
(with explicit authorization). The CLI has matching commands (`worlds`, `world`,
`world-versions`, `create-world`, `world-proposals`, `world-proposal`,
`accept-world-proposal`, `reject-world-proposal`, `rollback-world`,
`export-world`, `delete-world`), and `upload` accepts `video` and `lore`.
