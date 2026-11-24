import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gateway_kit import config
from gateway_kit.errors import ValidationError
from gateway_kit.ratelimit import Tenant, allocate_tpm

from .conftest import DATA


@pytest.fixture
def tenants():
    return config.parse_tpm(config.load_json(DATA / "tpm.json"))[0]


def as_dict(result):
    return {t.name: (t.allocated, t.rejected) for t in result.tenants}


def test_scenario_1_capacity_2m(tenants):
    r = allocate_tpm(tenants, 2_000_000)
    assert as_dict(r) == {
        "alpha": (1_000_000, 100_000),
        "bravo": (400_000, 0),
        "charlie": (400_000, 300_000),
        "delta": (50_000, 550_000),
        "echo": (150_000, 750_000),
    }
    assert r.total_allocated == 2_000_000 and r.total_rejected == 1_700_000
    assert not r.scaled_down


def test_scenario_2_capacity_1_5m(tenants):
    r = allocate_tpm(tenants, 1_500_000)  # guarantees sum == capacity exactly
    assert as_dict(r) == {
        "alpha": (800_000, 300_000),
        "bravo": (400_000, 0),
        "charlie": (300_000, 400_000),
        "delta": (0, 600_000),
        "echo": (0, 900_000),
    }
    assert r.total_allocated == 1_500_000 and not r.scaled_down


def test_proportional_scale_down_when_guarantees_exceed_capacity(tenants):
    r = allocate_tpm(tenants, 750_000)  # step-1 sum 1.5M -> scale by 0.5
    assert as_dict(r)["alpha"][0] == 400_000
    assert as_dict(r)["bravo"][0] == 200_000
    assert as_dict(r)["charlie"][0] == 150_000
    assert r.scaled_down and r.total_allocated == 750_000


def test_redistribution_when_a_tenant_hits_its_cap():
    ts = [Tenant("a", 0, 1, 10), Tenant("b", 0, 1, 1000)]
    r = allocate_tpm(ts, 100)  # a capped at 10, b gets the other 90
    assert as_dict(r) == {"a": (10, 0), "b": (90, 910)}


def test_capacity_exceeds_total_demand():
    ts = [Tenant("a", 5, 1, 10), Tenant("b", 0, 2, 20)]
    r = allocate_tpm(ts, 1000)
    assert r.total_rejected == 0 and r.total_allocated == 30


def test_zero_capacity():
    ts = [Tenant("a", 5, 1, 10)]
    assert allocate_tpm(ts, 0).total_allocated == 0


def test_zero_demand_tenant_gets_nothing():
    ts = [Tenant("a", 100, 1, 0), Tenant("b", 0, 1, 50)]
    assert as_dict(allocate_tpm(ts, 40)) == {"a": (0, 0), "b": (40, 10)}


def test_integer_rounding_never_exceeds_capacity():
    ts = [Tenant("a", 0, 1, 100), Tenant("b", 0, 1, 100), Tenant("c", 0, 1, 100)]
    r = allocate_tpm(ts, 100)  # 33.33 each -> largest remainder
    assert sorted(t.allocated for t in r.tenants) == [33, 33, 34]
    assert r.total_allocated == 100


def test_weights_split_proportionally():
    ts = [Tenant("a", 0, 3, 1000), Tenant("b", 0, 1, 1000)]
    assert as_dict(allocate_tpm(ts, 400)) == {"a": (300, 700), "b": (100, 900)}


@pytest.mark.parametrize(
    "bad",
    [
        [Tenant("a", 0, 0, 10)],  # zero weight
        [Tenant("a", -1, 1, 10)],  # negative guarantee
        [Tenant("a", 0, 1, -10)],  # negative demand
        [Tenant("a", 0, 1, 10), Tenant("a", 0, 1, 10)],  # duplicate names
        [],  # no tenants
    ],
)
def test_invalid_tenants(bad):
    with pytest.raises(ValidationError):
        allocate_tpm(bad, 100)


def test_invalid_capacity():
    with pytest.raises(ValidationError):
        allocate_tpm([Tenant("a", 0, 1, 1)], -1)


@settings(deadline=None, max_examples=300)
@given(
    rows=st.lists(
        st.tuples(st.integers(0, 10**6), st.integers(1, 10), st.integers(0, 10**6)),
        min_size=1,
        max_size=8,
    ),
    capacity=st.integers(0, 5 * 10**6),
)
def test_invariants_hold_for_any_input(rows, capacity):
    ts = [Tenant(f"t{i}", g, w, d) for i, (g, w, d) in enumerate(rows)]
    r = allocate_tpm(ts, capacity)
    total_demand = sum(d for _, _, d in rows)
    base = sum(min(d, g) for g, _, d in rows)
    assert r.total_allocated <= capacity
    assert r.total_allocated == min(capacity, total_demand)  # work-conserving
    for t in r.tenants:
        assert 0 <= t.allocated <= t.demand
    if base <= capacity:  # guarantees are honored whenever they fit
        for t, (g, _, d) in zip(r.tenants, rows, strict=True):
            assert t.allocated >= min(d, g)
