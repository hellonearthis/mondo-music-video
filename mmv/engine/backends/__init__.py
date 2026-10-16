"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
backends — the pluggable renderer registry.

get_backend() with no argument returns the default, and the default is
local_h3: the operator's local ComfyUI MiniMax H3 pipeline, exactly as it
has always behaved. Remote providers register here as they land (Task A
step 3 onward); none of them ever becomes the default silently.

Every backend is validated against the capability contract at construction,
so an incomplete declaration fails at get_backend() with a named list of
missing keys instead of failing mid-plan with a KeyError.
"""

from __future__ import annotations

from .base import Backend, BackendError, REQUIRED_CAPABILITY_KEYS
from .local_h3 import LocalH3Backend
from .wavespeed import WaveSpeedH3Backend
from .seedance import (
    Seedance2Backend,
    Seedance25Backend,
    rate_card_ready,
    rate_card_refusal,
)

DEFAULT_BACKEND = "local_h3"

_REGISTRY: dict[str, type[Backend]] = {
    "local_h3": LocalH3Backend,
    "wavespeed": WaveSpeedH3Backend,
}

_RATE_CARD_REGISTRY: dict[str, type[Backend]] = {
    "seedance_2": Seedance2Backend,
    "seedance_2_5": Seedance25Backend,
}


def backend_names() -> tuple[str, ...]:
    """Registered backend names, sorted, default first."""
    static = sorted(n for n in _REGISTRY if n != DEFAULT_BACKEND)
    ready = sorted(n for n in _RATE_CARD_REGISTRY if rate_card_ready(n))
    seen = set(static)
    extra = [n for n in ready if n not in seen]
    return (DEFAULT_BACKEND, *static, *extra)


def get_backend(name: str | None = None) -> Backend:
    """Construct a backend by name. None means the default (local_h3)."""
    key = (name or DEFAULT_BACKEND).strip()
    cls = _REGISTRY.get(key)
    if cls is not None:
        backend = cls()
        backend.validate_capabilities()
        return backend

    cls = _RATE_CARD_REGISTRY.get(key)
    if cls is not None:
        if not rate_card_ready(key):
            raise BackendError(rate_card_refusal(name))
        backend = cls()
        backend.validate_capabilities()
        return backend

    raise BackendError(
        f"Unknown backend '{name}'. Registered backends: "
        f"{', '.join(backend_names())}"
    )


__all__ = [
    "Backend",
    "BackendError",
    "DEFAULT_BACKEND",
    "LocalH3Backend",
    "REQUIRED_CAPABILITY_KEYS",
    "Seedance2Backend",
    "Seedance25Backend",
    "WaveSpeedH3Backend",
    "backend_names",
    "get_backend",
    "rate_card_ready",
    "rate_card_refusal",
]
