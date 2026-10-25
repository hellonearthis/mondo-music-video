# Bundled starter props

The owner supplied these instrument sheets for distribution with Mondo Music
Video under Apache-2.0, the project's license. Each folder is an Open Prop
Protocol v0.2 *source tree* (`manifest.json` plus a cleaned reference PNG). The
app packs it into an unsigned `.opp` bundle and imports it into the private props
library on first use, never overwriting an existing prop. Original exports remain
with the owner; only cleaned reference PNGs are bundled.

- `mmv-guitar`: 1360×2048 base sheet.
- `mmv-keyboards`: 1664×2496 base sheet.
- Drums and bass: awaiting owner-supplied sheets; import any OPP prop for them.

Native created resolutions are preserved without upscaling. Each sheet provides
front/rear/side/top/bottom views and detail sections. Some hardware counts differ
between panels; these are initial visual references, not construction drawings.
Generation model provenance is not independently verified.

These are props, not OAP actors. Local imports stay in the private app data
directory and are never collected by package-building globs. Do not copy other
actor/style assets here. See `docs/INSTRUMENTS.md` for the performance mode and
reference-slot rules.
