"""The command line, end to end."""

import json

from fleet_ops.cli import main
from fleet_ops.sbom import SBOM, Component


def test_demo_reports_the_rollbacks_and_the_halt(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "rolled back  : 2" in out
    assert "untouched    : 6" in out
    assert "halted" in out


def test_demo_can_write_a_machine_readable_report(tmp_path):
    out = tmp_path / "rollout.json"
    assert main(["demo", "--out", str(out)]) == 0
    payload = json.loads(out.read_text())
    assert payload["schema"] == "fleet-ops/rollout-report/v1"
    assert payload["rolled_back"] == 2
    assert payload["by_code"]["digest-mismatch"] == 1


def _write_sbom(path, version, components):
    path.write_text(json.dumps(SBOM.of("agent", version, components).as_dict()))


def test_sbom_diff_names_what_appeared(tmp_path, capsys):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_sbom(a, "1.0", [Component("zlib", "1.3.1")])
    _write_sbom(b, "2.0", [Component("zlib", "1.3.1"), Component("libssh", "0.10.6")])
    assert main(["sbom-diff", str(a), str(b)]) == 0
    assert "+ library/libssh 0.10.6" in capsys.readouterr().out


def test_sbom_diff_can_gate_a_pipeline(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write_sbom(a, "1.0", [Component("zlib", "1.3.1")])
    _write_sbom(b, "2.0", [Component("zlib", "1.3.2")])
    assert main(["sbom-diff", str(a), str(b), "--fail-on-change"]) == 1
    assert main(["sbom-diff", str(a), str(a), "--fail-on-change"]) == 0


def test_repro_exits_non_zero_when_the_builds_differ(tmp_path, capsys):
    for name, stamp in (("a", "one"), ("b", "two")):
        d = tmp_path / name
        (d / "bin").mkdir(parents=True)
        (d / "bin" / "agent").write_text("ELF")
        (d / "stamp.txt").write_text(stamp)
    assert main(["repro", str(tmp_path / "a"), str(tmp_path / "b")]) == 1
    assert "~ stamp.txt" in capsys.readouterr().out


def test_repro_exits_zero_on_identical_trees(tmp_path):
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        (d / "agent").write_text("ELF")
    assert main(["repro", str(tmp_path / "a"), str(tmp_path / "b")]) == 0
