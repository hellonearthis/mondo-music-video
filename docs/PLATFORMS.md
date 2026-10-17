# Platform support — 1.2.2

| Environment | Setup launcher | Verification status |
| --- | --- | --- |
| Linux | `install.sh` | Fresh Python 3.12 environment installed from public dependencies; 37 automated checks, Chromium, GPU Laya and a real local H3 music-video production; see VERIFICATION.md |
| Windows / WSL2 | `install.sh` inside WSL | Launcher included; full clean-machine and GPU verification pending |
| Native Windows | `install.ps1` | Launcher included; execution and GPU verification pending |
| macOS | `install.sh` | Launcher included; execution pending; use hosted renderers unless a compatible local runtime is independently established |

Python 3.11+, Git and FFmpeg/ffprobe are prerequisites. Dependency installation
requires internet access. The installer does not run OS package
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

The optional Comfy SDK renderer uses Python SDK/proxy packages and a loopback
ComfyUI installation. Linux transport, synthetic assembly and official-proxy
checks are covered by automated tests. Real H3 rendering through the proxy and
Windows/macOS execution remain unverified. See [COMFY_SDK.md](COMFY_SDK.md).

The 1.0.13 model settings/path-picker integration is verified with Linux mock
services and Chromium. Windows JSON lock retries are tested with simulated
permission errors; native Windows filesystem browsing and real model switching
remain operator checks. Parallel tests use four workers by default; use
`python -m pytest -n 0` for a serial run.

The 1.1.1 integration is verified on Linux using mock services and Chromium.
The Windows launcher adds opt-in context/batch/image-token presets and UTF-8
JSON settings transfer; native PowerShell execution remains unverified. Laya
CPU fallback is selectable rather than silently changing an explicit CUDA/MPS
choice. See [local writer tuning](LOCAL_WRITER_TUNING.md).

Startup updater logic in 1.1.3 is covered on Linux with disposable Git remotes,
mock installation, Chromium and offline real pip/mock-wheel checks. Native
Windows locking, package replacement and restart still need operator verification.
Automatic installation is off by default on every platform.
