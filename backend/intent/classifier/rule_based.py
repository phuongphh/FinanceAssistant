"""Rule-based intent classifier.

Loads regex patterns from ``content/intent_patterns.yaml`` once, then
evaluates each query against the full set and returns the highest-
confidence match. Designed to handle ~75% of Phase 3.5 traffic with
zero LLM calls and sub-200ms latency.

Normalization
-------------
Every query is lowercased AND diacritic-stripped before matching, so
patterns in the YAML are written in accent-free form. This gives the
matcher resilience to users who type without diacritics — common on
desktop and in fast Telegram exchanges — without doubling the pattern
count.

Parameter extraction
--------------------
After a pattern hits, we run two passes:
  1. Named regex groups from the pattern itself (e.g. ``?P<ticker>``).
  2. Configured ``parameter_extractors`` — either a dedicated extractor
     (time_range, category, ticker, amount, goal_name) or an inline
     keyword→value table.

Time-range values are stored as the stable label ("this_month") so they
match the test fixtures and downstream analytics; handlers that need
date arithmetic re-derive the range via ``time_range.extract``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from backend.intent.extractors import amount, category, goal_name, ticker, time_range
from backend.intent.extractors._normalize import strip_diacritics
from backend.intent.extractors.ticker import ALL_TICKERS
from backend.intent.intents import (
    CLASSIFIER_RULE,
    IntentResult,
    IntentType,
)

logger = logging.getLogger(__name__)

DEFAULT_PATTERNS_PATH = (
    Path(__file__).resolve().parents[3] / "content" / "intent_patterns.yaml"
)


@dataclass(frozen=True)
class _CompiledPattern:
    """One compiled regex with its confidence + parent intent."""

    intent: IntentType
    regex: re.Pattern[str]
    confidence: float
    parameter_extractors: dict


class RuleBasedClassifier:
    """Match user text against the YAML pattern set."""

    def __init__(self, patterns_path: str | Path | None = None) -> None:
        self._patterns_path = Path(patterns_path or DEFAULT_PATTERNS_PATH)
        self._patterns: list[_CompiledPattern] = self._load(self._patterns_path)

    # -------------------- public API --------------------

    def classify(self, text: str) -> IntentResult | None:
        """Return the highest-confidence match or None."""
        if not text or not text.strip():
            return None

        original = text.strip()
        # Slash commands stay literal — diacritic stripping would mangle
        # them and case-folding is fine because Telegram normalizes anyway.
        normalized = strip_diacritics(original.lower())

        best: tuple[_CompiledPattern, re.Match[str], dict] | None = None
        for compiled in self._patterns:
            m = compiled.regex.search(normalized)
            if not m:
                continue
            params = self._extract_parameters(
                normalized, original, m, compiled.parameter_extractors
            )
            # Validate captured ticker against the whitelist — otherwise
            # an off-target word ("tiet" inside "thời tiết") slips through
            # the query_market regex and beats the genuine out_of_scope
            # match on confidence. The check lives here (not in YAML) so
            # every intent with a ticker capture benefits automatically.
            if compiled.intent == IntentType.QUERY_MARKET:
                t = params.get("ticker")
                if not t or str(t).upper() not in ALL_TICKERS:
                    continue
                params["ticker"] = str(t).upper()
            if best is None or compiled.confidence > best[0].confidence:
                best = (compiled, m, params)

        if best is None:
            return None

        compiled, match, params = best
        return IntentResult(
            intent=compiled.intent,
            confidence=compiled.confidence,
            parameters=params,
            raw_text=original,
            classifier_used=CLASSIFIER_RULE,
        )

    # -------------------- internals --------------------

    def _load(self, path: Path) -> list[_CompiledPattern]:
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        compiled: list[_CompiledPattern] = []
        for intent_name, intent_block in raw.items():
            try:
                intent = IntentType(intent_name)
            except ValueError:
                logger.warning(
                    "Unknown intent %r in patterns file — skipping", intent_name
                )
                continue
            extractor_cfg = intent_block.get("parameter_extractors") or {}
            for entry in intent_block.get("patterns") or []:
                regex_str = entry["pattern"]
                conf = float(entry["confidence"])
                try:
                    regex = re.compile(regex_str, re.IGNORECASE)
                except re.error:
                    logger.exception(
                        "Bad regex for intent %s: %r", intent_name, regex_str
                    )
                    continue
                compiled.append(
                    _CompiledPattern(
                        intent=intent,
                        regex=regex,
                        confidence=conf,
                        parameter_extractors=extractor_cfg,
                    )
                )

        # Sort descending by confidence so iteration order also reflects
        # priority — handy when debugging the matcher.
        compiled.sort(key=lambda c: -c.confidence)
        return compiled

    def _extract_parameters(
        self,
        normalized: str,
        original: str,
        match: re.Match[str],
        extractor_cfg: dict,
    ) -> dict:
        params: dict = {}

        # 1. Named regex groups from the matched pattern.
        for key, value in match.groupdict().items():
            if value is not None:
                params[key] = value.strip()

        # 2. Configured extractors / inline keyword tables.
        for param_name, cfg in extractor_cfg.items():
            if "use_extractor" in cfg:
                value = self._run_extractor(
                    cfg["use_extractor"], normalized, original
                )
                if value is not None:
                    params[param_name] = value
            elif "patterns" in cfg:
                for entry in cfg["patterns"]:
                    if re.search(entry["match"], normalized, re.IGNORECASE):
                        params[param_name] = entry["value"]
                        break
        return params

    def _run_extractor(
        self, name: str, normalized: str, original: str
    ) -> object | None:
        if name == "time_range":
            tr = time_range.extract(original)
            return tr.label if tr else None
        if name == "category":
            return category.extract(original)
        if name == "ticker":
            return ticker.extract(original)
        if name == "amount":
            return amount.extract(original)
        if name == "goal_name":
            return goal_name.extract(original)
        logger.warning("Unknown extractor reference: %s", name)
        return None


__all__ = ["RuleBasedClassifier", "DEFAULT_PATTERNS_PATH"]
