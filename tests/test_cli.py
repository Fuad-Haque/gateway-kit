import json

from gateway_kit.cli import main

from .conftest import DATA


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_route_command(capsys):
    code, out, _ = run(capsys, "route", "--config", str(DATA / "routing.json"))
    assert code == 0
    assert "$11,152.80" in out and "96.15%" in out


def test_cache_command(capsys):
    code, out, _ = run(capsys, "cache", "--config", str(DATA / "cache.json"))
    assert code == 0 and "Chosen: 0.98" in out and "$1,788.00" in out


def test_tpm_command(capsys):
    code, out, _ = run(capsys, "tpm", "--config", str(DATA / "tpm.json"))
    assert code == 0 and "1,000,000" in out and "incident" in out


def test_tpm_capacity_override(capsys):
    code, out, _ = run(capsys, "tpm", "--config", str(DATA / "tpm.json"), "--capacity", "750000")
    assert code == 0 and "scaled down" in out


def test_cost_command(capsys):
    code, out, _ = run(capsys, "cost", "--config", str(DATA / "usage.json"))
    assert code == 0 and "0.0852" in out and "91.9%" in out


def test_json_output_is_valid(capsys):
    code, out, _ = run(capsys, "route", "--config", str(DATA / "routing.json"), "--json")
    assert code == 0 and json.loads(out)["policy"]["summarize"] == "A"


def test_missing_file_exit_code_2(capsys, tmp_path):
    code, _, err = run(capsys, "cost", "--config", str(tmp_path / "nope.json"))
    assert code == 2 and "not found" in err


def test_bad_json_exit_code_2(capsys, tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not json")
    code, _, err = run(capsys, "route", "--config", str(f))
    assert code == 2 and "invalid JSON" in err


def test_infeasible_exit_code_3(capsys, tmp_path):
    cfg = json.loads((DATA / "routing.json").read_text())
    cfg["constraints"]["min_blended_pass"] = 99.9
    f = tmp_path / "r.json"
    f.write_text(json.dumps(cfg))
    code, _, err = run(capsys, "route", "--config", str(f))
    assert code == 3 and "infeasible" in err
