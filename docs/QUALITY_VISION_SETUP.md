# Quality Vision Setup & Architecture Guide

This guide explains how **Vision Services** work in Mondo Music Video: the difference between **Style Harvest Vision** and **Quality Vision (Frame Checker)**, how each is configured and launched, and how to verify their operation.

---

## 0. Style Harvest Vision vs. Quality Vision (Frame Checker)

Mondo uses two separate vision capabilities that serve distinct roles:

| Capability | Role | When It Runs | Where It Is Configured | Needs mmproj? |
| :--- | :--- | :--- | :--- | :--- |
| **Style Harvest Vision** | Reads uploaded reference images and writes an 11-axis visual style card (`CRAFT`, `GRAMMAR`, `AFFECT`, etc.) | When clicking **Preview harvest** on **05. Style Harvest** | In **12. Settings** under **Vision Service Endpoint** (e.g. `http://127.0.0.1:8080/v1` or remote API like Gemini / OpenAI) | **Yes** if using local `llama-server`; **No** if using an API provider |
| **Quality Vision** | Inspects rendered video frames for unrequested borders, letterboxing, or visual artifacts | After video generation completes when **Vision quality check** is enabled | Derived automatically from **Writer Launch** command (`writer_launch`) in **12. Settings**; boots dynamically on port `8083` | **Yes**, requires a sibling `mmproj*.gguf` in the writer model directory |

> **Note for Style Harvesting:** You do **not** need Quality Vision to harvest visual styles. Style Harvest only requires your standard **Vision Service Endpoint** in Settings.

---

## 1. What is Quality Vision?

Quality Vision is Mondo's automated inspection stage that evaluates rendered video clips when the **Vision quality check** toggle is enabled during production.

```text
[Render Video Clip] ──► [Extract Sampled Frames (PNG)] ──► [Quality Vision (Port 8083)] ──► [Pass / Warn / Fail]
```

- **What it checks:**
  - Unrequested borders, letterboxing, pillarboxing, and framing devices (e.g. simulated TV frames, phone screens, split screens).
  - Visual glitches, severe artifacts, and rendering corruption.
- **Decision logic:**
  - If 2 or more sampled frames show unrequested framing devices, the passage **fails** and triggers an automatic re-render.
  - Minor defects produce a warning note in the production output without failing the run.
- **Resource management:**
  - Quality Vision does **not** stay running permanently. It remains offline during rendering to preserve GPU VRAM for ComfyUI.
  - Mondo starts it automatically on port `8083` right after rendering finishes, judges the frames in seconds, and terminates it when done.

---

## 2. How Mondo Derives the Launch Command

Unlike third-party APIs that use fixed remote URLs, local Quality Vision is derived dynamically from your local **Writer Launch** setting (`writer_launch` in `settings.json`):

1. **Model Discovery:** Mondo inspects the `-m` (or `--model`) parameter in `writer_launch`.
2. **Sibling Projector Matching:** It looks in the **same directory** as the model file for exactly one matching multimodal projector (`mmproj*.gguf`) matching the model family:
   ```text
   C:\llamaCPP\models\Qwen3-VL-4B-Instruct-GGUF\
   ├── Qwen3-VL-4B-Instruct-Q4_K_M.gguf          <-- Base model (-m)
   └── mmproj-Qwen3-VL-4B-Instruct-F16.gguf     <-- Sibling projector (--mmproj)
   ```
3. **Command Generation:** Mondo rewrites the port to `8083`, sets `--alias mmv-vision`, `-c 16384`, `--temp 0`, and adds `--mmproj <sibling_path>`.

---

## 3. The Error Explained

### The Error Message:
```text
Cannot be launched: expected one matching sibling mmproj*.gguf for Qwen3-VL-4B-Instruct-Q4_K_M.gguf; found 0
```

### Why it happened:
- When `start.ps1` configured `settings.json`, it previously stored a **relative path**:
  `"models\\Qwen3-VL-4B-Instruct-GGUF\\Qwen3-VL-4B-Instruct-Q4_K_M.gguf"`.
- When the web application executed inside its working directory (`c:\Users\Desktop-Dev\Desktop\hodge`), Python looked for `hodge\models\Qwen3-VL-4B-Instruct-GGUF\mmproj*.gguf`, which does not exist because your models live in `C:\llamaCPP\models\`.
- Finding 0 matching projectors in the expected directory triggered the `ValueError`.

---

## 4. What Was Done to Fix It

1. **Updated [`start.ps1`](file:///c:/Users/Desktop-Dev/Desktop/hodge/start.ps1):**
   - Changed `$selectedModel.RelativePath` to `$selectedModel.FullPath`.
   - Now `writer_launch` always stores absolute file paths (e.g. `C:\llamaCPP\models\Qwen3-VL-4B-Instruct-GGUF\Qwen3-VL-4B-Instruct-Q4_K_M.gguf`).
2. **Hardened [`mmv/vision_check.py`](file:///c:/Users/Desktop-Dev/Desktop/hodge/mmv/vision_check.py):**
   - Added automatic fallback resolution: if a relative model path is supplied in `writer_launch`, Mondo automatically checks `C:\llamaCPP` and `C:\llamaCPP\models` before failing.
3. **Updated `settings.json`:**
   - Synchronized your active `settings.json` with the full absolute model path.

---

## 5. Requirements for Quality Vision Models

If you switch writer/vision models in the future, ensure the following requirements are met:

| Requirement | Details |
| :--- | :--- |
| **Model Type** | Must be a Vision-Language Model (e.g. `Qwen3-VL-4B-Instruct`, `Qwen3-VL-8B-Instruct`). Text-only models cannot perform frame checks. |
| **Folder Collocation** | The model's `.gguf` file and its matching `mmproj-*.gguf` projector must reside in the **same directory**. |
| **Projector Naming** | The projector filename must start with `mmproj-` and share the model's family name (e.g. `mmproj-Qwen3-VL-4B-Instruct-F16.gguf` matches `Qwen3-VL-4B-Instruct-Q4_K_M.gguf`). |
| **Sibling Count** | Exactly **one** matching projector file per folder. Multiple ambiguous projectors for the same model will trigger a validation error. |

---

## 6. How to Verify Quality Vision Status

### Web UI
Open the Mondo Web UI (`http://127.0.0.1:8091`) and inspect the **Services** panel on the Video production page:
- **Vision (Quality Check):**
  - **Activity:** `Offline`
  - **Detail:** `Offline · Mondo starts it when the vision check runs`
  - *(This indicates the launch command is verified and ready to fire on demand).*

### CLI Verification
Run this command from PowerShell:
```powershell
python -c "from mmv.storage import Storage; from mmv.services import check_services; print(check_services(Storage(), force=True)['vision_quality'])"
```

**Expected output:**
```python
{
    'id': 'vision_quality',
    'name': 'Vision',
    'role': 'Quality Check',
    'url': 'http://127.0.0.1:8083',
    'available': False,
    'has_launch': True,
    'port_in_use': False,
    'error': None,
    'activity': 'offline',
    'detail': 'Offline · Mondo starts it when the vision check runs',
    'model': 'mmv-vision'
}
```
*(Notice `has_launch: True`, `error: None`, and `activity: 'offline'`).*

