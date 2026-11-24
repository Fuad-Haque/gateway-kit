"""Command-line interface: gateway-kit {route,cache,tpm,cost}."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict

from . import billing, cache, config, ratelimit, routing
from .errors import InfeasibleError, ValidationError
from .money import fmt_usd, quantize

EXIT_OK, EXIT_INVALID, EXIT_INFEASIBLE = 0, 2, 3


def _dump(obj) -> None:
    print(json.dumps(asdict(obj), indent=2, default=str))


def _cmd_route(args) -> None:
    classes, models, n, constraints, baseline = config.parse_routing(config.load_json(args.config))
    r = routing.optimize_routing(classes, models, n, constraints, baseline)
    if args.json:
        return _dump(r)
    by_name = {c.name: c for c in classes}
    print(f"{'class':<20}{'model':<7}{'pass %':>8}{'daily cost':>16}")
    for name, model in r.policy.items():
        print(f"{name:<20}{model:<7}{by_name[name].pass_rate[model]:>8}{fmt_usd(r.class_costs[name]):>16}")
    print(f"\nBlended pass rate : {r.blended_pass}%")
    print(f"Cost before ({baseline}) : {fmt_usd(r.baseline_cost)}")
    print(f"Cost after        : {fmt_usd(r.daily_cost)}")
    print(f"Daily savings     : {fmt_usd(r.savings)}")
    print(f"(searched {r.searched} policies, {r.feasible_policies} feasible)")


def _cmd_cache(args) -> None:
    options, n, costs, max_wrong = config.parse_cache(config.load_json(args.config))
    d = cache.evaluate_options(options, n, costs, max_wrong)
    if args.json:
        return _dump(d)
    print(f"{'option':<10}{'hits':>10}{'wrong':>9}{'wrong %':>9}{'net savings':>15}  ok?")
    for r in d.results:
        print(
            f"{r.label:<10}{r.hits:>10,.0f}{r.wrong_answers:>9,.0f}"
            f"{quantize(r.wrong_rate_of_all * 100, 3):>9}{fmt_usd(r.net_savings):>15}"
            f"  {'yes' if r.feasible else 'NO'}"
        )
    c = d.chosen
    print(f"\nChosen: {c.label} | net savings {fmt_usd(c.net_savings)}/day | wrong answers/day {c.wrong_answers:,.0f}")


def _cmd_tpm(args) -> None:
    tenants, scenarios = config.parse_tpm(config.load_json(args.config))
    if args.capacity is not None:
        scenarios = {"custom": args.capacity}
    results = {name: ratelimit.allocate_tpm(tenants, cap) for name, cap in scenarios.items()}
    if args.json:
        print(json.dumps({k: asdict(v) for k, v in results.items()}, indent=2))
        return
    for name, r in results.items():
        note = " (guarantees scaled down)" if r.scaled_down else ""
        print(f"\nScenario {name}: capacity {r.capacity:,} TPM{note}")
        print(f"{'tenant':<10}{'demand':>12}{'allocated':>12}{'rejected 429':>14}")
        for t in r.tenants:
            print(f"{t.name:<10}{t.demand:>12,}{t.allocated:>12,}{t.rejected:>14,}")
        print(f"{'TOTAL':<10}{'':>12}{r.total_allocated:>12,}{r.total_rejected:>14,}")


def _cmd_cost(args) -> None:
    records = config.load_json(args.config)
    if not isinstance(records, list):
        raise ValidationError("usage file must contain a JSON list of records")
    s = billing.summarize(records)
    if args.json:
        return _dump(s)
    print(f"{'id':<6}{'correct':>10}{'legacy':>10}")
    for r in s.records:
        print(f"{r.id:<6}{quantize(r.correct, 4):>10}{quantize(r.legacy, 4):>10}")
    print(f"\nCorrect total : ${quantize(s.correct_total, 4)}")
    print(f"Legacy total  : ${quantize(s.legacy_total, 4)}")
    pct = "n/a" if s.overstatement_pct is None else f"{quantize(s.overstatement_pct, 1)}%"
    print(f"Overstatement : {pct}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gateway-kit", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, func, default_config: str, help_text: str) -> argparse.ArgumentParser:
        # Arguments are added per subcommand: a shared parent parser would share one
        # --config action object, and the last set_defaults() would win for all.
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--config", default=default_config, help="path to input JSON")
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.set_defaults(func=func)
        return sp

    add("route", _cmd_route, "data/routing.json", "optimal per-class model routing")
    add("cache", _cmd_cache, "data/cache.json", "semantic cache threshold")
    tpm = add("tpm", _cmd_tpm, "data/tpm.json", "per-tenant TPM allocation")
    tpm.add_argument("--capacity", type=int, help="override: run one custom capacity")
    add("cost", _cmd_cost, "data/usage.json", "audit usage records vs provider billing")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except ValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INVALID
    except InfeasibleError as e:
        print(f"infeasible: {e}", file=sys.stderr)
        return EXIT_INFEASIBLE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
