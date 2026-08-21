"""Binding a manifest to bytes, and to a key."""

import pytest

from fleet_ops.artefact import Artefact, Manifest
from fleet_ops.errors import DigestMismatch, SbomMissing, SignatureInvalid
from fleet_ops.sbom import SBOM, Component


def _sbom(version="1.0.0"):
    return SBOM.of("agent", version, [Component("zlib", "1.3.1")])


def _artefact(payload=b"payload-bytes", version="1.0.0"):
    return Artefact("agent", version, payload)


def test_an_artefact_without_a_bill_of_materials_cannot_be_described():
    with pytest.raises(SbomMissing):
        Manifest.describing(_artefact(), None)


def test_bytes_that_do_not_match_the_manifest_are_refused():
    manifest = Manifest.describing(_artefact(), _sbom())
    with pytest.raises(DigestMismatch):
        manifest.verify_artefact(_artefact(b"different-bytes"))


def test_a_truncated_transfer_is_caught_even_when_it_looks_successful():
    original = _artefact(b"x" * 1024)
    manifest = Manifest.describing(original, _sbom())
    with pytest.raises(DigestMismatch):
        manifest.verify_artefact(Artefact("agent", "1.0.0", b"x" * 512))


def test_a_required_signature_with_no_verifier_is_a_failure_not_a_skip():
    manifest = Manifest.describing(_artefact(), _sbom())
    with pytest.raises(SignatureInvalid):
        manifest.verify_signature(None, quorum=1)


def test_an_unsigned_manifest_fails_a_quorum_of_one():
    manifest = Manifest.describing(_artefact(), _sbom())
    with pytest.raises(SignatureInvalid):
        manifest.verify_signature(lambda k, s, p: True, quorum=1)


def test_a_signature_cannot_be_transplanted_between_manifests():
    # The verifier binds the signature to the payload it covers, which is what
    # makes the transplant fail. A verifier that ignores the payload would pass
    # this, which is exactly the mistake being pinned.
    good = Manifest.describing(_artefact(b"good-build"), _sbom())
    evil = Manifest.describing(_artefact(b"evil-build"), _sbom())
    signature = good.digest

    def verifier(key_id: str, sig: str, payload: bytes) -> bool:
        from fleet_ops import canonical

        return sig == canonical.digest(__import__("json").loads(payload.decode()))

    assert good.signed_by("k1", signature).verify_signature(verifier, quorum=1) is None
    with pytest.raises(SignatureInvalid):
        evil.signed_by("k1", signature).verify_signature(verifier, quorum=1)


def test_two_signatures_from_one_key_do_not_make_a_quorum_of_two():
    manifest = Manifest.describing(_artefact(), _sbom())
    twice = manifest.signed_by("k1", "sig").signed_by("k1", "sig")
    with pytest.raises(SignatureInvalid):
        twice.verify_signature(lambda k, s, p: True, quorum=2)


def test_a_quorum_of_zero_skips_the_check_deliberately_and_visibly():
    # Unsigned deployment is a real choice for a bench rig. It has to be an
    # explicit zero, not the accident of forgetting to pass a verifier.
    Manifest.describing(_artefact(), _sbom()).verify_signature(None, quorum=0)


def test_the_signature_covers_the_sbom_digest():
    a = Manifest.describing(_artefact(), SBOM.of("agent", "1.0.0", [Component("zlib", "1.3.1")]))
    b = Manifest.describing(_artefact(), SBOM.of("agent", "1.0.0", [Component("zlib", "1.3.2")]))
    assert a.digest != b.digest
