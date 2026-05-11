"""Projection-service helpers for future Phase 4A persistence stories.

The full DB orchestration is implemented in Epic 2. This module already
consumes the engine version constant so every future persisted projection has a
single source of truth for the stamp.
"""
from __future__ import annotations

from backend.twin.engine import ENGINE_VERSION


DEFAULT_ENGINE_VERSION = ENGINE_VERSION


def engine_version_for_projection() -> str:
    """Return the engine version to stamp on ``twin_projections`` rows."""
    return DEFAULT_ENGINE_VERSION
