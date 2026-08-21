"""A deterministic rollout across a simulated fleet, with things going wrong.

The scenario is fixed and the failures are planted, because a demo where
everything succeeds demonstrates nothing. Twelve nodes in three waves — a
canary, a pilot, then the rest — and four planted failures, all in the pilot:

* ``node-03`` is never reachable — the transfer fails and it stays on the old
  version, which is the correct outcome and not an incident;
* ``node-04`` gets a truncated download — the digest check catches bytes that
  arrived successfully and are wrong, which is the failure mode a "did the
  download succeed" check misses entirely;
* ``node-05`` comes up and fails its health probe — it rolls itself back;
* ``node-06`` has no health probe configured — treated as a *failed* probe and
  rolled back, because a node nobody can ask about does not get to keep a
  change.

Four failures against a pilot budget of 20% on five nodes — one tolerated — so
the rollout halts before the third wave. Six nodes are never touched and stay on
the version that was working.

``fol demo`` must always print **2 rolled back** and **6 untouched**. If it does
not, something regressed; do not adjust the scenario to match the new output.
"""

from __future__ import annotations

from .artefact import Artefact, Manifest
from .node import Node
from .rollout import Rollout, RolloutPlan, RolloutReport, Wave
from .sbom import SBOM, Component
from .transport import FlakyTransport, InMemoryTransport

NODE_IDS = tuple(f"node-{i:02d}" for i in range(1, 13))

UNREACHABLE = "node-03"
TRUNCATED = "node-04"
UNHEALTHY = "node-05"
NO_PROBE = "node-06"


def _sbom(version: str) -> SBOM:
    return SBOM.of(
        "inspection-agent",
        version,
        [
            Component("zlib", "1.3.1", kind="library", licence="Zlib"),
            Component("libwebsockets", "4.3.3", kind="library", licence="MIT"),
            Component("tflite-micro", "1.3.0", kind="library", licence="Apache-2.0"),
            Component("inspection-model", "7", kind="model", licence="proprietary"),
        ],
    )


def build_artefact(version: str = "2.4.0") -> tuple[Artefact, Manifest]:
    artefact = Artefact(
        name="inspection-agent",
        version=version,
        payload=f"inspection-agent {version} payload".encode() * 64,
    )
    manifest = Manifest.describing(
        artefact, _sbom(version), build_inputs_digest="sha256:" + "0" * 64
    )
    return artefact, manifest


def run_demo(confirm_window_s: float = 300.0) -> tuple[RolloutReport, dict[str, Node]]:
    artefact, manifest = build_artefact()

    nodes = {
        n: Node(node_id=n, confirm_window_s=confirm_window_s) for n in NODE_IDS
    }
    # Every node starts on 2.3.0, confirmed, so there is something to roll back to.
    for node in nodes.values():
        slot = node.stage("2.3.0", "sha256:" + "1" * 64)
        node.mark_verified(slot)
        node.activate()
        node.confirm()

    transport = FlakyTransport(
        InMemoryTransport(),
        fail_nodes=frozenset({UNREACHABLE}),
        truncate_nodes=frozenset({TRUNCATED}),
    )

    probes = {
        n: (lambda node: node.node_id != UNHEALTHY)
        for n in NODE_IDS
        if n != NO_PROBE  # deliberately absent, and therefore a failure
    }

    plan = RolloutPlan(
        artefact_name="inspection-agent",
        version="2.4.0",
        waves=(
            # The canary absorbs nothing. One failure here is the canary working.
            Wave("canary", NODE_IDS[:1], failure_budget=0.0),
            Wave("pilot", NODE_IDS[1:6], failure_budget=0.2),
            Wave("fleet", NODE_IDS[6:], failure_budget=0.1),
        ),
    )
    report = Rollout(nodes=nodes, transport=transport, probes=probes).run(
        plan, artefact, manifest
    )
    return report, nodes
