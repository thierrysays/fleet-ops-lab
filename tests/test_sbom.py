"""The bill of materials, and the diff that is the reason to have one."""

import pytest

from fleet_ops.sbom import SBOM, SCHEMA, Component, diff


def _sbom(version, components):
    return SBOM.of("agent", version, components)


def test_the_digest_does_not_depend_on_scan_order():
    a = _sbom("1.0", [Component("zlib", "1.3.1"), Component("curl", "8.7.1")])
    b = _sbom("1.0", [Component("curl", "8.7.1"), Component("zlib", "1.3.1")])
    assert a.digest == b.digest


def test_a_version_change_changes_the_digest():
    a = _sbom("1.0", [Component("zlib", "1.3.1")])
    b = _sbom("1.0", [Component("zlib", "1.3.2")])
    assert a.digest != b.digest


def test_a_new_component_is_reported_as_added():
    before = _sbom("1.0", [Component("zlib", "1.3.1")])
    after = _sbom("2.0", [Component("zlib", "1.3.1"), Component("libssh", "0.10.6")])
    d = diff(before, after)
    assert [c.name for c in d.added] == ["libssh"]
    assert d.removed == ()
    assert d.is_empty is False


def test_a_dropped_component_is_reported_as_removed():
    before = _sbom("1.0", [Component("zlib", "1.3.1"), Component("libssh", "0.10.6")])
    after = _sbom("2.0", [Component("zlib", "1.3.1")])
    assert [c.name for c in diff(before, after).removed] == ["libssh"]


def test_the_same_name_in_a_different_kind_is_a_different_component():
    # A library called 'foo' and a model called 'foo' are not the same thing,
    # and collapsing them is how a model swap hides inside a dependency bump.
    before = _sbom("1.0", [Component("foo", "1.0", kind="library")])
    after = _sbom("2.0", [Component("foo", "1.0", kind="model")])
    d = diff(before, after)
    assert len(d.added) == 1 and len(d.removed) == 1
    assert d.changed == ()


def test_a_relicensed_dependency_is_surfaced_separately():
    # The quiet one: a patch bump that also changes licence terms is invisible
    # in a changelog and material to whoever ships the product.
    before = _sbom("1.0", [Component("thing", "2.1.0", licence="MIT")])
    after = _sbom("2.0", [Component("thing", "2.1.1", licence="BUSL-1.1")])
    d = diff(before, after)
    assert len(d.changed) == 1
    assert len(d.licence_changes) == 1
    assert "1 licence change" in d.summary()


def test_two_identical_bills_produce_an_empty_diff():
    a = _sbom("1.0", [Component("zlib", "1.3.1")])
    assert diff(a, a).is_empty is True


def test_an_unknown_schema_is_refused_on_load():
    with pytest.raises(ValueError):
        SBOM.from_dict({"schema": "fleet-ops/sbom/v2", "artefact": "a", "version": "1"})


def test_a_round_trip_through_json_preserves_the_digest():
    a = _sbom("1.0", [Component("zlib", "1.3.1", licence="Zlib", digest="sha256:" + "a" * 64)])
    assert SBOM.from_dict(a.as_dict()).digest == a.digest
    assert a.as_dict()["schema"] == SCHEMA


def test_the_cyclonedx_export_carries_only_fields_that_exist():
    bare = _sbom("1.0", [Component("zlib", "1.3.1")])
    exported = bare.to_cyclonedx()["components"][0]
    assert "licenses" not in exported  # no licence recorded, none invented
    assert "hashes" not in exported
