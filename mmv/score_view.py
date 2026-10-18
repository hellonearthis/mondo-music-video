"""Read-only musical score for a finished music video, built from saved run artifacts.

Times are seconds on the final video's clock, so an opening ident shifts the song.
Shot boundaries are the planner's cuts; passage boundaries are guaranteed by
frame-exact assembly, while cuts inside a passage depend on the generated clip.
"""
from __future__ import annotations

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
    fps = float(plan["fps"])
    offset = _opening_offset(store, read_json(directory / "request.json", {}))
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

    return {"title": output.get("title"), "duration": output.get("duration"), "offset": offset,
            "song_end": at(plan["total_frames"]), "tempo_bpm": score.get("tempo_bpm"),
            "beats_per_bar": score.get("beats_per_bar"),
            "beats": [{"time": at(b), "downbeat": b in downbeats, "energy": e}
                      for b, e in zip(beats, score.get("beat_energy", []))],
            "sections": [{"start": at(s["start_frame"]), "end": at(s["end_frame"]), "label": s.get("label"),
                          "energy": s.get("energy")} for s in score.get("sections", [])],
            "passages": passages}
