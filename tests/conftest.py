"""Shared fixtures, and the rule that a test's tier is the directory it is in."""

from __future__ import annotations

import os
import pathlib

import pytest

from fleet_ops.artefact import Artefact, Manifest
from fleet_ops.clock import ManualClock
from fleet_ops.node import Node
from fleet_ops.sbom import SBOM, Component


def running_node(node_id: str = "n1", version: str = "1.0.0", window: float = 300.0,
                 clock=None) -> Node:
    """A node already running a confirmed version, so there is something to lose."""
    node = Node(node_id=node_id, confirm_window_s=window, clock=clock or ManualClock())
    slot = node.stage(version, "sha256:" + "1" * 64)
    node.mark_verified(slot)
    node.activate()
    node.confirm()
    return node


def release(version: str = "2.0.0", payload: bytes | None = None) -> tuple[Artefact, Manifest]:
    artefact = Artefact("agent", version, payload or (f"agent {version}".encode() * 64))
    sbom = SBOM.of("agent", version, [Component("zlib", "1.3.1", licence="Zlib")])
    return artefact, Manifest.describing(artefact, sbom)


@pytest.fixture
def node() -> Node:
    return running_node()


@pytest.fixture
def fleet():
    def _build(n: int, clock=None):
        return {f"node-{i:02d}": running_node(f"node-{i:02d}", clock=clock)
                for i in range(1, n + 1)}
    return _build


@pytest.fixture
def release_factory():
    return release


@pytest.fixture
def cli_env() -> dict[str, str]:
    """Environment for a subprocess that must find the package.

    The end-to-end tiers run the CLI as a real process rather than calling
    ``main()``. A deployment tool that only works when imported by its own test
    suite is a tool nobody can deploy with.
    """
    src = str(pathlib.Path(__file__).resolve().parent.parent / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    return env


# The tier a test belongs to is the directory it sits in. Applying the marker
# from the path rather than by hand means a test cannot be moved into a tier and
# keep the old label, which is the way tier markers usually rot.
_TIERS = {"unit", "functional", "smoke", "security", "pentest"}


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        for part in pathlib.Path(str(item.fspath)).parts:
            if part in _TIERS:
                item.add_marker(getattr(pytest.mark, part))
                break
