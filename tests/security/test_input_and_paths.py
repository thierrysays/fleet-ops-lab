"""Security: what the package does with input and paths it did not create.

An update system is the highest-value target in a fleet. It writes to every
node, and whoever controls what it installs controls everything downstream. The
properties under test:

* untrusted input can make it **refuse**, and cannot make it do anything else;
* a path component from a plan file cannot escape the node's directory;
* a check that cannot run counts as failed, never as passed;
* nothing in the package executes what it reads.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fleet_ops.artefact import Manifest
from fleet_ops.errors import SignatureInvalid, TransportFailure
from fleet_ops.sbom import SBOM, Component
from fleet_ops.transport import InMemoryTransport, LocalDirTransport
from fleet_ops.update import update_node
from tests.conftest import release, running_node

SRC = Path(__file__).resolve().parents[2] / "src" / "fleet_ops"


# ------------------------------------------------------------ code execution
def test_the_package_never_evaluates_what_it_reads():
    """No eval, exec, pickle or shell anywhere in the package.

    An update system that can be talked into executing part of its input has
    skipped straight to the outcome the attacker wanted.
    """
    forbidden = re.compile(
        r"\b(eval|exec|compile)\s*\(|\bpickle\b|\bmarshal\b|\bshelve\b"
        r"|os\.system|subprocess\.|__import__\s*\("
    )
    offenders = [f.name for f in SRC.rglob("*.py") if forbidden.search(f.read_text())]
    assert offenders == []


def test_the_package_never_executes_a_downloaded_artefact():
    """The payload is opaque bytes here. Installing it is the deployment's job.

    Deliberate: a model that stages, verifies and hands over (rather than one
    that also runs what it staged) keeps the dangerous step where the operator
    can see it.
    """
    sources = " ".join(f.read_text() for f in SRC.rglob("*.py"))
    for runner in ("os.exec", "os.spawn", "runpy", "importlib.import_module"):
        assert runner not in sources


# ------------------------------------------------------------- path handling
@pytest.mark.parametrize("node_id", ["../escape", "..", "a/b", "../../etc"])
def test_a_node_id_cannot_escape_the_transport_root(tmp_path, node_id):
    t = LocalDirTransport(tmp_path)
    with pytest.raises(TransportFailure):
        t.put(node_id, "image.bin", b"x")


@pytest.mark.parametrize("name", ["../../etc/passwd", "a/b", ".."])
def test_a_blob_name_cannot_escape_the_node_directory(tmp_path, name):
    t = LocalDirTransport(tmp_path)
    with pytest.raises(TransportFailure):
        t.put("n1", name, b"x")
    with pytest.raises(TransportFailure):
        t.get("n1", name)


def test_a_partial_write_never_replaces_a_good_blob(tmp_path):
    """Write to a temporary name, rename into place.

    A process killed mid-write must leave the previous image intact rather than
    a truncated one, on a node, that difference is a brick.
    """
    t = LocalDirTransport(tmp_path)
    t.put("n1", "image.bin", b"good-image")
    assert list((tmp_path / "n1").glob("*.partial")) == []
    assert t.get("n1", "image.bin") == b"good-image"


def test_reading_a_blob_that_was_never_delivered_raises(tmp_path):
    with pytest.raises(TransportFailure):
        LocalDirTransport(tmp_path).get("n1", "image.bin")


# ------------------------------------------------------------- SBOM as input
def test_an_sbom_with_an_unknown_schema_is_refused():
    with pytest.raises(ValueError):
        SBOM.from_dict({"schema": "fleet-ops/sbom/v2", "artefact": "a", "version": "1"})


def test_an_sbom_that_is_not_an_object_is_refused():
    for bad in ([], "sbom", 7, None):
        with pytest.raises(ValueError):
            SBOM.from_dict(bad)


def test_an_unknown_component_field_is_refused_not_dropped():
    """Silently ignoring a field produces a diff that says nothing changed."""
    raw = SBOM.of("a", "1", [Component("zlib", "1.3.1")]).as_dict()
    raw["components"][0]["provenance_url"] = "http://example.invalid"
    with pytest.raises(ValueError) as excinfo:
        SBOM.from_dict(raw)
    assert "provenance_url" in str(excinfo.value)


def test_a_component_missing_its_name_or_version_is_refused():
    raw = SBOM.of("a", "1", [Component("zlib", "1.3.1")]).as_dict()
    del raw["components"][0]["version"]
    with pytest.raises(ValueError):
        SBOM.from_dict(raw)


def test_malformed_sbom_structure_is_refused_rather_than_coerced():
    base = SBOM.of("a", "1", [Component("zlib", "1.3.1")]).as_dict()
    for mutate in (
        lambda r: r.update(components="not-a-list"),
        lambda r: r.update(components=["not-an-object"]),
        lambda r: r.update(metadata=[1, 2, 3]),
        lambda r: r.update(version=7),
    ):
        raw = json.loads(json.dumps(base))
        mutate(raw)
        with pytest.raises(ValueError):
            SBOM.from_dict(raw)


# --------------------------------------------------- checks that cannot run
def test_a_verifier_that_raises_is_treated_as_a_refusal_not_a_crash():
    """An unreachable KMS must refuse the update, not kill the rollout.

    A crashed rollout is the one that gets retried with the check switched off.
    """
    def exploding_verifier(key_id, signature, payload):
        raise ConnectionError("KMS unreachable")

    artefact, manifest = release()
    signed = manifest.signed_by("k1", "sig")
    with pytest.raises(SignatureInvalid):
        signed.verify_signature(exploding_verifier, quorum=1)


def test_a_verifier_that_raises_stops_the_node_update_cleanly():
    def exploding_verifier(key_id, signature, payload):
        raise ConnectionError("KMS unreachable")

    node = running_node()
    artefact, manifest = release()
    outcome = update_node(node, artefact, manifest.signed_by("k1", "sig"),
                          InMemoryTransport(), probe=lambda n: True,
                          verifier=exploding_verifier, signature_quorum=1)
    assert outcome.code == "signature-invalid"
    assert node.running_version == "1.0.0"


def test_a_probe_that_raises_is_a_failed_probe_not_a_crashed_rollout():
    def exploding_probe(node):
        raise TimeoutError("no route to host")

    node = running_node()
    artefact, manifest = release()
    outcome = update_node(node, artefact, manifest, InMemoryTransport(),
                          probe=exploding_probe)
    assert outcome.rolled_back is True
    assert node.running_version == "1.0.0"


# ------------------------------------------------------------- digest safety
def test_a_digest_prefix_is_not_accepted_for_the_whole_digest():
    """Comparison is on the full string. A truncated digest is a wrong digest."""
    artefact, manifest = release()
    truncated = Manifest(
        name=manifest.name, version=manifest.version,
        artefact_digest=manifest.artefact_digest[:20],
        size=manifest.size, sbom_digest=manifest.sbom_digest,
    )
    from fleet_ops.errors import DigestMismatch

    with pytest.raises(DigestMismatch):
        truncated.verify_artefact(artefact)


def test_size_is_checked_as_well_as_digest():
    """Belt and braces: a size mismatch is refused even before the digest could
    plausibly collide."""
    from fleet_ops.errors import DigestMismatch

    artefact, manifest = release()
    same_digest_wrong_size = Manifest(
        name=manifest.name, version=manifest.version,
        artefact_digest=manifest.artefact_digest, size=manifest.size + 1,
        sbom_digest=manifest.sbom_digest,
    )
    with pytest.raises(DigestMismatch):
        same_digest_wrong_size.verify_artefact(artefact)


# -------------------------------------------------------------- disclosure
def test_a_rollout_report_carries_no_environment_and_no_payloads(tmp_path, fleet):
    """The report is shared. It must not carry the build machine or the image."""
    from fleet_ops.rollout import Rollout, RolloutPlan, Wave

    nodes = fleet(3)
    artefact, manifest = release(payload=b"SECRET-PAYLOAD-BYTES" * 10)
    plan = RolloutPlan("agent", "2.0.0", (Wave("all", tuple(nodes), 1.0),))
    report = Rollout(nodes, InMemoryTransport(),
                     {n: (lambda x: True) for n in nodes}).run(plan, artefact, manifest)
    serialised = json.dumps(report.as_dict())
    assert "SECRET-PAYLOAD-BYTES" not in serialised
    assert "/home/" not in serialised
    for leaky in ("TOKEN", "SECRET_KEY", "PASSWORD", "AWS_", "API_KEY"):
        assert leaky not in serialised
