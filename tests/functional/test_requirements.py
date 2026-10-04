"""Functional: one test per requirement in `docs/FUNCTIONAL_SPEC.md`.

Written from the specification rather than from the code, and named for the
requirement each discharges. Where a requirement is about something an operator
runs, the test runs it as a real subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from fleet_ops.artefact import Artefact, Manifest
from fleet_ops.clock import ManualClock
from fleet_ops.errors import SbomMissing
from fleet_ops.node import SlotState
from fleet_ops.rollout import Rollout, RolloutPlan, Wave
from fleet_ops.sbom import SBOM, Component, diff
from fleet_ops.transport import FlakyTransport, InMemoryTransport
from fleet_ops.update import update_node
from tests.conftest import release, running_node


def _cli(tmp_path, cli_env, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "fleet_ops.cli", *args],
        capture_output=True, text=True, cwd=tmp_path, env=cli_env,
    )


# ------------------------------------------------------------------ FR-1
def test_fr1_an_update_is_provisional_until_the_node_confirms():
    """FR-1, activation starts a confirmation window; it does not commit."""
    clock = ManualClock()
    node = running_node(clock=clock)
    artefact, manifest = release()
    slot = node.stage(manifest.version, manifest.artefact_digest)
    node.mark_verified(slot)
    node.activate()
    assert slot.state is SlotState.PENDING
    assert node.active is None
    assert node.state()["awaiting_confirmation"] is True


# ------------------------------------------------------------------ FR-2
def test_fr2_a_node_that_never_confirms_reverts_on_its_own_timer():
    """FR-2, silence is a rollback, driven by the node, consulting nothing."""
    clock = ManualClock()
    node = running_node(clock=clock, window=300.0)
    slot = node.stage("2.0.0", "sha256:new")
    node.mark_verified(slot)
    node.activate()

    clock.advance(299.0)
    assert node.tick() is False
    clock.advance(2.0)
    assert node.tick() is True
    assert node.running_version == "1.0.0"


# ------------------------------------------------------------------ FR-3
def test_fr3_bytes_that_do_not_match_the_manifest_never_reach_a_slot():
    """FR-3, the digest is checked on the node, after transfer."""
    node = running_node()
    artefact, manifest = release()
    transport = FlakyTransport(InMemoryTransport(), truncate_nodes=frozenset({"n1"}))
    outcome = update_node(node, artefact, manifest, transport, probe=lambda n: True)
    assert outcome.code == "digest-mismatch"
    assert node.running_version == "1.0.0"
    assert all(s.version != "2.0.0" for s in node.slots)


# ------------------------------------------------------------------ FR-4
def test_fr4_a_missing_health_probe_is_a_failed_probe():
    """FR-4, an update nobody can confirm is rolled back, not kept."""
    node = running_node()
    artefact, manifest = release()
    outcome = update_node(node, artefact, manifest, InMemoryTransport(), probe=None)
    assert outcome.ok is False
    assert outcome.rolled_back is True
    assert node.running_version == "1.0.0"


# ------------------------------------------------------------------ FR-5
def test_fr5_a_required_signature_with_no_verifier_is_a_failure():
    """FR-5, a check that cannot run is a check that failed."""
    node = running_node()
    artefact, manifest = release()
    signed = manifest.signed_by("k1", "whatever")
    outcome = update_node(node, artefact, signed, InMemoryTransport(),
                          probe=lambda n: True, verifier=None, signature_quorum=1)
    assert outcome.code == "signature-invalid"
    assert node.running_version == "1.0.0"


# ------------------------------------------------------------------ FR-6
def test_fr6_an_artefact_without_a_bill_of_materials_cannot_be_described():
    """FR-6, no SBOM, no manifest, therefore no deployment."""
    artefact = Artefact("agent", "2.0.0", b"payload")
    with pytest.raises(SbomMissing):
        Manifest.describing(artefact, None)


# ------------------------------------------------------------------ FR-7
def test_fr7_a_wave_beyond_its_budget_halts_the_rollout(fleet):
    """FR-7, the fleet stops itself, and the rest stay on the old version."""
    nodes = fleet(20)
    artefact, manifest = release()
    plan = RolloutPlan.canary_then_rest("agent", "2.0.0", list(nodes), canary=1)
    report = Rollout(nodes, InMemoryTransport(),
                     {n: (lambda x: x.node_id != "node-01") for n in nodes}).run(
        plan, artefact, manifest)
    assert report.halted_at == "canary"
    assert report.untouched == 19
    assert all(n.running_version == "1.0.0" for n in nodes.values())


def test_fr7_there_is_no_parameter_that_continues_past_a_halt():
    """The absence is the feature: `Rollout.run` takes no override."""
    import inspect

    signature = inspect.signature(Rollout.run)
    assert set(signature.parameters) == {"self", "plan", "artefact", "manifest"}


# ------------------------------------------------------------------ FR-8
def test_fr8_staging_is_refused_while_a_slot_is_pending():
    """FR-8, the rollback target is never overwritten."""
    from fleet_ops.errors import SlotUnavailable

    node = running_node()
    slot = node.stage("2.0.0", "sha256:new")
    node.mark_verified(slot)
    node.activate()
    with pytest.raises(SlotUnavailable):
        node.stage("3.0.0", "sha256:newer")


# ------------------------------------------------------------------ FR-9
def test_fr9_the_report_groups_outcomes_by_cause(fleet):
    """FR-9, every stopping point has a stable code a dashboard can group by."""
    nodes = fleet(6)
    artefact, manifest = release()
    transport = FlakyTransport(InMemoryTransport(),
                               fail_nodes=frozenset({"node-03"}),
                               truncate_nodes=frozenset({"node-04"}))
    plan = RolloutPlan("agent", "2.0.0", (Wave("all", tuple(nodes), 1.0),))
    report = Rollout(nodes, transport,
                     {n: (lambda x: x.node_id != "node-05") for n in nodes}).run(
        plan, artefact, manifest)
    codes = report.by_code()
    assert codes == {"digest-mismatch": 1, "health-probe-failed": 1,
                     "transport-failure": 1, "updated": 3}


# ------------------------------------------------------------------ FR-10
def test_fr10_an_sbom_diff_names_what_appeared():
    """FR-10, the diff is the useful part, not the document."""
    before = SBOM.of("agent", "1.0", [Component("zlib", "1.3.1", licence="Zlib")])
    after = SBOM.of("agent", "2.0", [
        Component("zlib", "1.3.1", licence="Zlib"),
        Component("telemetry-shim", "0.2.0", licence="BUSL-1.1"),
    ])
    d = diff(before, after)
    assert [c.name for c in d.added] == ["telemetry-shim"]
    assert d.is_empty is False


def test_fr10_a_relicensed_dependency_is_surfaced_separately():
    before = SBOM.of("agent", "1.0", [Component("thing", "2.1.0", licence="MIT")])
    after = SBOM.of("agent", "2.0", [Component("thing", "2.1.1", licence="BUSL-1.1")])
    assert len(diff(before, after).licence_changes) == 1


# ------------------------------------------------------------------ FR-11
def test_fr11_the_sbom_diff_can_gate_a_pipeline(tmp_path, cli_env):
    """FR-11, a CI gate needs an exit code, not a paragraph."""
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(SBOM.of("agent", "1.0", [Component("zlib", "1.3.1")]).as_dict()))
    b.write_text(json.dumps(SBOM.of("agent", "2.0", [Component("zlib", "1.3.2")]).as_dict()))
    assert _cli(tmp_path, cli_env, "sbom-diff", str(a), str(b), "--fail-on-change").returncode == 1
    assert _cli(tmp_path, cli_env, "sbom-diff", str(a), str(a), "--fail-on-change").returncode == 0


# ------------------------------------------------------------------ FR-12
def test_fr12_a_non_reproducible_build_names_the_files_that_differ(tmp_path, cli_env):
    """FR-12, "not reproducible" is useless; the paths are the deliverable."""
    for name, stamp in (("a", "one"), ("b", "two")):
        d = tmp_path / name
        (d / "bin").mkdir(parents=True)
        (d / "bin" / "agent").write_text("ELF")
        (d / "build-stamp.txt").write_text(stamp)
    result = _cli(tmp_path, cli_env, "repro", str(tmp_path / "a"), str(tmp_path / "b"))
    assert result.returncode == 1
    assert "~ build-stamp.txt" in result.stdout
    assert "bin/agent" not in result.stdout  # matched, so not named


# ------------------------------------------------------------------ FR-13
def test_fr13_the_demo_scenario_holds_its_pinned_counts(tmp_path, cli_env):
    """FR-13, the demo is a fixture. Its numbers are part of the contract."""
    out = tmp_path / "rollout.json"
    result = _cli(tmp_path, cli_env, "demo", "--out", str(out))
    assert result.returncode == 0
    payload = json.loads(out.read_text())
    assert payload["rolled_back"] == 2
    assert payload["untouched"] == 6
    assert payload["halted_at"] == "pilot"


# ------------------------------------------------------------------ FR-14
def test_fr14_a_node_records_every_transition_it_made():
    """FR-14, the incident report writes itself."""
    node = running_node()
    slot = node.stage("2.0.0", "sha256:new")
    node.mark_verified(slot)
    node.activate()
    node.rollback("probe failed")
    assert [event for event, _ in node.history][-4:] == [
        "staged", "verified", "activated-pending", "rolled-back",
    ]


def test_fr14_the_rollback_reason_is_carried_not_summarised():
    node = running_node()
    slot = node.stage("2.0.0", "sha256:new")
    node.mark_verified(slot)
    node.activate()
    node.rollback("health probe returned 503")
    assert any("503" in detail for _, detail in node.history)
