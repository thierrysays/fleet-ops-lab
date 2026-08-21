"""Waves and the halt, which is the only feature here that is not optional."""

import pytest

from fleet_ops.artefact import Artefact, Manifest
from fleet_ops.clock import ManualClock
from fleet_ops.node import Node
from fleet_ops.rollout import Rollout, RolloutPlan, Wave
from fleet_ops.sbom import SBOM, Component
from fleet_ops.transport import FlakyTransport, InMemoryTransport


def _fleet(n: int) -> dict[str, Node]:
    nodes = {}
    for i in range(1, n + 1):
        node = Node(f"node-{i:02d}", confirm_window_s=300.0, clock=ManualClock())
        slot = node.stage("1.0.0", "sha256:old")
        node.mark_verified(slot)
        node.activate()
        node.confirm()
        nodes[node.node_id] = node
    return nodes


@pytest.fixture
def release():
    artefact = Artefact("agent", "2.0.0", b"image" * 200)
    return artefact, Manifest.describing(
        artefact, SBOM.of("agent", "2.0.0", [Component("zlib", "1.3.1")])
    )


def test_a_clean_rollout_updates_everything(release):
    artefact, manifest = release
    nodes = _fleet(6)
    plan = RolloutPlan.canary_then_rest("agent", "2.0.0", list(nodes))
    report = Rollout(nodes, InMemoryTransport(), {n: (lambda x: True) for n in nodes}).run(
        plan, artefact, manifest
    )
    assert report.updated == 6
    assert report.halted_at is None
    assert report.untouched == 0


def test_one_canary_failure_stops_the_rollout(release):
    artefact, manifest = release
    nodes = _fleet(20)
    plan = RolloutPlan.canary_then_rest("agent", "2.0.0", list(nodes), canary=1)
    report = Rollout(
        nodes,
        InMemoryTransport(),
        {n: (lambda x: x.node_id != "node-01") for n in nodes},
    ).run(plan, artefact, manifest)
    assert report.halted_at == "canary"
    assert report.updated == 0
    assert report.untouched == 19


def test_the_untouched_nodes_stay_on_the_version_that_was_working(release):
    artefact, manifest = release
    nodes = _fleet(20)
    plan = RolloutPlan.canary_then_rest("agent", "2.0.0", list(nodes), canary=1)
    Rollout(
        nodes, InMemoryTransport(), {n: (lambda x: x.node_id != "node-01") for n in nodes}
    ).run(plan, artefact, manifest)
    assert all(n.running_version == "1.0.0" for n in nodes.values())


def test_failures_within_budget_do_not_halt(release):
    artefact, manifest = release
    nodes = _fleet(11)
    plan = RolloutPlan(
        "agent", "2.0.0",
        (Wave("canary", ("node-01",), 0.0), Wave("fleet", tuple(list(nodes)[1:]), 0.1)),
    )
    # One failure in ten, budget one node: tolerated, rollout completes.
    report = Rollout(
        nodes, InMemoryTransport(), {n: (lambda x: x.node_id != "node-05") for n in nodes}
    ).run(plan, artefact, manifest)
    assert report.halted_at is None
    assert report.failed == 1
    assert report.rolled_back == 1
    assert report.updated == 10


def test_one_failure_beyond_budget_halts(release):
    artefact, manifest = release
    nodes = _fleet(11)
    plan = RolloutPlan(
        "agent", "2.0.0",
        (Wave("canary", ("node-01",), 0.0), Wave("fleet", tuple(list(nodes)[1:]), 0.1)),
    )
    bad = {"node-05", "node-07"}
    report = Rollout(
        nodes, InMemoryTransport(), {n: (lambda x: x.node_id not in bad) for n in nodes}
    ).run(plan, artefact, manifest)
    assert report.halted_at == "fleet"
    assert "budget was 10%" in report.halt_reason


def test_the_report_groups_failures_by_cause(release):
    artefact, manifest = release
    nodes = _fleet(6)
    transport = FlakyTransport(
        InMemoryTransport(),
        fail_nodes=frozenset({"node-03"}),
        truncate_nodes=frozenset({"node-04"}),
    )
    plan = RolloutPlan("agent", "2.0.0", (Wave("all", tuple(nodes), 1.0),))
    report = Rollout(
        nodes, transport, {n: (lambda x: x.node_id != "node-05") for n in nodes}
    ).run(plan, artefact, manifest)
    codes = report.by_code()
    assert codes["transport-failure"] == 1
    assert codes["digest-mismatch"] == 1
    assert codes["health-probe-failed"] == 1
    assert codes["updated"] == 3


def test_a_wave_budget_of_zero_tolerates_nothing(release):
    assert Wave("canary", ("a", "b", "c"), 0.0).tolerated() == 0
    assert Wave("fleet", tuple(f"n{i}" for i in range(10)), 0.1).tolerated() == 1
