  Here is a breakdown of the current friction points in setup.py and
  concrete ideas for improving the setup of Laya, llama.cpp, and the
  overall onboarding flow.
  ──────
  ### 1. Laya Setup Improvements

  Currently, download_models in setup.py iterates through the 5 entries
  in laya-download.json and prompts the user to type yes 5 separate times
  (once for the 842 MB .safetensors file and 4 more times for tiny JSON
  config/tokenizer files from the exact same repo and license).
  Furthermore, if any file already exists or a .partial file is left
  behind from a dropped connection, it raises a hard ValueError instead
  of skipping or resuming.

  • Single-consent batch approval per license/repo: Group manifest
  entries that share the same license_url / repository so the user sees
  the total size (~846 MB across 5 files) and types yes once for Laya
  instead of 5 times in a row.
  • Skip already-verified files & auto-clean stale .partial files: Right
  now, if file 3 of 5 fails mid-download, re-running mondo-music-video
  download-laya errors out on file 1 (Destination already exists).
  Checking the SHA-256 of existing files and skipping valid ones (and
  overwriting/resuming .partial files) makes download-laya idempotent.
  • Download progress indicator: Downloading an 842 MB file via urllib.
  request in download_models prints nothing until completion, which can
  look hung on slower connections. Adding a simple inline progress
  percentage/MB counter in the terminal (and/or a one-click "Download
  Laya" button in the Web UI Settings panel) removes the guesswork.
  • **PyTorch CUDA wheel detection in install.ps1 / install.sh**: On
  Windows especially, a plain pip install . pulls the CPU-only PyTorch
  wheel from PyPI by default, causing configure to fall back to cpu even
  when an NVIDIA GPU is present. Detecting nvidia-smi in the install
  script and passing --extra-index-url https://download.pytorch.
  org/whl/cu124 (or cu126) ensures Laya actually gets CUDA out of the box.
  ──────
  ### 2. llama.cpp (llama-server) Setup Improvements

  In configure, setting up a local writer requires the user to manually
  obtain llama-server, know its binary path, know the exact path to a
  .gguf file, and accept a hardcoded 64k context (-c 65536) launch
  command that may OOM on 8–12 GB GPUs.

  • Auto-detect or download prebuilt llama-server binaries:
      • First, check shutil.which("llama-server") as well as common
      install locations (winget,  scoop, Homebrew, LM Studio, or store.
      home / "bin").
      • Offer an opt-in helper (similar to download-laya, e.g. mondo-
      music-video download-llama) that fetches the official prebuilt
      llama.cpp release zip for the user's OS/GPU (CUDA / Metal / Vulkan
      / CPU) from GitHub Releases, verifies its SHA-256, and extracts
      llama-server into store.home / "bin".
  • Pinned / Recommended Writer GGUF manifest:
      • Users often don't know which GGUF model or quantization works
      best with Mondo's JSON schema and prompt structure. Providing a
      curated manifest (or 2 tiers based on detected VRAM in doctor, e.g.,
      an 8B/14B Q4_K_M for 8–12 GB VRAM and a 32B Q4_K_M for 24 GB+ VRAM)
      lets users download a known-good writer GGUF into store.home /
      "models/writer" using the existing download_models infrastructure.
  • Auto-discover local .gguf files & existing local servers:
      • Just like configure_standard_graph scans for .safetensors in
      ComfyUI, setup can scan store.home / "models", ~/.cache/lm-
      studio/models, and ~/.cache/huggingface to list discovered .gguf
      files so the user doesn't have to copy-paste long paths.
      • Alternatively, if the user already runs Ollama, LM Studio, or an
      external llama-server, setup can probe localhost:8080/v1/models,
      localhost:11434/v1/models, and localhost:1234/v1/models and let
      them pick an already-available model name directly.
  • VRAM-aware writer_launch defaults:
      • Currently configure hardcodes -c 65536 and -ngl all. Since doctor
      already queries nvidia-smi --query-gpu=name,memory.total, setup can
      size -c (e.g., 16384 or 32768 on ≤12 GB VRAM vs. 65536 on ≥16 GB
      VRAM) so the generated launch command works reliably on midrange
      cards.

  ──────
  ### 3. ComfyUI & General Setup Flow (Low-Touch Quality-of-Life)

  Even leaving ComfyUI as an external install, a few small touches can
  make connecting it much smoother:

  • Expanded path & Desktop/Portable detection: On Windows, ComfyUI is
  frequently installed as the standalone portable package
  (ComfyUI_windows_portable\ComfyUI with ..\python_embeded\python.exe) or
  ComfyUI Desktop. Auto-detecting python_embeded\python.exe relative to
  the ComfyUI folder avoids the user having to hunt for the embedded
  Python path.
  • Numbered selection instead of typing filenames: In
  configure_standard_graph, when .safetensors files are found in
  models/vae, models/diffusion_models, or models/text_encoders, letting
  the user type 1 to pick from the numbered list (or auto-selecting when
  there is an exact/single match) avoids typos.
  • Configure from the Web UI first (serve without mandatory CLI wizard):
  Running install.ps1 or install.sh immediately drops into the 15-
  question CLI configure prompt. Booting straight into the web UI (or
  offering a "Setup Wizard / Doctor" status banner in the Settings tab
  with "Test Connection" and "Download Laya" buttons) is much friendlier
  than answering raw CLI prompts before ever seeing the app.

  Would you like to explore or implement any of these—such as
  streamlining the Laya downloader, adding GGUF/llama-server auto-
  detection and presets, or fixing the Windows CUDA PyTorch install?
