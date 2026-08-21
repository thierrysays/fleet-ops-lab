"""Smoke: does the thing start at all.

Run after an install on a machine nobody has used before, before anything else
is believed. Under a second, no fleet, no network.
"""

from __future__ import annotations

import json
import subprocess
import sys


def test_the_package_imports():
    import fleet_ops

    assert fleet_ops.__version__


def test_the_public_surface_is_importable_from_the_top_level():
    from fleet_ops import Artefact, Manifest, Node, Rollout  # noqa: F401


def test_the_console_entry_point_answers(cli_env):
    result = subprocess.run(
        [sys.executable, "-m", "fleet_ops.cli", "--version"],
        capture_output=True, text=True, env=cli_env,
    )
    assert result.returncode == 0
    assert "fleet-ops-lab" in result.stdout


def test_the_demo_runs_and_reports_its_rollbacks(tmp_path, cli_env):
    result = subprocess.run(
        [sys.executable, "-m", "fleet_ops.cli", "demo"],
        capture_output=True, text=True, cwd=tmp_path, env=cli_env,
    )
    assert result.returncode == 0, result.stderr
    assert "rolled back  : 2" in result.stdout


def test_the_demo_writes_a_report_that_parses(tmp_path, cli_env):
    out = tmp_path / "rollout.json"
    subprocess.run(
        [sys.executable, "-m", "fleet_ops.cli", "demo", "--out", str(out)],
        capture_output=True, text=True, cwd=tmp_path, env=cli_env, check=True,
    )
    payload = json.loads(out.read_text())
    assert payload["schema"] == "fleet-ops/rollout-report/v1"


def test_the_help_text_lists_every_subcommand(cli_env):
    result = subprocess.run(
        [sys.executable, "-m", "fleet_ops.cli", "--help"],
        capture_output=True, text=True, env=cli_env,
    )
    for command in ("demo", "sbom-diff", "repro"):
        assert command in result.stdout
