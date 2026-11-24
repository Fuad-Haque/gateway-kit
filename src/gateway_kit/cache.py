"""Semantic-cache threshold selection by expected net savings.

net = hits * uncached_cost - requests * lookup_cost - wrong * wrong_cost
Only options with wrong/requests <= max_wrong_rate are eligible.
'no cache' (net 0, no lookup cost) is always eligible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .errors import ValidationError

NO_CACHE = "no cache"


@dataclass(frozen=True)
class CacheOption:
    label: str
    hit_rate: Decimal  # 0..1
    wrong_rate_among_hits: Decimal  # 0..1


@dataclass(frozen=True)
class CacheCosts:
    uncached_request_cost: Decimal
    lookup_cost: Decimal
    wrong_answer_cost: Decimal


@dataclass(frozen=True)
class OptionResult:
    label: str
    hits: Decimal
    wrong_answers: Decimal
    wrong_rate_of_all: Decimal
    model_cost_avoided: Decimal
    lookup_cost_total: Decimal
    wrong_answer_cost_total: Decimal
    net_savings: Decimal
    feasible: bool


@dataclass(frozen=True)
class CacheDecision:
    chosen: OptionResult
    results: list[OptionResult]


def _check_rate(value: Decimal, field: str) -> None:
    if not (0 <= value <= 1):
        raise ValidationError(f"{field} must be within 0..1")


def evaluate_options(
    options: Sequence[CacheOption],
    daily_requests: int,
    costs: CacheCosts,
    max_wrong_rate: Decimal,
) -> CacheDecision:
    if isinstance(daily_requests, bool) or not isinstance(daily_requests, int) or daily_requests < 0:
        raise ValidationError("daily_requests must be a non-negative integer")
    _check_rate(max_wrong_rate, "max_wrong_rate")
    for name in ("uncached_request_cost", "lookup_cost", "wrong_answer_cost"):
        if getattr(costs, name) < 0:
            raise ValidationError(f"{name} must be >= 0")
    labels = [o.label for o in options]
    if len(set(labels)) != len(labels) or NO_CACHE in labels:
        raise ValidationError("option labels must be unique and not 'no cache'")

    n = Decimal(daily_requests)
    results = [
        OptionResult(NO_CACHE, Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), True)
    ]
    for o in options:
        _check_rate(o.hit_rate, f"{o.label}.hit_rate")
        _check_rate(o.wrong_rate_among_hits, f"{o.label}.wrong_rate_among_hits")
        hits = n * o.hit_rate
        wrong = hits * o.wrong_rate_among_hits
        avoided = hits * costs.uncached_request_cost
        lookup = n * costs.lookup_cost
        wrong_cost = wrong * costs.wrong_answer_cost
        results.append(
            OptionResult(
                label=o.label,
                hits=hits,
                wrong_answers=wrong,
                wrong_rate_of_all=(wrong / n) if n else Decimal(0),
                model_cost_avoided=avoided,
                lookup_cost_total=lookup,
                wrong_answer_cost_total=wrong_cost,
                net_savings=avoided - lookup - wrong_cost,
                feasible=wrong <= n * max_wrong_rate,
            )
        )

    chosen = results[0]  # strict '>' means ties keep the simpler option (no cache first)
    for r in results[1:]:
        if r.feasible and r.net_savings > chosen.net_savings:
            chosen = r
    return CacheDecision(chosen, results)
