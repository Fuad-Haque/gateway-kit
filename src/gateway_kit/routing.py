"""Per-class static routing between models under quality constraints.

Algorithm: exhaustive search over all M**N class->model assignments, keeping
the feasible policy with the lowest cost. Exact for small N; for large N
switch to an ILP/DP solver (see README).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import product

from .errors import InfeasibleError, ValidationError
from .money import PER_MILLION

MAX_SEARCH_SPACE = 2_000_000


@dataclass(frozen=True)
class ModelPrice:
    input_per_m: Decimal
    output_per_m: Decimal


@dataclass(frozen=True)
class RequestClass:
    name: str
    share: Decimal  # fraction of traffic, 0..1
    avg_in_tokens: int
    avg_out_tokens: int
    pass_rate: Mapping[str, Decimal]  # percent per model, 0..100


@dataclass(frozen=True)
class Constraints:
    min_blended: Decimal = Decimal("96.0")
    min_class: Decimal = Decimal("90")


@dataclass(frozen=True)
class RoutingResult:
    policy: dict[str, str]
    blended_pass: Decimal
    daily_cost: Decimal
    baseline_cost: Decimal
    savings: Decimal
    class_costs: dict[str, Decimal]
    feasible_policies: int
    searched: int


def _validate(
    classes: Sequence[RequestClass],
    models: Mapping[str, ModelPrice],
    daily_requests: int,
    baseline_model: str,
) -> None:
    if not classes:
        raise ValidationError("at least one request class is required")
    if len(models) < 1:
        raise ValidationError("at least one model is required")
    if baseline_model not in models:
        raise ValidationError(f"baseline model {baseline_model!r} is not defined")
    if isinstance(daily_requests, bool) or not isinstance(daily_requests, int) or daily_requests < 0:
        raise ValidationError("daily_requests must be a non-negative integer")
    names = [c.name for c in classes]
    if len(set(names)) != len(names):
        raise ValidationError("class names must be unique")
    if sum((c.share for c in classes), Decimal(0)) != 1:
        raise ValidationError("class shares must sum to exactly 1")
    for c in classes:
        if c.share < 0:
            raise ValidationError(f"{c.name}: share must be >= 0")
        if c.avg_in_tokens < 0 or c.avg_out_tokens < 0:
            raise ValidationError(f"{c.name}: token counts must be >= 0")
        for m in models:
            if m not in c.pass_rate:
                raise ValidationError(f"{c.name}: missing pass_rate for model {m!r}")
            if not (0 <= c.pass_rate[m] <= 100):
                raise ValidationError(f"{c.name}/{m}: pass_rate must be within 0..100")
    if len(models) ** len(classes) > MAX_SEARCH_SPACE:
        raise ValidationError("search space too large for brute force; use an ILP solver")


def optimize_routing(
    classes: Sequence[RequestClass],
    models: Mapping[str, ModelPrice],
    daily_requests: int,
    constraints: Constraints = Constraints(),
    baseline_model: str = "B",
) -> RoutingResult:
    _validate(classes, models, daily_requests, baseline_model)
    model_names = list(models)

    def class_cost(c: RequestClass, m: str) -> Decimal:
        p = models[m]
        per_request = c.avg_in_tokens * p.input_per_m + c.avg_out_tokens * p.output_per_m
        return per_request / PER_MILLION * daily_requests * c.share

    cost = {c.name: {m: class_cost(c, m) for m in model_names} for c in classes}

    best_key = None
    best_combo: tuple[int, ...] = ()
    best_blended = Decimal(0)
    feasible = 0
    searched = 0
    for combo in product(range(len(model_names)), repeat=len(classes)):
        searched += 1
        picks = [model_names[i] for i in combo]
        if any(c.pass_rate[m] < constraints.min_class for c, m in zip(classes, picks, strict=True)):
            continue
        blended = sum((c.share * c.pass_rate[m] for c, m in zip(classes, picks, strict=True)), Decimal(0))
        if blended < constraints.min_blended:
            continue
        feasible += 1
        total = sum((cost[c.name][m] for c, m in zip(classes, picks, strict=True)), Decimal(0))
        key = (total, -blended, combo)  # cheapest, then higher quality, then deterministic
        if best_key is None or key < best_key:
            best_key, best_combo, best_blended = key, combo, blended

    if best_key is None:
        raise InfeasibleError("no routing policy satisfies the constraints")

    policy = {c.name: model_names[i] for c, i in zip(classes, best_combo, strict=True)}
    baseline = sum((cost[c.name][baseline_model] for c in classes), Decimal(0))
    total_cost = best_key[0]
    return RoutingResult(
        policy=policy,
        blended_pass=best_blended,
        daily_cost=total_cost,
        baseline_cost=baseline,
        savings=baseline - total_cost,
        class_costs={c.name: cost[c.name][policy[c.name]] for c in classes},
        feasible_policies=feasible,
        searched=searched,
    )
