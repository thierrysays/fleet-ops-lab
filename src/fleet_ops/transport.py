"""Getting bytes to a node, badly, which is the normal case.

Constrained edge fleets are on the worst networks anyone deploys to: a factory
Wi-Fi with a metal ceiling, a cellular modem sharing a mast with a car park, a
site link that a forklift disconnects twice a week. A transport that is assumed
to work produces an update process that has never been tested against the
conditions it will actually meet.

So the interface is four methods, failure is an ordinary return path rather than
an exception in the caller's face, and :class:`FlakyTransport` exists to make the
test suite live in the same world as the deployment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .errors import TransportFailure


class Transport(Protocol):
    """Move named blobs to a node and read them back."""

    def put(self, node_id: str, name: str, data: bytes) -> None:
        """Deliver ``data``. Raise :class:`~.errors.TransportFailure` if it did not arrive."""

    def get(self, node_id: str, name: str) -> bytes:
        """Read back what is on the node. Raise on absence."""

    def has(self, node_id: str, name: str) -> bool: ...

    def delete(self, node_id: str, name: str) -> None: ...


class InMemoryTransport:
    """A dictionary. The reference implementation, and what tests use."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], bytes] = {}

    def put(self, node_id: str, name: str, data: bytes) -> None:
        self._store[(node_id, name)] = bytes(data)

    def get(self, node_id: str, name: str) -> bytes:
        try:
            return self._store[(node_id, name)]
        except KeyError:
            raise TransportFailure(f"{node_id}: nothing named {name!r}") from None

    def has(self, node_id: str, name: str) -> bool:
        return (node_id, name) in self._store

    def delete(self, node_id: str, name: str) -> None:
        self._store.pop((node_id, name), None)


class LocalDirTransport:
    """A directory per node. Useful for a bench rig with shared storage."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, node_id: str, name: str) -> Path:
        # Node ids and blob names come from a plan file, which is not a trust
        # boundary but is a typo boundary. Refuse traversal rather than resolve it.
        if "/" in node_id or ".." in node_id or "/" in name or ".." in name:
            raise TransportFailure(f"unsafe path component: {node_id!r}/{name!r}")
        return self.root / node_id / name

    def put(self, node_id: str, name: str, data: bytes) -> None:
        p = self._path(node_id, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so a process killed mid-write
        # leaves the previous blob intact rather than a truncated one.
        tmp = p.with_suffix(p.suffix + ".partial")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, node_id: str, name: str) -> bytes:
        p = self._path(node_id, name)
        if not p.exists():
            raise TransportFailure(f"{node_id}: nothing named {name!r}")
        return p.read_bytes()

    def has(self, node_id: str, name: str) -> bool:
        return self._path(node_id, name).exists()

    def delete(self, node_id: str, name: str) -> None:
        self._path(node_id, name).unlink(missing_ok=True)


class FlakyTransport:
    """Wraps a transport and makes it behave like a real network.

    ``fail_every`` fails one delivery in N. ``truncate_every`` is the nastier
    one: the delivery succeeds and the bytes are wrong. A digest check that has
    only ever been tested against total failure has not been tested.
    """

    def __init__(
        self,
        inner: Transport,
        fail_every: int = 0,
        truncate_every: int = 0,
        fail_nodes: frozenset[str] = frozenset(),
        truncate_nodes: frozenset[str] = frozenset(),
    ) -> None:
        self.inner = inner
        self.fail_every = fail_every
        self.truncate_every = truncate_every
        self.fail_nodes = fail_nodes
        self.truncate_nodes = truncate_nodes
        self._n = 0

    def put(self, node_id: str, name: str, data: bytes) -> None:
        self._n += 1
        if node_id in self.fail_nodes or (
            self.fail_every and self._n % self.fail_every == 0
        ):
            raise TransportFailure(f"{node_id}: link dropped during transfer of {name!r}")
        if node_id in self.truncate_nodes or (
            self.truncate_every and self._n % self.truncate_every == 0
        ):
            self.inner.put(node_id, name, data[: max(0, len(data) // 2)])
            return
        self.inner.put(node_id, name, data)

    def get(self, node_id: str, name: str) -> bytes:
        return self.inner.get(node_id, name)

    def has(self, node_id: str, name: str) -> bool:
        return self.inner.has(node_id, name)

    def delete(self, node_id: str, name: str) -> None:
        self.inner.delete(node_id, name)
