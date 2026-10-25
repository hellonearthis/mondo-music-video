# Qwen3-Embedding-0.6B Setup Guide

This guide describes how to install, configure, and run the **Qwen3-Embedding-0.6B** model with `llama-server` for vocabulary clustering, deduplication, and style vector embedding sidecars (`.emb.json`).

---

## 1. Status Overview

- **Is it currently installed?** **No.**
  A scan of `C:\llamaCPP\models\` shows existing models (`Qwen3-VL-4B-Instruct`, `Qwen3-VL-8B-Instruct`, `Qwen2.5-Coder-14B`, `nomic-embed-text-v1.5`), but `Qwen3-Embedding-0.6B-GGUF` is not yet installed.
- **Runtime:** `C:\llamaCPP\llama-server.exe` (build 11205) is already installed and supports direct Hugging Face model fetching and embedding endpoints.

---

## 2. Model Specifications

| Parameter | Value |
| :--- | :--- |
| **Model Repository** | [`Qwen/Qwen3-Embedding-0.6B-GGUF`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF) |
| **Recommended Quant** | `Q8_0` (~639 MB) or `Q4_K_M` (~380 MB) |
| **Parameter Count** | ~0.6B parameters |
| **Embedding Dimensions** | 1,024 float dimensions (supports Matryoshka down to 256) |
| **Pooling Mode** | **`last`** (Last-token pooling) |
| **Hardware Overhead** | ~650 MB RAM on CPU (`-ngl 0`), 0 GPU VRAM required |
| **Default Port** | `8092` |

> [!IMPORTANT]
> **Pooling Requirement:** Qwen3-Embedding series models require **last-token pooling** (`--pooling last`). Do not use `--pooling mean` (which is for BGE/Nomic). Using the wrong pooling mode produces distorted vectors that break clustering and similarity checks.

---

## 3. Quick Setup & Launch Options

### Option A: Launch Directly via `llama-server` (Auto-Download)

`llama-server` can fetch and cache the model from Hugging Face automatically:

```powershell
Set-Location "C:\llamaCPP"
.\llama-server.exe -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --embeddings --pooling last --port 8092 -ngl 0
```

*When run for the first time, `llama-server` downloads the ~639 MB `Q8_0` GGUF file to its local cache and immediately starts serving on port `8092`.*

---

### Option B: Download Manually into `C:\llamaCPP\models\Qwen`

If you prefer to keep a persistent `.gguf` file inside your local models directory:

1. **Download the GGUF file:**
   Open PowerShell and run:
   ```powershell
   New-Item -ItemType Directory -Force -Path "C:\llamaCPP\models\Qwen\Qwen3-Embedding-0.6B-GGUF"
   Set-Location "C:\llamaCPP\models\Qwen\Qwen3-Embedding-0.6B-GGUF"

   # Download Q8_0 (~639 MB)
   Invoke-WebRequest -Uri "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf" -OutFile "Qwen3-Embedding-0.6B-Q8_0.gguf"
   ```

   *(Alternative: If using huggingface-cli: `huggingface-cli download Qwen/Qwen3-Embedding-0.6B-GGUF Qwen3-Embedding-0.6B-Q8_0.gguf --local-dir C:\llamaCPP\models\Qwen\Qwen3-Embedding-0.6B-GGUF`)*

2. **Launch `llama-server` pointing to the file:**
   ```powershell
   Set-Location "C:\llamaCPP"
   .\llama-server.exe -m models\Qwen\Qwen3-Embedding-0.6B-GGUF\Qwen3-Embedding-0.6B-Q8_0.gguf --embeddings --pooling last --port 8092 -ngl 0
   ```

---

## 4. Key CLI Flags Explained

- `--embeddings`: Enables the OpenAI-compatible `/v1/embeddings` endpoint and `/embeddings` native route.
- `--pooling last`: Instructs the engine to extract the embedding vector from the final token position.
- `--port 8092`: Dedicated port to prevent collisions with the web application (`8080`), vision LLM (`8081`), or ComfyUI (`8188`).
- `-ngl 0`: Runs purely on CPU. Embedding 0.6B is virtually instantaneous on modern CPUs and preserves all GPU VRAM for video and image generation pipelines.
- `--parallel 4`: (Optional) Allows handling up to 4 concurrent embedding requests if batching large vocabularies.

---

## 5. Verifying the Server

To verify that the embedding server is up and returning valid 1,024-dimension vectors:

```powershell
$response = Invoke-RestMethod -Uri "http://127.0.0.1:8092/v1/embeddings" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"input": "settings: monolithic concrete atrium"}'

Write-Host "Model returned:" $response.model
Write-Host "Embedding vector dimension:" $response.data[0].embedding.Count
```

**Expected output:**
```text
Model returned: Qwen3-Embedding-0.6B-Q8_0.gguf
Embedding vector dimension: 1024
```

---

## 6. How It Integrates with the Codebase

### 1. Vocabulary Clustering (`cluster_vocab.py`)
Run the clustering tool against the live embedding endpoint:
```powershell
python cluster_vocab.py --server http://127.0.0.1:8092 --output data/vocabulary_clusters.json
```
The script embeds each vocabulary entry with its category context prefix (e.g. `settings: brutalist transit hall`), applies cosine distance clustering, and outputs cluster assignments for rotation and anti-repetition.

### 2. Style Sidecar Embeddings (`.emb.json`)
When indexing or importing a style card:
1. Strip subject nouns to leave only craft and grammar directives.
2. Prefix with `style:`:
   ```text
   style: Monochrome charcoal tonal structure; crushed blacks at 0-5 IRE; coarse 35mm silver halide grain; hard raking light
   ```
3. Query `http://127.0.0.1:8092/v1/embeddings`.
4. Unit-normalize the vector and write the `.emb.json` sidecar alongside the style file.

