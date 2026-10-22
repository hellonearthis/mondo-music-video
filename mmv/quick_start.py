"""One-click music video settings: a random but valid plan from what is installed."""
import random

from mmv.starter_assets import ACTORS as STARTER_CAST

NO_CAST_CHANCE = .25
DANCE_CHANCE = .5
MAX_CAST = 3
DIRECTIONS = (
    "A cinematic performance film that follows the song's energy, with a different place and light for each section.",
    "Dreamlike scenes that drift from calm to intense as the music builds, shot like a bold art-house music video.",
    "A road trip through strange and beautiful places, the camera moving with the rhythm of the song.",
    "A night-time city story of small moments and big feelings, cutting hard on the beat.",
    "A playful, colourful world where everything moves to the music, with a new surprise in every section.",
    "Moody, intimate portraits and wide empty landscapes, trading places as the song rises and falls.",
    "A wild live-show fantasy: huge stages, smoke, lights and a crowd that never stops moving.",
    "Found-footage memories of a summer that never ended, warm, grainy and full of motion.",
)


def pick_cast(actor_ids, rng):
    """The bundled starter cast when installed (else any actors); sometimes nobody, to vary the result."""
    pool = [a for a in STARTER_CAST if a in actor_ids] or list(actor_ids)
    if not pool or rng.random() < NO_CAST_CHANCE:
        return []
    return rng.sample(pool, rng.randint(1, min(MAX_CAST, len(pool))))


def plan(actor_ids, style_ids, rng=None):
    """Settings for a hands-off video. Instruments, subliminal flashes and captions are never chosen."""
    rng = rng or random.Random()
    cast = pick_cast(list(actor_ids), rng)
    dancing = bool(cast) and rng.random() < DANCE_CHANCE
    return {"actors": cast, "dance_mode": "group" if dancing else "off", "dancers": cast if dancing else [],
            "direction": rng.choice(DIRECTIONS), "style_id": rng.choice(list(style_ids)) if style_ids else "daylight"}
