"""Provider-accurate token billing.

Rule: `prompt_tokens` INCLUDES `cached_tokens`, so
    uncached = prompt_tokens - cached_tokens
and the three parts are priced separately.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .errors import ValidationError
from .money import PER_MILLION


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens."""

    uncached_input: Decimal = Decimal("3.00")
    cached_input: Decimal = Decimal("0.30")
    output: Decimal = Decimal("15.00")


DEFAULT_PRICING = Pricing()


def _tokens(usage: Mapping[str, Any], key: str, required: bool = True) -> int:
    value = usage.get(key)
    if value is None:
        if required:
            raise ValidationError(f"usage is missing required field {key!r}")
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{key} must be a non-negative integer, got {value!r}")
    return value


def cost(usage: Mapping[str, Any], pricing: Pricing = DEFAULT_PRICING) -> Decimal:
    """Exact USD cost of one usage record."""
    if not isinstance(usage, Mapping):
        raise ValidationError("usage must be a mapping")
    prompt = _tokens(usage, "prompt_tokens")
    completion = _tokens(usage, "completion_tokens")
    cached = _tokens(usage, "cached_tokens", required=False)
    if cached > prompt:
        raise ValidationError(f"cached_tokens ({cached}) exceeds prompt_tokens ({prompt})")
    uncached = prompt - cached
    total = uncached * pricing.uncached_input + cached * pricing.cached_input + completion * pricing.output
    return total / PER_MILLION


def legacy_cost(usage: Mapping[str, Any], pricing: Pricing = DEFAULT_PRICING) -> Decimal:
    """The buggy formula (all prompt tokens at full price). Kept for audits."""
    prompt = _tokens(usage, "prompt_tokens")
    completion = _tokens(usage, "completion_tokens")
    return (prompt * pricing.uncached_input + completion * pricing.output) / PER_MILLION


@dataclass(frozen=True)
class RecordCost:
    id: str
    correct: Decimal
    legacy: Decimal


@dataclass(frozen=True)
class BillingSummary:
    records: list[RecordCost]
    correct_total: Decimal
    legacy_total: Decimal
    overstatement_pct: Decimal | None  # None when correct_total == 0


def summarize(records: Sequence[Mapping[str, Any]], pricing: Pricing = DEFAULT_PRICING) -> BillingSummary:
    rows = [
        RecordCost(str(rec.get("id", f"#{i}")), cost(rec, pricing), legacy_cost(rec, pricing))
        for i, rec in enumerate(records)
    ]
    correct = sum((r.correct for r in rows), Decimal(0))
    legacy = sum((r.legacy for r in rows), Decimal(0))
    pct = (legacy - correct) / correct * 100 if correct > 0 else None
    return BillingSummary(rows, correct, legacy, pct)
