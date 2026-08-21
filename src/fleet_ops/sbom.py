"""A bill of materials, and the diff that is the actually useful part.

Producing an SBOM is a compliance exercise. Diffing two of them is an
engineering one: what changed between the version running in the field and the
version about to replace it, and did anything appear that nobody chose.

The format here is deliberately small — name, version, kind, licence, digest,
supplier — and maps onto the common subset of CycloneDX and SPDX rather than
implementing either. A full CycloneDX document is a fine export target; it is a
poor working representation, and this package does not want a parser dependency
to answer "what changed".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, fields
from typing import Any

from . import canonical

SCHEMA = "fleet-ops/sbom/v1"


@dataclass(frozen=True, slots=True)
class Component:
    """One thing in the image that somebody else wrote."""

    name: str
    version: str
    #: ``library``, ``application``, ``firmware``, ``os``, ``container``, ``model``.
    kind: str = "library"
    licence: str = ""
    #: Digest of the component as shipped, where one is available.
    digest: str = ""
    supplier: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "licence": self.licence,
            "digest": self.digest,
            "supplier": self.supplier,
        }


@dataclass(frozen=True, slots=True)
class SBOM:
    """The components of one artefact, at one version."""

    artefact: str
    version: str
    components: tuple[Component, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        artefact: str,
        version: str,
        components: Iterable[Component],
        **metadata: Any,
    ) -> SBOM:
        # Sorted at construction: an SBOM whose digest depends on the order the
        # scanner happened to walk the filesystem is not a digest of anything.
        return cls(
            artefact=artefact,
            version=version,
            components=tuple(sorted(components, key=lambda c: (c.kind, c.name, c.version))),
            metadata=dict(metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "artefact": self.artefact,
            "version": self.version,
            "components": [c.as_dict() for c in self.components],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SBOM:
        """Load a bill of materials from untrusted JSON.

        Every failure here is a refusal with a reason. An SBOM that cannot be
        parsed is not an empty SBOM: treating it as one would let a malformed
        file through the very check that exists to say what is inside an image.
        """
        if not isinstance(raw, dict):
            raise ValueError("an SBOM must be a JSON object")
        if raw.get("schema") != SCHEMA:
            raise ValueError(f"unknown SBOM schema {raw.get('schema')!r}")
        for required in ("artefact", "version"):
            if not isinstance(raw.get(required), str):
                raise ValueError(f"SBOM {required!r} must be a string")
        components_raw = raw.get("components", [])
        if not isinstance(components_raw, list):
            raise ValueError("SBOM 'components' must be a list")

        known = {f.name for f in fields(Component)}
        components = []
        for entry in components_raw:
            if not isinstance(entry, dict):
                raise ValueError("each SBOM component must be a JSON object")
            unknown = set(entry) - known
            if unknown:
                # Refused rather than ignored. A field this version does not
                # understand may be the one that matters, and silently dropping
                # it produces a diff that says nothing changed.
                raise ValueError(
                    f"unknown component field(s): {', '.join(sorted(unknown))}"
                )
            missing = {"name", "version"} - set(entry)
            if missing:
                raise ValueError(
                    f"component missing required field(s): {', '.join(sorted(missing))}"
                )
            components.append(Component(**entry))

        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("SBOM 'metadata' must be a JSON object")
        return cls.of(raw["artefact"], raw["version"], components, **metadata)

    @property
    def digest(self) -> str:
        return canonical.digest(self.as_dict())

    def by_key(self) -> dict[str, Component]:
        return {c.key: c for c in self.components}

    def to_cyclonedx(self) -> dict[str, Any]:
        """Export to the subset of CycloneDX 1.5 that this data supports.

        Deliberately partial. Emitting a document that validates against the
        schema while carrying invented fields is worse than emitting a small
        honest one.
        """
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "application",
                    "name": self.artefact,
                    "version": self.version,
                }
            },
            "components": [
                {
                    "type": "library" if c.kind == "library" else "application",
                    "name": c.name,
                    "version": c.version,
                    **({"licenses": [{"license": {"id": c.licence}}]} if c.licence else {}),
                    **({"supplier": {"name": c.supplier}} if c.supplier else {}),
                    **(
                        {"hashes": [{"alg": "SHA-256", "content": c.digest.split(":")[-1]}]}
                        if c.digest.startswith("sha256:")
                        else {}
                    ),
                }
                for c in self.components
            ],
        }


@dataclass(frozen=True, slots=True)
class SbomDiff:
    """What changed between two bills of materials."""

    added: tuple[Component, ...]
    removed: tuple[Component, ...]
    #: ``(before, after)`` for components present in both at different versions.
    changed: tuple[tuple[Component, Component], ...]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    @property
    def licence_changes(self) -> tuple[tuple[Component, Component], ...]:
        """Version bumps that also changed licence.

        The quiet one. A dependency that relicenses at a patch version is
        invisible in a changelog and visible here.
        """
        return tuple((a, b) for a, b in self.changed if a.licence != b.licence)

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": [c.as_dict() for c in self.added],
            "removed": [c.as_dict() for c in self.removed],
            "changed": [
                {"before": a.as_dict(), "after": b.as_dict()} for a, b in self.changed
            ],
        }

    def summary(self) -> str:
        return (
            f"{len(self.added)} added, {len(self.removed)} removed, "
            f"{len(self.changed)} changed"
            + (
                f", {len(self.licence_changes)} licence change(s)"
                if self.licence_changes
                else ""
            )
        )


def diff(before: SBOM, after: SBOM) -> SbomDiff:
    """Component-level diff, keyed on kind and name rather than version."""
    a, b = before.by_key(), after.by_key()
    added = tuple(b[k] for k in sorted(set(b) - set(a)))
    removed = tuple(a[k] for k in sorted(set(a) - set(b)))
    changed = tuple(
        (a[k], b[k]) for k in sorted(set(a) & set(b)) if a[k].version != b[k].version
    )
    return SbomDiff(added=added, removed=removed, changed=changed)
