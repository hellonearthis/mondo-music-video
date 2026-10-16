"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
Casting. Who appears in which segment, and under which picture tag.

The division of labour matters and is deliberate:

  the planner owns STRUCTURE  -- how many reference slots a segment carries
  this module owns IDENTITY   -- which actor fills each of those slots

The planner already decides `ref_image_slots` per segment from the ref policy
and the cast size, exactly as it decides frame counts and cut positions: from
the seed, deterministically, before any model is consulted. That keeps a single
source of truth for counts, because a graph built with two LoadImage nodes and
a writer job promising one `<Picture>` tag is a wasted render that fails
silently rather than loudly.

This module then fills those slots with names. It never changes a count. If a
segment has two slots it gets two actors; if it has none it gets none.

Slot order is load-bearing. `WorkflowBuilder.build` numbers image loaders in
list order, so slot 0 is always `<Picture 1>`. The assignment written here is
the same list the renderer walks when wiring loaders and the same list the
writer job quotes as `cast`, so the three can never disagree.

Fairness before randomness: with three actors cast and eleven segments, a naive
per-segment random draw will eventually leave one actor out of an entire video.
The assigner therefore seeds each actor into the pool once before drawing
freely, so everyone cast actually appears.

Policies:
  random   -- seeded random draw, fairness-corrected. The current default.
  rotate   -- strict round robin across segments, in roster order.
  section  -- the cast changes when the song changes section; within a section
              the same actor holds. This is the "one, then the other" reading
              of a music video, tied to musical structure rather than segment
              index.
  manual   -- identities are read from an existing casting.json and preserved.
              This is the seam the future casting director writes through: a
              script is broken down into scenes, a crew assigns parts, and the
              result arrives here as a manual map that this pipeline honours
              without re-deciding anything.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

POLICY_RANDOM = "random"
POLICY_ROTATE = "rotate"
POLICY_SECTION = "section"
POLICY_MANUAL = "manual"

POLICIES = (POLICY_RANDOM, POLICY_ROTATE, POLICY_SECTION, POLICY_MANUAL)

CASTING_VERSION = 1


def picture_tag(slot: int) -> str:
    """Slot index -> prompt tag. Slot 0 is <Picture 1>, and always will be."""
    return f"<Picture {slot + 1}>"


def normalize_roster(roster: list[dict]) -> list[dict]:
    """Accept a loose roster and return one with every field the assigner needs.

    A roster entry describes one castable actor. `sheet_path` is absolute and
    is what the renderer stages into the ComfyUI input folder; `sheet` is the
    actor-relative path recorded for provenance and for the writer contract.
    """
    out = []
    for i, entry in enumerate(roster):
        actor_id = str(entry.get("actor_id") or entry.get("id") or "").strip()
        if not actor_id:
            raise ValueError(f"roster entry {i} has no actor_id")
        out.append({
            "actor_id": actor_id,
            "display_name": str(entry.get("display_name") or actor_id),
            "sheet": entry.get("sheet") or "",
            "sheet_path": str(entry.get("sheet_path") or ""),
        })
    return out


def _fair_pool(n_needed: int, n_actors: int, rng: random.Random) -> list[int]:
    """Indices to draw from, with every actor guaranteed at least one turn.

    Whole shuffled passes are laid end to end and the tail is trimmed, so the
    distribution stays flat instead of drifting toward whoever the seed liked.
    """
    if n_actors <= 0:
        return []
    pool: list[int] = []
    while len(pool) < n_needed:
        block = list(range(n_actors))
        rng.shuffle(block)
        pool.extend(block)
    return pool[:n_needed]


def _assign_random(segments, roster, rng):
    n_actors = len(roster)
    demand = [(i, s["slots"]) for i, s in enumerate(segments) if s["slots"] > 0]
    total = sum(slots for _, slots in demand)
    pool = _fair_pool(total, n_actors, rng)

    result: dict[int, list[int]] = {}
    cursor = 0
    for seg_i, slots in demand:
        picked: list[int] = []
        for _ in range(slots):
            # Never cast the same actor twice in one segment: two LoadImage
            # nodes pointing at one sheet is not a two-shot, it is a clone.
            choice = None
            look = cursor
            while look < len(pool):
                if pool[look] not in picked:
                    choice = pool[look]
                    pool.pop(look)
                    break
                look += 1
            if choice is None:
                spare = [a for a in range(n_actors) if a not in picked]
                if not spare:
                    break
                choice = rng.choice(spare)
            picked.append(choice)
        cursor = 0
        result[seg_i] = picked
    return result


def _assign_rotate(segments, roster, rng):
    n_actors = len(roster)
    result: dict[int, list[int]] = {}
    cursor = 0
    for i, seg in enumerate(segments):
        picked: list[int] = []
        for _ in range(min(seg["slots"], n_actors)):
            picked.append(cursor % n_actors)
            cursor += 1
        result[i] = picked
    return result


def _assign_section(segments, roster, rng):
    """Hold one actor for a whole musical section, then hand over.

    Section boundaries are the planner's, so the cast change lands on a real
    musical seam rather than an arbitrary segment count.
    """
    n_actors = len(roster)
    result: dict[int, list[int]] = {}
    seen_sections: list[int] = []
    for i, seg in enumerate(segments):
        sec = seg.get("section_index", 0)
        if sec not in seen_sections:
            seen_sections.append(sec)
        lead = seen_sections.index(sec) % n_actors
        picked: list[int] = []
        for k in range(min(seg["slots"], n_actors)):
            picked.append((lead + k) % n_actors)
        result[i] = picked
    return result


ASSIGNERS = {
    POLICY_RANDOM: _assign_random,
    POLICY_ROTATE: _assign_rotate,
    POLICY_SECTION: _assign_section,
}


ROLE_LEAD = "lead"
ROLE_SUPPORT = "support"


def cast_entry(slot: int, actor: dict, *, part: str | None = None) -> dict:
    """One character's presence in one segment.

    The shape is deliberately larger than a music video needs. `part`, `lines`
    and `direction` are the scaffolding for scripted work: an actor is hired to
    play a part, a part may have lines, and a scene may carry direction for how
    those lines are delivered. None of the three is consumed by the current
    pipeline. They are written now, empty, so that a casting director agent can
    populate them later without a schema migration and without any downstream
    stage needing to learn a new format.

    `role` IS consumed today. Slot 0 is the lead and the rest are support, which
    is what gives the writer its frame-prominence ordering: the lead takes the
    nearer or larger position and support sits back, so two contracted faces
    never occupy equivalent space in frame.
    """
    return {
        "slot": slot,
        "picture_tag": picture_tag(slot),
        "actor_id": actor["actor_id"],
        "display_name": actor["display_name"],
        "sheet": actor.get("sheet", ""),
        "role": ROLE_LEAD if slot == 0 else ROLE_SUPPORT,
        "part": part or actor["display_name"],
        "lines": [],
        "direction": "",
    }


def population_block(cast_on_screen: int, extras: int = 0) -> dict:
    """The headcount for a segment, contracted and otherwise.

    Reference slots and scene population are different numbers. Every
    contracted character costs an image loader and a slice of conditioning;
    an extra costs nothing but a sentence of prose. A film scene with five
    people in it may have two contracted characters and three extras, and only
    the two need reference sheets. `extras` is always 0 today and is carried so
    that it does not have to be retrofitted.
    """
    return {
        "cast_on_screen": cast_on_screen,
        "extras": extras,
        "target_total": cast_on_screen + extras,
    }


SCENE_RESERVED = {
    "location": None,
    "time_of_day": None,
    "blocking": None,
    "continuity_group": None,
}


def assign(
    plan,
    roster: list[dict],
    *,
    policy: str = POLICY_RANDOM,
    seed: int = 0,
    ref_policy: str = "",
    ensemble_mode: str = "off",
    on_screen=1,
    previous: dict | None = None,
) -> dict:
    """Build the casting map for one plan.

    Returns the casting.json structure. Counts come from the plan and are never
    modified here.
    """
    roster = normalize_roster(roster)
    segments = [
        {
            "segment_id": s.segment_id,
            "montage_type": s.montage_type,
            "section_index": s.section_index,
            "section_label": s.section_label,
            "energy": s.energy,
            "slots": min(int(s.ref_image_slots), len(roster)),
        }
        for s in plan.segments
    ]

    if policy == POLICY_MANUAL:
        if not previous:
            raise ValueError(
                "policy 'manual' needs an existing casting map to read from"
            )
        return _rebuild_manual(previous, segments, roster, ref_policy,
                               ensemble_mode, on_screen)

    if policy not in ASSIGNERS:
        raise ValueError(f"unknown casting policy: {policy}")

    rng = random.Random(seed)
    picks = ASSIGNERS[policy](segments, roster, rng)

    out_segments = {}
    for i, seg in enumerate(segments):
        chosen = picks.get(i, [])
        out_segments[seg["segment_id"]] = {
            "montage_type": seg["montage_type"],
            "section_index": seg["section_index"],
            "section_label": seg["section_label"],
            "slots": len(chosen),
            "population": population_block(len(chosen)),
            "scene": dict(SCENE_RESERVED),
            "cast": [
                cast_entry(slot, roster[a])
                for slot, a in enumerate(chosen)
            ],
        }

    return {
        "version": CASTING_VERSION,
        "policy": policy,
        "seed": seed,
        "ref_policy": ref_policy,
        "ensemble_mode": ensemble_mode,
        "on_screen": on_screen,
        "roster": roster,
        "segments": out_segments,
    }


def _rebuild_manual(previous, segments, roster, ref_policy, ensemble_mode,
                    on_screen):
    """Honour an operator-authored or crew-authored map, clamped to the plan.

    An entry naming an actor who is not on the roster is dropped rather than
    guessed at, and a segment carrying more names than the planner gave it
    slots is trimmed, so a hand-edited file can never desynchronise the graph
    from the writer job.
    """
    by_id = {a["actor_id"]: a for a in roster}
    prev_segments = previous.get("segments", {}) or {}
    out_segments = {}
    for seg in segments:
        entry = prev_segments.get(seg["segment_id"], {}) or {}
        wanted = []
        for member in entry.get("cast", []) or []:
            actor_id = member.get("actor_id")
            if actor_id in by_id and actor_id not in wanted:
                wanted.append(actor_id)
        wanted = wanted[: seg["slots"]]
        prev_entry = prev_segments.get(seg["segment_id"], {}) or {}
        prev_cast = {m.get("actor_id"): m for m in (prev_entry.get("cast") or [])}
        out_segments[seg["segment_id"]] = {
            "montage_type": seg["montage_type"],
            "section_index": seg["section_index"],
            "section_label": seg["section_label"],
            "slots": len(wanted),
            "population": population_block(
                len(wanted),
                int((prev_entry.get("population") or {}).get("extras", 0) or 0),
            ),
            "scene": {**SCENE_RESERVED, **(prev_entry.get("scene") or {})},
            "cast": [
                _manual_entry(slot, by_id[actor_id], prev_cast.get(actor_id))
                for slot, actor_id in enumerate(wanted)
            ],
        }
    return {
        "version": CASTING_VERSION,
        "policy": POLICY_MANUAL,
        "seed": previous.get("seed", 0),
        "ref_policy": ref_policy,
        "ensemble_mode": ensemble_mode,
        "on_screen": on_screen,
        "roster": roster,
        "segments": out_segments,
    }


def _manual_entry(slot, actor, previous_member):
    """Rebuild one hand-authored cast entry, preserving script fields.

    Slot, tag and role are recomputed from the clamped position so a hand-edit
    can never leave a gap in the numbering. Part, lines and direction are the
    author's and are carried through untouched -- that is the whole point of
    the manual policy.
    """
    entry = cast_entry(slot, actor)
    if previous_member:
        entry["part"] = previous_member.get("part") or entry["part"]
        entry["lines"] = list(previous_member.get("lines") or [])
        entry["direction"] = previous_member.get("direction") or ""
    return entry


def cast_for(casting: dict | None, segment_id: str) -> list[dict]:
    """The cast list for one segment, in slot order. Empty when uncast."""
    if not casting:
        return []
    entry = (casting.get("segments") or {}).get(segment_id) or {}
    return list(entry.get("cast") or [])


def load(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save(casting: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(casting, indent=2))
    return p


def sheet_paths(casting: dict) -> dict[str, str]:
    """actor_id -> absolute reference sheet path, for render staging."""
    return {
        a["actor_id"]: a["sheet_path"]
        for a in casting.get("roster", [])
        if a.get("sheet_path")
    }


def report(casting: dict, *, width: int = 78) -> str:
    """The human-readable casting table, printed before a GPU hour is spent."""
    lines = []
    lines.append("=" * width)
    lines.append("🪿 MAXIMUM GOOSE LABORATORY — CASTING REPORT 🪿")
    lines.append("=" * width)
    roster = casting.get("roster", [])
    lines.append(f"Policy: {casting.get('policy')}    Seed: {casting.get('seed')}    "
                 f"Ref policy: {casting.get('ref_policy')}")
    lines.append(f"Ensemble: {casting.get('ensemble_mode')}    "
                 f"On screen: {casting.get('on_screen')}")
    lines.append(f"Cast of {len(roster)}:")
    for a in roster:
        sheet = a.get("sheet") or "(no sheet)"
        lines.append(f"   {a['display_name']}  [{a['actor_id']}]  {sheet}")
    lines.append("-" * width)
    lines.append(f"{'SEGMENT':9s} {'GRAMMAR':40s} {'SEC':4s} {'IN FRAME'}")
    lines.append("-" * width)

    counts: dict[str, int] = {}
    shared = 0
    uncast = 0
    peak_headcount = 0
    for seg_id, entry in casting.get("segments", {}).items():
        members = entry.get("cast") or []
        for m in members:
            counts[m["actor_id"]] = counts.get(m["actor_id"], 0) + 1
        if len(members) >= 2:
            shared += 1
        if not members:
            uncast += 1
        peak_headcount = max(peak_headcount, len(members))
        who = " + ".join(
            f"{m['display_name']} {m['picture_tag']}"
            f"{'*' if m.get('role') == ROLE_LEAD and len(members) > 1 else ''}"
            for m in members
        )
        lines.append(
            f"{seg_id:9s} {entry.get('montage_type', ''):40s} "
            f"{entry.get('section_index', 0):<4d} {who or '—'}"
        )

    lines.append("-" * width)
    total = len(casting.get("segments", {}))
    lines.append(f"{total} segments: {total - uncast} cast, {uncast} uncast, "
                 f"{shared} with more than one character in frame")
    lines.append(f"Largest frame population: {peak_headcount} contracted "
                 f"character(s)")
    if peak_headcount > 1:
        lines.append("* marks the lead, who takes the nearer or larger position "
                     "in frame.")
    for a in roster:
        n = counts.get(a["actor_id"], 0)
        flag = "   <-- never appears" if n == 0 else ""
        lines.append(f"   {a['display_name']}: {n} segment(s){flag}")
    if peak_headcount >= 3:
        lines.append("")
        lines.append("NOTE: three or more contracted faces in one frame is the "
                     "highest identity-bleed risk this system can produce.")
        lines.append("Render one segment before committing a full run. If faces "
                     "blend, drop --on-screen to 2 or use --ensemble-mode mixed.")
    lines.append("=" * width)
    return "\n".join(lines)
