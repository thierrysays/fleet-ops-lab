"""One node through the sequence, mostly by the routes where it stops."""

import pytest

from fleet_ops.artefact import Artefact, Manifest
from fleet_ops.clock import ManualClock
from fleet_ops.node import Node
from fleet_ops.sbom import SBOM, Component
from fleet_ops.transport import FlakyTransport, InMemoryTransport
from fleet_ops.update import update_node


@pytest.fixture
def running_node() -> Node:
    node = Node("n1", confirm_window_s=300.0, clock=ManualClock())
    slot = node.stage("1.0.0", "sha256:old")
    node.mark_verified(slot)
    node.activate()
    node.confirm()
    return node


@pytest.fixture
def release():
    artefact = Artefact("agent", "2.0.0", b"new-image" * 100)
    sbom = SBOM.of("agent", "2.0.0", [Component("zlib", "1.3.1")])
    return artefact, Manifest.describing(artefact, sbom)


def test_a_healthy_update_commits(running_node, release):
    artefact, manifest = release
    outcome = update_node(
        running_node, artefact, manifest, InMemoryTransport(), probe=lambda n: True
    )
    assert outcome.ok is True
    assert outcome.code == "updated"
    assert running_node.running_version == "2.0.0"


def test_a_dropped_transfer_leaves_the_node_on_the_old_version(running_node, release):
    artefact, manifest = release
    transport = FlakyTransport(InMemoryTransport(), fail_nodes=frozenset({"n1"}))
    outcome = update_node(running_node, artefact, manifest, transport, probe=lambda n: True)
    assert outcome.code == "transport-failure"
    assert running_node.running_version == "1.0.0"
    assert outcome.rolled_back is False  # nothing was activated, so nothing reverted


def test_bytes_that_arrive_corrupted_never_reach_a_slot(running_node, release):
    # The transfer succeeded. That is precisely why this check exists.
    artefact, manifest = release
    transport = FlakyTransport(InMemoryTransport(), truncate_nodes=frozenset({"n1"}))
    outcome = update_node(running_node, artefact, manifest, transport, probe=lambda n: True)
    assert outcome.code == "digest-mismatch"
    assert running_node.running_version == "1.0.0"
    assert all(s.version != "2.0.0" for s in running_node.slots)


def test_an_unsigned_release_is_refused_when_a_quorum_is_required(running_node, release):
    artefact, manifest = release
    outcome = update_node(
        running_node, artefact, manifest, InMemoryTransport(),
        probe=lambda n: True, verifier=lambda k, s, p: True, signature_quorum=1,
    )
    assert outcome.code == "signature-invalid"
    assert running_node.running_version == "1.0.0"


def test_a_missing_verifier_refuses_rather_than_waves_it_through(running_node, release):
    artefact, manifest = release
    signed = manifest.signed_by("k1", "whatever")
    outcome = update_node(
        running_node, artefact, signed, InMemoryTransport(),
        probe=lambda n: True, verifier=None, signature_quorum=1,
    )
    assert outcome.code == "signature-invalid"
    assert "cannot run is a check that failed" in outcome.detail


def test_a_failing_probe_rolls_the_node_back(running_node, release):
    artefact, manifest = release
    outcome = update_node(
        running_node, artefact, manifest, InMemoryTransport(), probe=lambda n: False
    )
    assert outcome.code == "health-probe-failed"
    assert outcome.rolled_back is True
    assert running_node.running_version == "1.0.0"


def test_an_absent_probe_is_a_failed_probe(running_node, release):
    artefact, manifest = release
    outcome = update_node(running_node, artefact, manifest, InMemoryTransport(), probe=None)
    assert outcome.ok is False
    assert outcome.rolled_back is True
    assert running_node.running_version == "1.0.0"


def test_a_probe_that_raises_is_a_failed_probe(running_node, release):
    artefact, manifest = release

    def exploding(node):
        raise RuntimeError("probe endpoint unreachable")

    outcome = update_node(
        running_node, artefact, manifest, InMemoryTransport(), probe=exploding
    )
    assert outcome.rolled_back is True
    assert "probe raised" in outcome.detail


def test_the_signature_is_checked_before_the_digest(running_node, release):
    # Order matters: a digest checked against an unauthenticated manifest proves
    # only that the download was not corrupted, which is not the question asked.
    artefact, manifest = release
    transport = FlakyTransport(InMemoryTransport(), truncate_nodes=frozenset({"n1"}))
    outcome = update_node(
        running_node, artefact, manifest, transport,
        probe=lambda n: True, verifier=lambda k, s, p: True, signature_quorum=1,
    )
    assert outcome.code == "signature-invalid"


def test_a_failed_update_does_not_consume_the_rollback_target(running_node, release):
    artefact, manifest = release
    update_node(running_node, artefact, manifest, InMemoryTransport(), probe=lambda n: False)
    later = Artefact("agent", "2.0.1", b"fixed-image" * 100)
    manifest2 = Manifest.describing(
        later, SBOM.of("agent", "2.0.1", [Component("zlib", "1.3.1")])
    )
    outcome = update_node(
        running_node, later, manifest2, InMemoryTransport(), probe=lambda n: True
    )
    assert outcome.ok is True
    assert running_node.running_version == "2.0.1"
