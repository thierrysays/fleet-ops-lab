"""What gets shipped, and the manifest that describes it.

An artefact is opaque bytes: a firmware image, a container layer, a tarball, a
model file. The manifest is the part with opinions — it binds the bytes to a
digest, a version, and a bill of materials, and it is the manifest that gets
signed.

Binding rather than accompanying is the distinction that matters. A manifest
that merely travels alongside an image can be paired with a different image. A
manifest that carries the image's digest cannot, and the node checks.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import canonical
from .errors import DigestMismatch, SbomMissing, SignatureInvalid
from .sbom import SBOM

SCHEMA = "fleet-ops/manifest/v1"


@dataclass(frozen=True, slots=True)
class Artefact:
    """Bytes plus the name they travel under."""

    name: str
    version: str
    payload: bytes

    @property
    def digest(self) -> str:
        return canonical.digest_bytes(self.payload)

    @property
    def size(self) -> int:
        return len(self.payload)


@dataclass(frozen=True, slots=True)
class Manifest:
    """The signed description of one artefact.

    ``requires_sbom`` defaults to true, and a manifest without one cannot be
    constructed. That is a refusal, not a warning: an image nobody can produce a
    component list for is an image nobody can answer a vulnerability question
    about, and the question always arrives on a deadline.
    """

    name: str
    version: str
    artefact_digest: str
    size: int
    sbom_digest: str
    #: Digest over the inputs that produced the build — sources, toolchain,
    #: flags. Two builds sharing this and differing in ``artefact_digest`` are
    #: the definition of a non-reproducible build.
    build_inputs_digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    signatures: tuple[dict[str, str], ...] = ()

    @classmethod
    def describing(
        cls,
        artefact: Artefact,
        sbom: SBOM | None,
        build_inputs_digest: str = "",
        **metadata: Any,
    ) -> Manifest:
        if sbom is None:
            raise SbomMissing(
                f"{artefact.name} {artefact.version} has no bill of materials; "
                "an artefact that cannot be enumerated cannot be deployed"
            )
        return cls(
            name=artefact.name,
            version=artefact.version,
            artefact_digest=artefact.digest,
            size=artefact.size,
            sbom_digest=sbom.digest,
            build_inputs_digest=build_inputs_digest,
            metadata=dict(metadata),
        )

    # ------------------------------------------------------------------ signing
    def to_be_signed(self) -> dict[str, Any]:
        """The bytes a signature covers — everything except the signatures."""
        return {
            "schema": SCHEMA,
            "name": self.name,
            "version": self.version,
            "artefact_digest": self.artefact_digest,
            "size": self.size,
            "sbom_digest": self.sbom_digest,
            "build_inputs_digest": self.build_inputs_digest,
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        return canonical.digest(self.to_be_signed())

    def signed_by(self, key_id: str, signature: str) -> Manifest:
        return Manifest(
            name=self.name,
            version=self.version,
            artefact_digest=self.artefact_digest,
            size=self.size,
            sbom_digest=self.sbom_digest,
            build_inputs_digest=self.build_inputs_digest,
            metadata=dict(self.metadata),
            signatures=self.signatures + ({"key_id": key_id, "signature": signature},),
        )

    # ----------------------------------------------------------------- checking
    def verify_artefact(self, artefact: Artefact) -> None:
        """Bind manifest to bytes. Raises :class:`~.errors.DigestMismatch`.

        Checked on the node after transfer, not on the builder before it. The
        interesting corruption happens in between.
        """
        actual = artefact.digest
        if actual != self.artefact_digest:
            raise DigestMismatch(self.artefact_digest, actual, self.name)
        if artefact.size != self.size:
            raise DigestMismatch(
                f"{self.size} bytes", f"{artefact.size} bytes", self.name
            )

    def verify_signature(
        self, verifier: Callable[[str, str, bytes], bool] | None, quorum: int = 1
    ) -> None:
        """Check signatures with a caller-supplied verifier.

        No cryptography is bundled. Whoever runs the fleet already has a key
        story — a TPM, a cloud KMS, an HSM, a plain Ed25519 key in a file — and
        this package will not choose one for them. What it does insist on is that
        an *absent* verifier with a required quorum is a failure, never a skip.
        """
        if quorum <= 0:
            return
        if verifier is None:
            raise SignatureInvalid(
                f"{self.name} requires {quorum} signature(s) but no verifier was "
                "supplied; a check that cannot run is a check that failed"
            )
        payload = canonical.canonical_json(self.to_be_signed()).encode("utf-8")
        good = {
            s["key_id"]
            for s in self.signatures
            if verifier(s["key_id"], s["signature"], payload)
        }
        if len(good) < quorum:
            raise SignatureInvalid(
                f"{self.name}: {len(good)} valid signature(s) from distinct keys, "
                f"{quorum} required"
            )

    def as_dict(self) -> dict[str, Any]:
        return {**self.to_be_signed(), "signatures": [dict(s) for s in self.signatures]}
