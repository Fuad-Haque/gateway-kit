import copy
from decimal import Decimal

import pytest

from gateway_kit import config
from gateway_kit.errors import InfeasibleError, ValidationError
from gateway_kit.money import quantize
from gateway_kit.routing import optimize_routing

from .conftest import DATA


@pytest.fixture
def cfg():
    return config.load_json(DATA / "routing.json")


def solve(cfg_dict):
    classes, models, n, con, base = config.parse_routing(cfg_dict)
    return optimize_routing(classes, models, n, con, base)


def test_supplied_example(cfg):
    r = solve(cfg)
    assert r.policy == {
        "faq_lookup": "B",
        "summarize": "A",
        "extract_json": "A",
        "reasoning_support": "B",
    }
    assert r.blended_pass == Decimal("96.15")
    assert quantize(r.baseline_cost) == Decimal("21204.00")
    assert quantize(r.daily_cost) == Decimal("10051.20")
    assert quantize(r.savings) == Decimal("11152.80")
    assert r.searched == 16 and r.feasible_policies == 6


def test_class_floor_forces_large_model(cfg):
    assert solve(cfg).policy["reasoning_support"] == "B"  # A scores 71 < 90


def test_loose_constraints_send_everything_to_cheap_model(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["constraints"] = {"min_blended_pass": 0, "min_class_pass": 0}
    assert set(solve(cfg).policy.values()) == {"A"}


def test_blended_boundary_is_inclusive(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["constraints"]["min_blended_pass"] = Decimal("96.15")
    assert solve(cfg).blended_pass == Decimal("96.15")
    cfg["constraints"]["min_blended_pass"] = Decimal("96.16")
    assert solve(cfg).policy != {  # needs a different (costlier) policy
        "faq_lookup": "B",
        "summarize": "A",
        "extract_json": "A",
        "reasoning_support": "B",
    }


def test_infeasible_raises(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["constraints"]["min_blended_pass"] = 99.5
    with pytest.raises(InfeasibleError):
        solve(cfg)


def test_shares_must_sum_to_one(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["classes"][0]["share"] = Decimal("0.5")
    with pytest.raises(ValidationError):
        solve(cfg)


def test_missing_pass_rate_rejected(cfg):
    cfg = copy.deepcopy(cfg)
    del cfg["classes"][0]["pass_rate"]["A"]
    with pytest.raises(ValidationError):
        solve(cfg)


def test_unknown_baseline_rejected(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["baseline_model"] = "Z"
    with pytest.raises(ValidationError):
        solve(cfg)


def test_three_models(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["models"]["C"] = {"input_per_m": 1.0, "output_per_m": 5.0}
    for c in cfg["classes"]:
        c["pass_rate"]["C"] = c["pass_rate"]["B"]
    r = solve(cfg)
    assert r.searched == 81
    assert r.savings >= Decimal("11152.80")  # more options never hurt
