"""Waves, a canary, and the halt that is not optional.

A fleet-wide update that goes out to everything at once is a fleet-wide outage
waiting for one bad build. The mitigation is old: send it to a few, watch, then
widen. What matters is what happens when the few fail.

Here, the halt is structural. A wave whose failure ratio exceeds its budget stops
the rollout, and there is no flag to continue — because the flag would be set at
three in the morning by someone who has been awake for nineteen hours and wants
the deployment finished. A stopped rollout leaves the remaining nodes on the old
version, which is the version that was working.

The canary wave defaults to a budget of zero. One failure in the canary is the
canary doing its job.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .artefact import Artefact, Manifest
from .node import Node
from .transport import Transport
from .update import HealthProbe, SignatureVerifier, UpdateOutcome, update_node


@dataclass(frozen=True, slots=True)
class Wave:
    """A named group of nodes and the failure it is allowed to absorb."""

    name: str
    node_ids: tuple[str, ...]
    #: Fraction of the wave that may fail before the rollout halts.
    failure_budget: float = 0.0

    def tolerated(self) -> int:
        return int(len(self.node_ids) * self.failure_budget)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_ids": list(self.node_ids),
            "failure_budget": self.failure_budget,
        }


@dataclass(frozen=True, slots=True)
class RolloutPlan:
    """Which nodes, in which order, under which budgets."""

    artefact_name: str
    version: str
    waves: tuple[Wave, ...]

    @classmethod
    def canary_then_rest(
        cls,
        artefact_name: str,
        version: str,
        node_ids: Sequence[str],
        canary: int = 1,
        rest_budget: float = 0.1,
    ) -> RolloutPlan:
        """The default shape: a canary at zero budget, then everything else."""
        canary = max(1, min(canary, len(node_ids)))
        return cls(
            artefact_name=artefact_name,
            version=version,
            waves=(
                Wave("canary", tuple(node_ids[:canary]), failure_budget=0.0),
                Wave("fleet", tuple(node_ids[canary:]), failure_budget=rest_budget),
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "artefact": self.artefact_name,
            "version": self.version,
            "waves": [w.as_dict() for w in self.waves],
        }


@dataclass(frozen=True, slots=True)
class RolloutReport:
    """What the rollout did, and where it stopped."""

    plan: RolloutPlan
    outcomes: tuple[UpdateOutcome, ...]
    halted_at: str | None
    halt_reason: str

    @property
    def updated(self) -> int:
        return sum(1 for o in self.outcomes if o.ok)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok)

    @property
    def rolled_back(self) -> int:
        return sum(1 for o in self.outcomes if o.rolled_back)

    @property
    def untouched(self) -> int:
        attempted = {o.node_id for o in self.outcomes}
        return sum(
            1 for w in self.plan.waves for n in w.node_ids if n not in attempted
        )

    def by_code(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.outcomes:
            counts[o.code] = counts.get(o.code, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "fleet-ops/rollout-report/v1",
            "plan": self.plan.as_dict(),
            "updated": self.updated,
            "failed": self.failed,
            "rolled_back": self.rolled_back,
            "untouched": self.untouched,
            "halted_at": self.halted_at,
            "halt_reason": self.halt_reason,
            "by_code": self.by_code(),
            "outcomes": [o.as_dict() for o in self.outcomes],
        }


@dataclass
class Rollout:
    """Runs a plan across a fleet, wave by wave, and stops when told to by the data."""

    nodes: dict[str, Node]
    transport: Transport
    probes: dict[str, HealthProbe] = field(default_factory=dict)
    verifier: SignatureVerifier | None = None
    signature_quorum: int = 0

    def run(
        self, plan: RolloutPlan, artefact: Artefact, manifest: Manifest
    ) -> RolloutReport:
        outcomes: list[UpdateOutcome] = []
        halted_at: str | None = None
        halt_reason = ""

        for wave in plan.waves:
            wave_outcomes = [
                update_node(
                    self.nodes[node_id],
                    artefact,
                    manifest,
                    self.transport,
                    probe=self.probes.get(node_id),
                    verifier=self.verifier,
                    signature_quorum=self.signature_quorum,
                )
                for node_id in wave.node_ids
                if node_id in self.nodes
            ]
            outcomes.extend(wave_outcomes)

            failures = sum(1 for o in wave_outcomes if not o.ok)
            if failures > wave.tolerated():
                halted_at = wave.name
                halt_reason = (
                    f"{failures}/{len(wave_outcomes)} failed in wave {wave.name!r}, "
                    f"budget was {wave.failure_budget:.0%} "
                    f"({wave.tolerated()} node(s))"
                )
                break

        return RolloutReport(
            plan=plan,
            outcomes=tuple(outcomes),
            halted_at=halted_at,
            halt_reason=halt_reason,
        )


def fleet_of(node_ids: Iterable[str], **node_kwargs: Any) -> dict[str, Node]:
    """Convenience: a dict of fresh nodes, for tests and demos."""
    return {n: Node(node_id=n, **node_kwargs) for n in node_ids}
