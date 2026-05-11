"""Financial Twin Monte Carlo engine.

Versioning rule:
- Patch bumps are for internal refactors that keep outputs statistically equivalent.
- Minor bumps are required when tuning distributions, correlations, or default
  simulation parameters.
- Major bumps are required when changing the model family or output schema.

Every persisted projection must stamp this version so future accuracy tracking
can separate old predictions from newer engine behavior.
"""

ENGINE_VERSION = "4a.1.0"

__all__ = ["ENGINE_VERSION"]
