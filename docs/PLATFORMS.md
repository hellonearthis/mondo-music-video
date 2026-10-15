# Platform support — 0.1.0

| Environment | Setup launcher | Verification status |
| --- | --- | --- |
| Linux | `install.sh` | Fresh Python 3.12 environment installed from public dependencies; 23 checks and real FFmpeg assembly passed; AI services mocked |
| Windows / WSL2 | `install.sh` inside WSL | Launcher included; full clean-machine and GPU verification pending |
| Native Windows | `install.ps1` | Launcher included; execution and GPU verification pending |
| macOS | `install.sh` | Launcher included; execution pending; use hosted renderers unless a compatible local runtime is independently established |

Python 3.11+, Git and FFmpeg/ffprobe are prerequisites. Dependency installation
requires internet access. This preview intentionally does not run OS package
managers, request administrator rights, or install GPU drivers automatically.

Run `mondo-music-video doctor` to inspect OS, Python, paths, FFmpeg, optional
NVIDIA detection and configured services. Detection is not proof that a model
fits your hardware. No model runtime is downloaded during normal installation.

The Topaz action requires an installed, licensed Topaz-compatible FFmpeg binary
and installed model metadata. Native execution and WSL-to-Windows path handling
are implemented but real exports remain unverified. On WSL, configure paths in
WSL notation; on Windows use native paths. Other Topaz/platform combinations
must be tested individually and are not claimed as supported.

The app uses filesystem permissions for its credential file. Windows users
should keep their application data under their private user profile and apply
appropriate Windows ACLs; POSIX mode bits are not a Windows access-control claim.
