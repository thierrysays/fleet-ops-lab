# ADR 0003 — No signing, no key store, no crypto dependency

**Status:** accepted · 2026-08-21

## Context

An update system that does not verify signatures is a remote code execution
service. So the temptation is to bundle a signing scheme — pick Ed25519, ship a
key format, done.

Every fleet that will ever run this already has a key story: a TPM on the
device, a KMS in the cloud, an HSM in a rack, a hardware secure element, or a
key in a file because it is a bench rig. None of them will adopt a second one
because a Python package brought it.

## Decision

`Manifest.verify_signature` takes a `(key_id, signature, payload) -> bool`
callable. The package canonicalises the to-be-signed structure and hands over the
bytes. It holds no keys, implements no algorithm, and has no cryptographic
dependency.

## Cost

The most security-critical check in the package is implemented by the caller,
and a caller who writes `lambda *_: True` has a system that verifies nothing
while appearing to. Nothing here can prevent that.

What is prevented is the *accidental* version: `verify_signature(None, quorum=1)`
raises rather than passing. A check that cannot run is a failed check, and the
absent-verifier case is the one that happens by mistake rather than by intent.

## Consequence

The to-be-signed structure — every manifest field except the signatures — is
frozen. It binds the artefact digest and the SBOM digest, so a signature cannot
be transplanted onto a different image or a different bill of materials.
`test_a_signature_cannot_be_transplanted_between_manifests` pins it.
