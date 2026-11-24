"""Load and validate JSON config files into domain objects.

JSON floats are parsed straight to Decimal so 0.0095 stays exactly 0.0095.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from .cache import CacheCosts, CacheOption
from .errors import ValidationError
from .money import to_decimal
from .ratelimit import Tenant
from .routing import Constraints, ModelPrice, RequestClass


def load_json(path: str | Path) -> Any:
    p = Path(path)
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f, parse_float=Decimal)
    except FileNotFoundError:
        raise ValidationError(f"config file not found: {p}") from None
    except json.JSONDecodeError as e:
        raise ValidationError(f"{p}: invalid JSON ({e})") from None


def _get(d: Mapping[str, Any], key: str, ctx: str) -> Any:
    if not isinstance(d, Mapping) or key not in d:
        raise ValidationError(f"{ctx}: missing required key {key!r}")
    return d[key]


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field}: must be an integer, got {value!r}")
    return value


def parse_routing(cfg: Mapping[str, Any]):
    models = {
        name: ModelPrice(
            to_decimal(_get(p, "input_per_m", f"models.{name}"), f"models.{name}.input_per_m"),
            to_decimal(_get(p, "output_per_m", f"models.{name}"), f"models.{name}.output_per_m"),
        )
        for name, p in _get(cfg, "models", "config").items()
    }
    con = _get(cfg, "constraints", "config")
    constraints = Constraints(
        to_decimal(_get(con, "min_blended_pass", "constraints"), "min_blended_pass"),
        to_decimal(_get(con, "min_class_pass", "constraints"), "min_class_pass"),
    )
    classes = []
    for i, c in enumerate(_get(cfg, "classes", "config")):
        ctx = f"classes[{i}]"
        classes.append(
            RequestClass(
                name=str(_get(c, "name", ctx)),
                share=to_decimal(_get(c, "share", ctx), f"{ctx}.share"),
                avg_in_tokens=_int(_get(c, "avg_in_tokens", ctx), f"{ctx}.avg_in_tokens"),
                avg_out_tokens=_int(_get(c, "avg_out_tokens", ctx), f"{ctx}.avg_out_tokens"),
                pass_rate={m: to_decimal(v, f"{ctx}.pass_rate.{m}") for m, v in _get(c, "pass_rate", ctx).items()},
            )
        )
    return (
        classes,
        models,
        _int(_get(cfg, "daily_requests", "config"), "daily_requests"),
        constraints,
        str(_get(cfg, "baseline_model", "config")),
    )


def parse_cache(cfg: Mapping[str, Any]):
    options = [
        CacheOption(
            label=str(_get(o, "threshold", f"options[{i}]")),
            hit_rate=to_decimal(_get(o, "hit_rate", f"options[{i}]"), "hit_rate"),
            wrong_rate_among_hits=to_decimal(
                _get(o, "wrong_rate_among_hits", f"options[{i}]"), "wrong_rate_among_hits"
            ),
        )
        for i, o in enumerate(_get(cfg, "options", "config"))
    ]
    costs = CacheCosts(
        to_decimal(_get(cfg, "uncached_request_cost", "config"), "uncached_request_cost"),
        to_decimal(_get(cfg, "lookup_cost", "config"), "lookup_cost"),
        to_decimal(_get(cfg, "wrong_answer_cost", "config"), "wrong_answer_cost"),
    )
    return (
        options,
        _int(_get(cfg, "daily_requests", "config"), "daily_requests"),
        costs,
        to_decimal(_get(cfg, "max_wrong_rate", "config"), "max_wrong_rate"),
    )


def parse_tpm(cfg: Mapping[str, Any]):
    tenants = []
    for i, t in enumerate(_get(cfg, "tenants", "config")):
        ctx = f"tenants[{i}]"
        w = _get(t, "weight", ctx)
        tenants.append(
            Tenant(
                name=str(_get(t, "name", ctx)),
                guaranteed=_int(_get(t, "guaranteed", ctx), f"{ctx}.guaranteed"),
                weight=Fraction(str(w)) if not isinstance(w, bool) else w,
                demand=_int(_get(t, "demand", ctx), f"{ctx}.demand"),
            )
        )
    scenarios = {str(k): _int(v, f"scenarios.{k}") for k, v in _get(cfg, "scenarios", "config").items()}
    return tenants, scenarios
