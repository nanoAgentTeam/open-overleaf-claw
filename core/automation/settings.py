"""Feature flags for automation memory rollout."""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


USE_UNIFIED_MEMORY_FOR_AUTOMATION = _env_bool("USE_UNIFIED_MEMORY_FOR_AUTOMATION", True)
MIRROR_LEGACY_MEMORY = _env_bool("MIRROR_LEGACY_MEMORY", False)
GC_PROTECT_JOB_STATE_REFS = _env_bool("GC_PROTECT_JOB_STATE_REFS", True)
