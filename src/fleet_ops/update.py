"""One node, one update, and the six ways it is allowed to stop.

The sequence is fixed, and the order is load-bearing:

1. **Transfer** the artefact and its manifest.
2. **Verify the signature** on the manifest — with a verifier the caller
   supplied, because an absent verifier is a failed check and not a skipped one.
3. **Verify the digest** of the bytes against the manifest that was just proven
   authentic. In that order: checking a digest against an unauthenticated
   manifest proves the download was not corrupted, which is not the question.
4. **Stage** into the spare slot, never the running one.
5. **Activate** provisionally.
6. **Probe**. A passing probe confirms; a failing or absent probe rolls back.

Every stopping point leaves the node running what it was running before, and
every one of them has a code. There is no path through this function that leaves
a node running an image whose manifest did not verify, and adding one would be a
defect rather than a feature.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .artefact import Artefact, Manifest
from .errors import FleetOpsError
from .node import Node
from .transport import Transport

#: A probe answers one question: is this node healthy on the image it just
#: booted. It is supplied by the deployment, because only the deployment knows.
HealthProbe = Callable[[Node], bool]

#: ``(key_id, signature, payload) -> bool``. Supplied by whoever holds the keys.
SignatureVerifier = Callable[[str, str, bytes], bool]


@dataclass(frozen=True, slots=True)
class UpdateOutcome:
    """What happened to one node, in a form a dashboard can group by."""

    node_id: str
    ok: bool
    #: Stable reason code: ``updated``, ``transport-failure``, ``digest-mismatch``,
    #: ``signature-invalid``, ``health-probe-failed``, ``slot-unavailable``…
    code: str
    detail: str
    from_version: str
    to_version: str
    rolled_back: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "ok": self.ok,
            "code": self.code,
            "detail": self.detail,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "rolled_back": self.rolled_back,
        }


def update_node(
    node: Node,
    artefact: Artefact,
    manifest: Manifest,
    transport: Transport,
    probe: HealthProbe | None = None,
    verifier: SignatureVerifier | None = None,
    signature_quorum: int = 0,
) -> UpdateOutcome:
    """Run one node through the sequence. Never raises for an ordinary failure."""
    from_version = node.running_version

    def failed(code: str, detail: str, rolled_back: bool = False) -> UpdateOutcome:
        return UpdateOutcome(
            node_id=node.node_id,
            ok=False,
            code=code,
            detail=detail,
            from_version=from_version,
            to_version=manifest.version,
            rolled_back=rolled_back,
        )

    # 1. transfer -------------------------------------------------------------
    try:
        transport.put(node.node_id, f"{manifest.name}.bin", artefact.payload)
        received = Artefact(
            name=manifest.name,
            version=manifest.version,
            payload=transport.get(node.node_id, f"{manifest.name}.bin"),
        )
    except FleetOpsError as exc:
        return failed(exc.code, str(exc))

    # 2. authenticate the manifest, 3. bind it to the bytes --------------------
    try:
        manifest.verify_signature(verifier, quorum=signature_quorum)
        manifest.verify_artefact(received)
    except FleetOpsError as exc:
        transport.delete(node.node_id, f"{manifest.name}.bin")
        return failed(exc.code, str(exc))

    # 4. stage, 5. activate provisionally --------------------------------------
    try:
        slot = node.stage(manifest.version, manifest.artefact_digest)
        node.mark_verified(slot)
        node.activate()
    except FleetOpsError as exc:
        return failed(exc.code, str(exc))

    # 6. probe ------------------------------------------------------------------
    healthy = False
    detail = "no health probe supplied"
    if probe is not None:
        try:
            healthy = bool(probe(node))
            detail = "health probe passed" if healthy else "health probe failed"
        except Exception as exc:  # a probe that throws is a probe that failed
            healthy = False
            detail = f"health probe raised: {exc}"

    if not healthy:
        # An absent probe is a failed probe. A node nobody can ask about is a
        # node that gets rolled back, because the alternative is a fleet of
        # machines running an unverified change on the strength of silence.
        node.rollback(detail)
        return failed("health-probe-failed", detail, rolled_back=True)

    node.confirm()
    return UpdateOutcome(
        node_id=node.node_id,
        ok=True,
        code="updated",
        detail=detail,
        from_version=from_version,
        to_version=manifest.version,
    )
