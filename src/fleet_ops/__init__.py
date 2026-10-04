"""fleet-ops-lab, updating a fleet of constrained nodes without bricking it.

Nothing in this package is clever, and that is the point. Over-the-air update,
rollback, a bill of materials, and a build that produces the same bytes twice
are the four questions an industrial buyer asks before they ask anything about
the model. They are also the four that get postponed until a field failure makes
them urgent.

The design rule throughout: **an update is provisional until the node says
otherwise.** Activation is a promise to try, not a commitment. A node that
activates a new slot and then fails to check in (because the image is bad,
because the network died, because someone pulled the power) reverts to what it
was running before, without anybody being available to intervene. The default
outcome of silence is rollback.

The second rule: **the fleet halts itself.** A wave that exceeds its failure
budget stops the rollout. Continuing is not an option a flag can enable, because
the flag is always enabled at three in the morning.

Nothing here knows what a node is. A node has slots, a digest, a health probe
and a transport. Whether that is a Linux SBC, a microcontroller with two flash
banks, or a container on a k3s node at the edge is the deployment's business.
"""

from .artefact import Artefact, Manifest
from .node import Node, Slot, SlotState
from .rollout import Rollout, RolloutPlan, RolloutReport, Wave
from .sbom import SBOM, Component, SbomDiff
from .update import UpdateOutcome, update_node

__all__ = [
    "Artefact",
    "Manifest",
    "Node",
    "Slot",
    "SlotState",
    "Rollout",
    "RolloutPlan",
    "RolloutReport",
    "Wave",
    "SBOM",
    "Component",
    "SbomDiff",
    "UpdateOutcome",
    "update_node",
]

__version__ = "0.1.0"
