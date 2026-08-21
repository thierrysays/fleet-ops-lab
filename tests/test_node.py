"""The slot machine, and the rule that silence is a rollback."""

import pytest

from fleet_ops.clock import ManualClock
from fleet_ops.errors import NotStaged, SlotUnavailable
from fleet_ops.node import Node, SlotState


def _running_node(clock=None, window=300.0) -> Node:
    node = Node(node_id="n1", confirm_window_s=window, clock=clock or ManualClock())
    slot = node.stage("1.0.0", "sha256:aaa")
    node.mark_verified(slot)
    node.activate()
    node.confirm()
    return node


def test_staging_never_writes_to_the_running_slot():
    node = _running_node()
    active_before = node.active
    staged = node.stage("2.0.0", "sha256:bbb")
    assert staged is not active_before
    assert active_before.version == "1.0.0"
    assert active_before.state is SlotState.ACTIVE


def test_an_unverified_image_is_never_activated():
    node = _running_node()
    node.stage("2.0.0", "sha256:bbb")
    with pytest.raises(NotStaged):
        node.activate()
    assert node.running_version == "1.0.0"


def test_activation_is_provisional_not_committed():
    node = _running_node()
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()
    assert slot.state is SlotState.PENDING
    assert node.active is None
    assert node.state()["awaiting_confirmation"] is True


def test_a_node_that_never_confirms_rolls_itself_back():
    # No server, no operator, no network: the node's own timer does this.
    clock = ManualClock()
    node = _running_node(clock=clock, window=300.0)
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()

    clock.advance(299.0)
    assert node.tick() is False
    assert node.running_version == "2.0.0"

    clock.advance(2.0)
    assert node.tick() is True
    assert node.running_version == "1.0.0"
    assert slot.state is SlotState.FAILED


def test_confirming_within_the_window_commits_the_new_version():
    clock = ManualClock()
    node = _running_node(clock=clock)
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()
    clock.advance(10.0)
    node.confirm()
    clock.advance(10_000.0)
    assert node.tick() is False
    assert node.running_version == "2.0.0"


def test_the_rollback_target_survives_the_failed_activation():
    node = _running_node()
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()
    node.rollback("probe failed")
    assert node.running_version == "1.0.0"
    assert node.active is not None
    assert node.active.digest == "sha256:aaa"


def test_staging_while_a_slot_is_pending_is_refused():
    # Otherwise the second update overwrites the only copy of the version the
    # node would roll back to, and a bad pair of updates bricks the node.
    node = _running_node()
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()
    with pytest.raises(SlotUnavailable):
        node.stage("3.0.0", "sha256:ccc")


def test_confirming_nothing_is_an_error_not_a_no_op():
    with pytest.raises(NotStaged):
        _running_node().confirm()


def test_the_history_records_every_transition():
    node = _running_node()
    slot = node.stage("2.0.0", "sha256:bbb")
    node.mark_verified(slot)
    node.activate()
    node.rollback("probe failed")
    events = [e for e, _ in node.history]
    assert events == [
        "staged", "verified", "activated-pending", "confirmed",
        "staged", "verified", "activated-pending", "rolled-back",
    ]
