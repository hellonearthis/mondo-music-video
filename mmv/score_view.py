"""Read-only musical score for a finished music video, built from saved run artifacts.

Times are seconds on the final video's clock, so an opening ident shifts the song.
Shot boundaries are the planner's cuts; passage boundaries are guaranteed by
frame-exact assembly, while cuts inside a passage depend on the generated clip.
"""
from __future__ import annotations

import re
from pathlib import Path

from .storage import identifier, inside, read_json

GRAMMARS = {
    "standard": ("Standard", "One subject, sustained observation, fewer and longer shots."),
    "type3_thematic_multi_scene": ("Thematic multi-scene",
                                   "New subjects and settings connected by one thematic anchor."),
    "type2_chaotic_multi_scene": ("Chaotic multi-scene",
                                  "New subjects, settings and actions in discontinuous collisions."),
    "type1_single_subject_fragmentation": ("Single-subject fragmentation",
                                           "A recurring subject seen through many angles and shot scales."),
}


def _opening_offset(store, request):
    opening = request.get("start_ident")
    if not opening:
        return 0.0
    record = read_json(inside(store.home / "runs", opening).parent / "output.json", {})
    return float(record.get("duration") or 0.0)


def music_score(store, run_id):
    directory = store.home / "runs" / identifier(run_id)
    output = read_json(directory / "output.json")
    if not output or output.get("kind") != "video":
        raise ValueError("A musical score is available only for completed music videos")
    score, plan = read_json(directory / "score.json"), read_json(directory / "plan.json")
    if not isinstance(score, dict) or not isinstance(plan, dict):
        raise ValueError("This video has no saved musical analysis")
    source = read_json(directory / "assembly-source.json", {})
    offset = (source["song_start_frame"] / source["fps"] if "song_start_frame" in source
              else _opening_offset(store, read_json(directory / "request.json", {})))
    return build_score(score, plan, offset=offset, title=output.get("title"), duration=output.get("duration"))


def build_score(score, plan, *, offset=0.0, title=None, duration=None):
    """The score structure from a saved or freshly prepared analysis and plan (both as dicts)."""
    fps = float(plan["fps"])
    at = lambda frame: round(offset + frame / fps, 4)
    beats, downbeats = list(score["beat_frames"]), set(score["downbeat_frames"])
    beat_set = set(beats)

    passages = []
    for segment in plan["segments"]:
        start = segment["song_start_frame"]
        end = start + segment["trim_frames"]
        name, description = GRAMMARS.get(segment["montage_type"], (segment["montage_type"], ""))
        shots = []
        for index, shot in enumerate(segment["shots"]):
            frame = start + shot["start_frame"]
            # The first shot opens the passage; later cuts were placed on beats or split long holds.
            cut = ("passage" if index == 0 else "downbeat" if frame in downbeats
                   else "beat" if frame in beat_set else "split")
            shots.append({"start": at(frame), "end": at(min(frame + shot["frames"], end)), "cut": cut,
                          "camera": shot.get("camera"), "shot_scale": shot.get("shot_scale")})
        passages.append({"index": segment["index"], "start": at(start), "end": at(end),
                         "on_downbeat": start in downbeats,
                         "section": segment.get("section_label"), "energy": segment.get("energy"),
                         "grammar": name, "grammar_description": description,
                         "beats": sum(1 for b in beats if start <= b < end), "shots": shots})

    return {"title": title, "duration": duration, "offset": offset,
            "song_end": at(plan["total_frames"]), "tempo_bpm": score.get("tempo_bpm"),
            "beats_per_bar": score.get("beats_per_bar"),
            "beats": [{"time": at(b), "downbeat": b in downbeats, "energy": e}
                      for b, e in zip(beats, score.get("beat_energy", []))],
            "sections": [{"start": at(s["start_frame"]), "end": at(s["end_frame"]), "label": s.get("label"),
                          "energy": s.get("energy")} for s in score.get("sections", [])],
            "passages": passages}


CLIP_SUFFIXES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


def _origin_run(store, run_id, seen=()):
    """A captioned or other derived output keeps no prompts; follow its `source` back to the run that rendered it."""
    directory = inside(store.home / "runs", identifier(run_id))
    output = read_json(directory / "output.json", {})
    if not output:
        raise ValueError("Output not found")
    source = str(output.get("source") or "").split("/")[0]
    rendered_here = (directory / "plan.json").is_file() or (directory / "prompts.json").is_file()
    if source and not rendered_here and source not in seen and len(seen) < 8:
        return _origin_run(store, source, (*seen, run_id))
    return run_id


def _run_files(store, run_id):
    directory = inside(store.home / "runs", identifier(run_id))
    plan = read_json(directory / "plan.json", {}) or read_json(directory / "prepared.json", {}).get("plan") or {}
    return plan, read_json(directory / "prompts.json", {}) or {}, read_json(directory / "renders.json", {}) or {}


def _clip_roots(store):
    """Renderer clips are served only from the data folder or the configured ComfyUI output folder."""
    configured = store.settings().get("comfy_output")
    return [store.home.resolve(), *([Path(configured).expanduser().resolve()] if configured else [])]


def _recorded_clip(renders, segment_id, roots):
    """The renderer's original clip recorded for this passage, or None. Only this exact path is ever served."""
    got = renders.get(segment_id)
    video = got.get("video") if isinstance(got, dict) else None
    if not video:
        return None
    path = Path(video).resolve()
    allowed = path.suffix.lower() in CLIP_SUFFIXES and any(path.is_relative_to(root) for root in roots)
    return path if allowed and path.is_file() else None


def _passage(run_id, segment_id, index, prompt, clip, *, seconds=0.0, frames=0, shots=()):
    return {"index": index, "segment_id": segment_id, "prompt": prompt, "duration": seconds, "trim_frames": frames,
            "shots": list(shots), "has_clip": clip is not None,
            "clip_url": f"/api/outputs/{run_id}/clips/{segment_id}" if clip else None}


def passage_breakdown(store, run_id):
    """Each passage's written prompt, planned shots and whether its original rendered clip is available."""
    run_id = identifier(run_id)
    output = read_json(inside(store.home / "runs", run_id) / "output.json", {})
    origin = _origin_run(store, run_id)
    plan, prompts, renders = _run_files(store, origin)
    roots, fps = _clip_roots(store), plan.get("fps", 24)
    if plan.get("segments"):
        passages = [_passage(origin, sid, seg["index"], prompts.get(sid, ""), _recorded_clip(renders, sid, roots),
                             seconds=round(seg.get("trim_frames", 0) / fps, 3), frames=seg.get("trim_frames", 0),
                             shots=({k: shot.get(k) for k in ("n", "shot_scale", "camera", "cut_time")}
                                    for shot in seg.get("shots", [])))
                    for seg in plan["segments"] for sid in [f"seg{seg['index']:03d}"]]
    else:
        passages = [_passage(origin, sid, int(sid[3:]) if sid[3:].isdigit() else i, prompt,
                             _recorded_clip(renders, sid, roots))
                    for i, (sid, prompt) in enumerate(sorted(prompts.items()))]
    return {"run_id": run_id, "source_run_id": origin, "title": output.get("title", "Finished production"),
            "kind": output.get("kind", "video"), "segments": passages}


def passage_clip(store, run_id, segment_id):
    """Path and media type of one passage's recorded original clip."""
    if not re.fullmatch(r"seg\d{3,4}", segment_id or ""):
        raise ValueError("Invalid passage ID")
    path = _recorded_clip(_run_files(store, _origin_run(store, run_id))[2], segment_id, _clip_roots(store))
    if path is None:
        raise ValueError("The original clip for this passage is not available")
    return path, CLIP_SUFFIXES[path.suffix.lower()]
