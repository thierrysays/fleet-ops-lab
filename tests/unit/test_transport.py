"""Getting bytes to a node, including when that fails."""

import pytest

from fleet_ops.errors import TransportFailure
from fleet_ops.transport import FlakyTransport, InMemoryTransport, LocalDirTransport


def test_reading_something_that_was_never_delivered_is_a_failure_not_an_empty_blob():
    with pytest.raises(TransportFailure):
        InMemoryTransport().get("n1", "image.bin")


def test_a_local_directory_round_trips(tmp_path):
    t = LocalDirTransport(tmp_path)
    t.put("n1", "image.bin", b"payload")
    assert t.get("n1", "image.bin") == b"payload"
    assert t.has("n1", "image.bin") is True
    t.delete("n1", "image.bin")
    assert t.has("n1", "image.bin") is False


def test_a_local_write_leaves_no_partial_file_behind(tmp_path):
    t = LocalDirTransport(tmp_path)
    t.put("n1", "image.bin", b"payload")
    assert list((tmp_path / "n1").glob("*.partial")) == []


def test_path_components_that_escape_the_node_directory_are_refused(tmp_path):
    t = LocalDirTransport(tmp_path)
    with pytest.raises(TransportFailure):
        t.put("../elsewhere", "image.bin", b"x")
    with pytest.raises(TransportFailure):
        t.get("n1", "../../etc/passwd")


def test_a_flaky_link_can_drop_a_transfer():
    t = FlakyTransport(InMemoryTransport(), fail_nodes=frozenset({"n2"}))
    t.put("n1", "image.bin", b"payload")
    with pytest.raises(TransportFailure):
        t.put("n2", "image.bin", b"payload")


def test_a_truncating_link_succeeds_and_delivers_the_wrong_bytes():
    # The failure mode a "did the download succeed" check cannot see.
    t = FlakyTransport(InMemoryTransport(), truncate_nodes=frozenset({"n1"}))
    t.put("n1", "image.bin", b"x" * 100)
    assert len(t.get("n1", "image.bin")) == 50


def test_every_nth_transfer_can_be_made_to_fail():
    t = FlakyTransport(InMemoryTransport(), fail_every=3)
    t.put("n1", "a", b"1")
    t.put("n1", "b", b"2")
    with pytest.raises(TransportFailure):
        t.put("n1", "c", b"3")
