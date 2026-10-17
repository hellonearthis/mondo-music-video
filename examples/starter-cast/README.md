# Starter cast

Four owner-selected actors are supplied as signed, full Open Actor Protocol
packages. Each contains one reference sheet and its visual description and rider.

| Actor ID | Display name | Package |
| --- | --- | --- |
| `animal_pig` | Hambo | [Download](animal_pig.oap) |
| `robobabe1` | Robotic Woman | [Download](robobabe1.oap) |
| `henchman_1` | Henchman #1 | [Download](henchman_1.oap) |
| `human_female_casual_01` | Human Female Casual #1 | [Download](human_female_casual_01.oap) |

## Import

Agent-assisted installation includes these four actors by default unless you
decline, with package/signature verification and explicit signer acceptance.
Existing actor IDs are preserved. See the
[agent installation guide](../../docs/INSTALL_WITH_AGENT.md). For manual import:

The platform installers also include this step. Interactive setup asks once for
acceptance of the verified starter signer. Noninteractive setup imports actors
with `--accept-starter-signer` (PowerShell: `-AcceptStarterSigner`); without it,
actors are reported as pending signer approval. The standalone command is
`mondo-music-video install-starter-assets --accept-starter-signer` with the app
stopped. Starter assets are also included in installed wheels.

To remove an unwanted actor, click **Delete actor** on its Actors & OAP card
and confirm. Export first if you want a backup. Completed videos and previous
exports are retained. Deletions survive restarts and installer reruns; add
`--restore` to the standalone starter command only when you want them restored.

1. Open **Actors & OAP** and choose one of these `.oap` files under **Bring an actor
   with OAP**. For a GitHub download, open the file and use **Download raw file**.
2. Click **Inspect package**, review the reference identity, content rider and
   signature report, and explicitly acknowledge the signer before importing.
   These packages are signed; **Allow an unsigned package** is unnecessary.
3. Import the actor. Repeat for the other packages you want, then select them in
   the music-video cast selector.

Packages use a dedicated starter-cast signing identity, so a new installation
will report a valid signature with a signer it does not yet trust. Signatures
verify integrity and authorship, not endorsement. Check `manifest.json` here for
package and reference-image SHA-256 hashes.

Imports never overwrite an existing actor. If an ID already exists, keep your
local actor or choose a different local ID. You can decline the starter cast;
the app launcher alone does not import actors into your roster.

These four actor assets are distributed under the repository's Apache-2.0
license; their OAP riders remain available for production checks. No voice,
private signing keys, studio metadata backups or other roster members are
included.
