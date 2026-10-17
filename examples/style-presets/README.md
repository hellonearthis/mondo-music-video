# Optional style presets

Six owner-approved presets for Mondo Music Video:

| ID | Style |
| --- | --- |
| `sun_bleach` | Sun Bleach |
| `nature_doc` | Nature Documentary |
| `industrial_decay` | Industrial Decay |
| `noir_bw` | Noir B&W |
| `gel_wash_psych` | Gel Wash Psych |
| `crt_1990s` | CRT 1990s |

Each JSON file contains the MMV style ID, display name, full aesthetic direction
and a short style card. These public copies preserve the original lighting,
color, film texture and camera direction, with SFW costume/sound wording and
explicit non-sexual content boundaries. Actual generated output still needs
review. The presets are distributed under the repository's Apache-2.0 license.

## Install

Stop MMV before copying files. Copy the six named preset JSON files into the
`styles` folder inside **your MMV application data directory**. Copy neither
`manifest.json` nor this README into that folder. Keep existing files if their
IDs are already installed; choose different IDs/filenames for variants instead
of overwriting your own styles.

Default application data locations:

- Linux/WSL: `~/.local/share/mondo-music-video/`
- macOS: `~/Library/Application Support/mondo-music-video/`
- Windows: `%LOCALAPPDATA%\mondo-music-video\`

`MMV_HOME` or the launcher's `--data-dir` option can select a different directory.
Use the directory your running app actually uses, rather than the defaults when
you have overridden them. Create its `styles` folder if necessary.

Restart MMV and refresh the browser. The styles appear in the Styles panel and
style dropdowns. Alternatively, create a style in the UI using its `id`, `name`
and the entire `direction` value from the JSON file; the optional short style
card is used when installing the complete JSON directly.

`manifest.json` lists the SHA-256 hash of each published preset. No private
studio paths, model selections or render defaults are needed. Adding these
optional assets does not change existing users' locally installed styles.
