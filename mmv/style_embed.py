"""Style vector sidecar (<style_id>.emb.json) generation and synchronization.

Pure functions extract aesthetic digests and build normalized vector sidecars.
The sync boundary checks SHA-256 hashes of the digest before querying the
embedding server, skipping re-computation when sources have not changed.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

import numpy as np

Embedder = Callable[[List[str]], np.ndarray]
DEFAULT_MODEL = "Qwen3-Embedding-0.6B-GGUF:Q8_0"


# --------------------------------------------------------------------------- #
# Pure functional core
# --------------------------------------------------------------------------- #
def string_sha256(text: str) -> str:
    """Deterministic SHA-256 hash of a UTF-8 text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_style_digest(style: dict) -> str:
    """Build aesthetic digest from CRAFT and GRAMMAR lines, or fallback to direction.

    The subtraction test strips reference-specific content from CRAFT and
    GRAMMAR, leaving transferable aesthetic directives. FREE AXES are excluded
    because they define what the style intentionally leaves unconstrained.
    """
    card = style.get("style_card") or ""
    craft_grammar: List[str] = []
    if isinstance(card, str) and card.strip():
        for line in card.splitlines():
            line_str = line.strip()
            if line_str.upper().startswith(("CRAFT:", "GRAMMAR:")):
                parts = line_str.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    craft_grammar.append(parts[1].strip())
    if craft_grammar:
        digest = "; ".join(craft_grammar)
    else:
        digest = (style.get("direction") or style.get("name") or "").strip()
    return f"style: {digest}"


def build_sidecar_record(
    style_id: str,
    digest_text: str,
    vector: Sequence[float],
    model: str = DEFAULT_MODEL,
    pooling: str = "last",
) -> dict:
    """Build a serializable .emb.json record with L2-normalized vector."""
    vec = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return {
        "style_id": style_id,
        "model": model,
        "pooling": pooling,
        "dims": int(len(vec)),
        "normalized": True,
        "embed_text_version": 1,
        "embed_text_sha256": string_sha256(digest_text),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vector": [float(x) for x in vec],
    }


def should_recompute_sidecar(
    sidecar_data: Optional[dict],
    current_digest_sha: str,
    expected_model: str = DEFAULT_MODEL,
) -> bool:
    """Pure predicate: True if sidecar is missing or its digest/model hash differs."""
    if not sidecar_data:
        return True
    return (
        sidecar_data.get("embed_text_sha256") != current_digest_sha
        or sidecar_data.get("model") != expected_model
    )


# --------------------------------------------------------------------------- #
# Side-effect boundary: Filesystem and Embedder
# --------------------------------------------------------------------------- #
def sync_style_file(
    style_path: Union[str, Path],
    embed: Embedder,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> Tuple[str, dict]:
    """Sync a single style's .emb.json sidecar.

    Returns:
        (status, sidecar_dict) where status is "skipped" or "updated".
    """
    path = Path(style_path)
    if not path.is_file():
        raise FileNotFoundError(f"Style file not found: {path}")

    style_data = json.loads(path.read_text(encoding="utf-8"))
    style_id = style_data.get("id") or path.stem

    digest_text = extract_style_digest(style_data)
    digest_sha = string_sha256(digest_text)

    sidecar_path = path.parent / f"{style_id}.emb.json"

    if not force and sidecar_path.is_file():
        try:
            cached = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if not should_recompute_sidecar(cached, digest_sha, model):
                print(f"[style:{style_id}] Source digest unchanged (sha256: {digest_sha[:12]}...). Sidecar up to date.")
                return "skipped", cached
        except Exception:
            pass

    print(f"[style:{style_id}] Digest modified or sidecar missing. Waking embedder to generate sidecar...")
    raw_vecs = embed([digest_text])
    sidecar = build_sidecar_record(style_id, digest_text, raw_vecs[0], model=model)
    sidecar_path.write_text(json.dumps(sidecar, indent=1), encoding="utf-8")
    print(f"[style:{style_id}] Sidecar updated ({sidecar['dims']} dims, normalized) -> {sidecar_path.name}")
    return "updated", sidecar


def sync_styles_directory(
    styles_dir: Union[str, Path],
    embed: Embedder,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> dict[str, int]:
    """Sync all style JSON files in a directory, reporting counts."""
    p = Path(styles_dir)
    if not p.is_dir():
        return {"skipped": 0, "updated": 0, "total": 0}

    style_files = [f for f in sorted(p.glob("*.json")) if not f.name.endswith(".emb.json")]
    skipped_count = 0
    updated_count = 0

    for f in style_files:
        status, _ = sync_style_file(f, embed=embed, model=model, force=force)
        if status == "skipped":
            skipped_count += 1
        else:
            updated_count += 1

    print(f"[styles] Sync complete: {skipped_count} up to date (skipped), {updated_count} updated ({len(style_files)} total).")
    return {"skipped": skipped_count, "updated": updated_count, "total": len(style_files)}

