from decimal import Decimal

import pytest

from gateway_kit.billing import Pricing, cost, legacy_cost, summarize
from gateway_kit.errors import ValidationError
from gateway_kit.money import quantize

R1 = {"id": "r1", "prompt_tokens": 12000, "cached_tokens": 10000, "completion_tokens": 400}
R2 = {"id": "r2", "prompt_tokens": 8000, "cached_tokens": 0, "completion_tokens": 1200}
R3 = {"id": "r3", "prompt_tokens": 15000, "cached_tokens": 14000, "completion_tokens": 300}
R4 = {"id": "r4", "prompt_tokens": 6000, "cached_tokens": 5000, "completion_tokens": 800}


@pytest.mark.parametrize(
    ("record", "expected"),
    [(R1, "0.0150"), (R2, "0.0420"), (R3, "0.0117"), (R4, "0.0165")],
)
def test_supplied_examples(record, expected):
    assert quantize(cost(record), 4) == Decimal(expected)


def test_costs_are_exact_decimals():
    assert cost(R1) == Decimal("0.015")  # no float noise


def test_totals_and_overstatement():
    s = summarize([R1, R2, R3, R4])
    assert quantize(s.correct_total, 4) == Decimal("0.0852")
    assert quantize(s.legacy_total, 4) == Decimal("0.1635")
    assert quantize(s.overstatement_pct, 1) == Decimal("91.9")


def test_no_cache_hits_matches_legacy():
    assert cost(R2) == legacy_cost(R2)


def test_missing_cached_field_treated_as_zero():
    rec = {"prompt_tokens": 1000, "completion_tokens": 100}
    assert cost(rec) == Decimal("0.0045")


def test_null_cached_field_treated_as_zero():
    assert cost({"prompt_tokens": 1000, "cached_tokens": None, "completion_tokens": 0}) == Decimal("0.003")


def test_all_tokens_cached():
    assert cost({"prompt_tokens": 1000, "cached_tokens": 1000, "completion_tokens": 0}) == Decimal("0.0003")


def test_zero_usage_costs_zero():
    assert cost({"prompt_tokens": 0, "completion_tokens": 0}) == 0


def test_custom_pricing():
    p = Pricing(Decimal("1"), Decimal("0.1"), Decimal("2"))
    assert cost({"prompt_tokens": 1_000_000, "cached_tokens": 0, "completion_tokens": 0}, p) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"completion_tokens": 1},  # missing prompt
        {"prompt_tokens": 10},  # missing completion
        {"prompt_tokens": 10, "cached_tokens": 11, "completion_tokens": 0},  # cached > prompt
        {"prompt_tokens": -1, "completion_tokens": 0},  # negative
        {"prompt_tokens": 1.5, "completion_tokens": 0},  # float
        {"prompt_tokens": True, "completion_tokens": 0},  # bool
        {"prompt_tokens": "10", "completion_tokens": 0},  # string
    ],
)
def test_invalid_usage_rejected(bad):
    with pytest.raises(ValidationError):
        cost(bad)


def test_non_mapping_rejected():
    with pytest.raises(ValidationError):
        cost([1, 2, 3])


def test_summary_of_empty_list():
    s = summarize([])
    assert s.correct_total == 0 and s.overstatement_pct is None
