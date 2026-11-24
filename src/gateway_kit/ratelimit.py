"""Per-tenant TPM allocation.

1. Each tenant gets min(demand, guaranteed).
2. If that sum exceeds capacity, scale everyone proportionally and stop.
3. Otherwise give the remainder out by weighted max-min fairness (water-filling),
   capping each tenant at its unmet demand and redistributing leftovers.

Math runs in exact Fractions; the final result is converted to integers with
largest-remainder rounding so totals never exceed capacity.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from .errors import ValidationError


@dataclass(frozen=True)
class Tenant:
    name: str
    guaranteed: int
    weight: int | Fraction
    demand: int


@dataclass(frozen=True)
class TenantAllocation:
    name: str
    demand: int
    allocated: int
    rejected: int


@dataclass(frozen=True)
class AllocationResult:
    capacity: int
    tenants: list[TenantAllocation]
    total_allocated: int
    total_rejected: int
    scaled_down: bool


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate(tenants: Sequence[Tenant], capacity: int) -> None:
    if not _is_int(capacity) or capacity < 0:
        raise ValidationError("capacity must be a non-negative integer")
    if not tenants:
        raise ValidationError("at least one tenant is required")
    names = [t.name for t in tenants]
    if len(set(names)) != len(names):
        raise ValidationError("tenant names must be unique")
    for t in tenants:
        if not _is_int(t.guaranteed) or t.guaranteed < 0:
            raise ValidationError(f"{t.name}: guaranteed must be a non-negative integer")
        if not _is_int(t.demand) or t.demand < 0:
            raise ValidationError(f"{t.name}: demand must be a non-negative integer")
        if Fraction(t.weight) <= 0:
            raise ValidationError(f"{t.name}: weight must be > 0")


def _water_fill(tenants: Sequence[Tenant], alloc: dict[str, Fraction], remaining: Fraction) -> None:
    weight = {t.name: Fraction(t.weight) for t in tenants}
    unmet = {t.name: Fraction(t.demand) - alloc[t.name] for t in tenants}
    active = {n for n, u in unmet.items() if u > 0}
    while remaining > 0 and active:
        wsum = sum((weight[n] for n in active), Fraction(0))
        share = {n: remaining * weight[n] / wsum for n in active}
        capped = {n for n in active if share[n] >= unmet[n]}
        if not capped:
            for n in active:
                alloc[n] += share[n]
            return
        for n in sorted(capped):
            alloc[n] += unmet[n]
            remaining -= unmet[n]
        active -= capped


def _to_integers(exact: dict[str, Fraction]) -> dict[str, int]:
    floors = {n: math.floor(v) for n, v in exact.items()}
    leftover = math.floor(sum(exact.values(), Fraction(0))) - sum(floors.values())
    by_remainder = sorted(exact, key=lambda n: (-(exact[n] - floors[n]), n))
    for n in by_remainder[:leftover]:
        floors[n] += 1  # exact[n] <= integer demand, so ceil never exceeds demand
    return floors


def allocate_tpm(tenants: Sequence[Tenant], capacity: int) -> AllocationResult:
    _validate(tenants, capacity)
    cap = Fraction(capacity)
    exact = {t.name: Fraction(min(t.demand, t.guaranteed)) for t in tenants}
    total = sum(exact.values(), Fraction(0))
    scaled = total > cap
    if scaled:
        exact = {n: a * cap / total for n, a in exact.items()}
    else:
        _water_fill(tenants, exact, cap - total)

    ints = _to_integers(exact)
    rows = [TenantAllocation(t.name, t.demand, ints[t.name], t.demand - ints[t.name]) for t in tenants]
    return AllocationResult(
        capacity=capacity,
        tenants=rows,
        total_allocated=sum(r.allocated for r in rows),
        total_rejected=sum(r.rejected for r in rows),
        scaled_down=scaled,
    )
