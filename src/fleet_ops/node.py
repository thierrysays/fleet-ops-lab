"""A node with two slots, and the rule that makes rollback automatic.

The A/B slot model is old, boring and correct: two copies of the payload, one
running, one spare. Update writes to the spare, activation swaps which one boots,
and the previous one stays intact as the rollback target.

The part that is routinely got wrong is what happens *after* activation.
Everything is fine while an operator is watching. The interesting case is the
node that activates a bad image at 03:00 on a site with no engineer, where the
new image cannot bring up the network it would need to be told to roll back.

So activation here is provisional. It sets a deadline; the node must confirm
before it expires; and expiry reverts to the previous slot. The state that
survives a power cut is ``PENDING``, and ``PENDING`` reverts. Silence is a
rollback, never a success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .clock import Clock, SystemClock
from .errors import NotStaged, SlotUnavailable


class SlotState(str, Enum):
    """What one slot currently holds."""

    EMPTY = "empty"
    STAGED = "staged"
    #: Verified against the manifest and eligible for activation.
    VERIFIED = "verified"
    #: Booted but unconfirmed. Reverts on deadline. This is the interesting one.
    PENDING = "pending"
    ACTIVE = "active"
    #: Activated, failed to confirm, reverted. Kept for the incident report.
    FAILED = "failed"


@dataclass
class Slot:
    """One half of a node."""

    name: str
    state: SlotState = SlotState.EMPTY
    version: str = ""
    digest: str = ""
    boot_attempts: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "version": self.version,
            "digest": self.digest,
            "boot_attempts": self.boot_attempts,
        }


@dataclass
class Node:
    """Two slots, a clock, and a confirmation deadline."""

    node_id: str
    #: Seconds a node has to confirm a new image before it is reverted.
    confirm_window_s: float = 300.0
    clock: Clock = field(default_factory=SystemClock)
    a: Slot = field(default_factory=lambda: Slot("a"))
    b: Slot = field(default_factory=lambda: Slot("b"))
    _deadline: float | None = field(default=None, init=False, repr=False)
    #: Every state transition, in order. The incident report writes itself.
    history: list[tuple[str, str]] = field(default_factory=list, init=False, repr=False)

    # ------------------------------------------------------------------ lookups
    @property
    def slots(self) -> tuple[Slot, Slot]:
        return (self.a, self.b)

    @property
    def active(self) -> Slot | None:
        return next((s for s in self.slots if s.state is SlotState.ACTIVE), None)

    @property
    def pending(self) -> Slot | None:
        return next((s for s in self.slots if s.state is SlotState.PENDING), None)

    @property
    def running_version(self) -> str:
        current = self.pending or self.active
        return current.version if current else ""

    def _spare(self) -> Slot:
        """The slot that is not running and is not the rollback target."""
        if self.pending is not None:
            raise SlotUnavailable(
                f"{self.node_id}: slot {self.pending.name!r} is pending confirmation; "
                "staging now would destroy the rollback target"
            )
        active = self.active
        if active is None:
            return self.a
        spare = self.b if active is self.a else self.a
        return spare

    def _record(self, event: str, detail: str = "") -> None:
        self.history.append((event, detail))

    # ---------------------------------------------------------------- lifecycle
    def stage(self, version: str, digest: str) -> Slot:
        """Write into the spare slot. Never touches what is running."""
        slot = self._spare()
        slot.state = SlotState.STAGED
        slot.version = version
        slot.digest = digest
        slot.boot_attempts = 0
        self._record("staged", f"{slot.name}:{version}")
        return slot

    def mark_verified(self, slot: Slot) -> None:
        if slot.state is not SlotState.STAGED:
            raise NotStaged(f"{self.node_id}: slot {slot.name!r} is {slot.state.value}")
        slot.state = SlotState.VERIFIED
        self._record("verified", f"{slot.name}:{slot.version}")

    def activate(self) -> Slot:
        """Boot the verified slot, provisionally. Starts the confirmation clock."""
        slot = next((s for s in self.slots if s.state is SlotState.VERIFIED), None)
        if slot is None:
            raise NotStaged(
                f"{self.node_id}: nothing verified to activate; "
                "an unverified image is never booted"
            )
        previous = self.active
        if previous is not None:
            # The previous slot keeps its contents and becomes the rollback
            # target. It is not erased, not overwritten, and not marked empty.
            previous.state = SlotState.VERIFIED
        slot.state = SlotState.PENDING
        slot.boot_attempts += 1
        self._deadline = self.clock.monotonic() + self.confirm_window_s
        self._record("activated-pending", f"{slot.name}:{slot.version}")
        return slot

    def confirm(self) -> None:
        """The node reports that it came up and works. Only now is it committed."""
        slot = self.pending
        if slot is None:
            raise NotStaged(f"{self.node_id}: nothing pending confirmation")
        slot.state = SlotState.ACTIVE
        for other in self.slots:
            if other is not slot and other.state is SlotState.ACTIVE:
                other.state = SlotState.VERIFIED
        self._deadline = None
        self._record("confirmed", f"{slot.name}:{slot.version}")

    def rollback(self, reason: str) -> Slot | None:
        """Revert to the previous slot, which was never destroyed."""
        failed = self.pending
        if failed is None:
            return None
        failed.state = SlotState.FAILED
        target = next((s for s in self.slots if s is not failed), None)
        if target is not None and target.version:
            target.state = SlotState.ACTIVE
        self._deadline = None
        self._record("rolled-back", f"{failed.name}:{failed.version} ({reason})")
        return target

    def tick(self) -> bool:
        """Advance the node's own timers. Returns True if it rolled itself back.

        This is what a node's supervisor calls, and what a watchdog would do in
        firmware. It takes no arguments and consults no server: a node that can
        only roll back when told to is a node that cannot roll back.
        """
        if self._deadline is None or self.pending is None:
            return False
        if self.clock.monotonic() < self._deadline:
            return False
        self.rollback("confirmation window expired")
        return True

    # ----------------------------------------------------------------- reporting
    def state(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "running_version": self.running_version,
            "slots": [s.as_dict() for s in self.slots],
            "awaiting_confirmation": self.pending is not None,
        }
