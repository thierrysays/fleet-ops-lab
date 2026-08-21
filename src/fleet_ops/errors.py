"""One exception per way an update is refused, each with a stable ``code``.

The codes are the interface. A fleet dashboard that greps message text breaks on
the first rewording; one that switches on ``code`` does not, and the codes are
what end up in the incident report.
"""

from __future__ import annotations


class FleetOpsError(Exception):
    """Base class. Carries a stable, machine-readable ``code``."""

    code = "fleet-ops-error"


class DigestMismatch(FleetOpsError):
    """The bytes that arrived are not the bytes the manifest describes.

    This is the single most important refusal in the package. A partial download,
    a corrupted flash write and a substituted image are indistinguishable at this
    point, and all three must stop the update.
    """

    code = "digest-mismatch"

    def __init__(self, expected: str, actual: str, name: str) -> None:
        super().__init__(f"{name}: manifest says {expected}, bytes hash to {actual}")
        self.expected = expected
        self.actual = actual
        self.name = name


class SignatureInvalid(FleetOpsError):
    """The manifest is not signed by anyone this node trusts."""

    code = "signature-invalid"


class SbomMissing(FleetOpsError):
    """An artefact arrived without a bill of materials.

    Refused rather than warned about. An artefact with no SBOM is an artefact
    nobody can answer a vulnerability question about, and the answer is needed on
    the day the question is asked, not sixty days later.
    """

    code = "sbom-missing"


class SlotUnavailable(FleetOpsError):
    """There is nowhere to stage this without destroying the rollback target."""

    code = "slot-unavailable"


class NotStaged(FleetOpsError):
    """Activation was attempted with nothing verified in the inactive slot."""

    code = "not-staged"


class TransportFailure(FleetOpsError):
    """The bytes did not arrive. Ordinary, expected, and not an error state."""

    code = "transport-failure"


class RolloutHalted(FleetOpsError):
    """A wave exceeded its failure budget and the rollout stopped itself."""

    code = "rollout-halted"

    def __init__(self, wave: str, failed: int, attempted: int, budget: float) -> None:
        super().__init__(
            f"wave {wave!r}: {failed}/{attempted} failed, budget {budget:.0%}"
        )
        self.wave = wave
        self.failed = failed
        self.attempted = attempted
        self.budget = budget
