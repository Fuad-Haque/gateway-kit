from decimal import Decimal as D

import pytest

from gateway_kit import config
from gateway_kit.cache import NO_CACHE, CacheCosts, CacheOption, evaluate_options
from gateway_kit.errors import ValidationError
from gateway_kit.money import quantize

from .conftest import DATA


def run(cfg=None):
    cfg = cfg or config.load_json(DATA / "cache.json")
    return evaluate_options(*config.parse_cache(cfg))


def test_supplied_example():
    d = run()
    by = {r.label: r for r in d.results}
    assert d.chosen.label == "0.98"
    assert quantize(d.chosen.net_savings) == D("1788.00")
    assert d.chosen.wrong_answers == 432
    assert {k: v.feasible for k, v in by.items()} == {
        NO_CACHE: True,
        "0.98": True,
        "0.95": False,
        "0.92": False,
        "0.90": False,
    }
    assert quantize(by["0.95"].net_savings) == D("1440.00")
    assert quantize(by["0.92"].net_savings) == D("-4836.00")
    assert quantize(by["0.90"].net_savings) == D("-16512.00")


def test_all_options_infeasible_means_no_cache():
    cfg = config.load_json(DATA / "cache.json")
    cfg["max_wrong_rate"] = D("0.00001")
    assert run(cfg).chosen.label == NO_CACHE


def test_constraint_boundary_is_inclusive():
    costs = CacheCosts(D("0.01"), D("0"), D("0"))
    opt = CacheOption("x", D("0.5"), D("0.001"))  # wrong = 0.05% of all requests exactly
    d = evaluate_options([opt], 1_000_000, costs, D("0.0005"))
    assert d.chosen.label == "x"


def test_negative_net_option_never_chosen_even_if_feasible():
    costs = CacheCosts(D("0.001"), D("0.01"), D("0"))  # lookup dearer than a model call
    d = evaluate_options([CacheOption("x", D("0.1"), D("0"))], 1000, costs, D("1"))
    assert d.chosen.label == NO_CACHE


def test_zero_traffic():
    d = evaluate_options([CacheOption("x", D("0.5"), D("0.1"))], 0, CacheCosts(D(1), D(1), D(1)), D("0.1"))
    assert d.chosen.label == NO_CACHE


@pytest.mark.parametrize("hit,wrong", [(D("1.1"), D("0")), (D("-0.1"), D("0")), (D("0.5"), D("2"))])
def test_invalid_rates(hit, wrong):
    with pytest.raises(ValidationError):
        evaluate_options([CacheOption("x", hit, wrong)], 100, CacheCosts(D(1), D(0), D(0)), D("0.1"))


def test_duplicate_or_reserved_labels():
    c = CacheCosts(D(1), D(0), D(0))
    with pytest.raises(ValidationError):
        evaluate_options([CacheOption("x", D(0), D(0)), CacheOption("x", D(0), D(0))], 1, c, D("0.1"))
    with pytest.raises(ValidationError):
        evaluate_options([CacheOption(NO_CACHE, D(0), D(0))], 1, c, D("0.1"))
