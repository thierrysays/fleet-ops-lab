# Technical reference

What each module is, what it refuses, and the exact shape of every artefact.
[ARCHITECTURE.md](ARCHITECTURE.md) argues *why*; this is the file to keep open
while writing code against the package.

Package `fleet_ops`, distribution `fleet-ops-lab`, console script `fol`.

---

## Foundations

### `canonical.py`

`canonical_json(payload)`, `digest(payload)`, `digest_bytes(raw)`. Sorted keys,
`(",", ":")` separators, non-finite floats refused. Every manifest digest, SBOM
digest and reproducibility comparison goes through here.

### `clock.py`

`Clock` protocol with `SystemClock` and `ManualClock`. Confirmation deadlines are
the reason it exists: a rollback window measured against the real clock is a
window that has never been tested.

### `errors.py`

| Exception | `code` | Raised when |
|---|---|---|
| `FleetOpsError` | `fleet-ops-error` | base class |
| `DigestMismatch` | `digest-mismatch` | the bytes that arrived are not the bytes described |
| `SignatureInvalid` | `signature-invalid` | unsigned, under-signed, untrusted key, or no verifier supplied |
| `SbomMissing` | `sbom-missing` | an artefact arrived without a bill of materials |
| `SlotUnavailable` | `slot-unavailable` | staging now would destroy the rollback target |
| `NotStaged` | `not-staged` | activation attempted with nothing verified |
| `TransportFailure` | `transport-failure` | the bytes did not arrive, or a path component was unsafe |
| `RolloutHalted` | `rollout-halted` | a wave exceeded its failure budget |

---

## The release

### `sbom.py`

`Component(name, version, kind, licence, digest, supplier)` with a derived
`key` of `kind:name` — a library and a model of the same name are different
components, and collapsing them hides a model swap inside a dependency bump.

`SBOM.of(artefact, version, components, **metadata)` sorts at construction. An
SBOM whose digest depends on the order the scanner walked the filesystem is not
a digest of anything.

`SBOM.from_dict(raw)` refuses: a non-object, an unknown schema, a non-string
artefact or version, a non-list `components`, a non-object component, an unknown
component field, a component missing `name` or `version`, non-object `metadata`.
An SBOM that cannot be parsed is not an empty SBOM.

`SBOM.to_cyclonedx()` exports the subset of CycloneDX 1.5 this data supports.
Deliberately partial: a document that validates while carrying invented fields is
worse than a small honest one.

`diff(before, after) -> SbomDiff` with `added`, `removed`, `changed`,
`licence_changes`, `is_empty`, `summary()`.

### `artefact.py`

`Artefact(name, version, payload)` — opaque bytes, with derived `digest` and
`size`.

`Manifest.describing(artefact, sbom, build_inputs_digest="", **metadata)` — the
signed description. Raises `SbomMissing` if the SBOM is `None`.

| Method | Does | Refuses |
|---|---|---|
| `to_be_signed()` | the structure a signature covers — everything but the signatures | — |
| `digest` | `sha256:…` over `to_be_signed()` | — |
| `signed_by(key_id, signature)` | returns a new manifest with one more signature | — |
| `verify_artefact(artefact)` | binds manifest to bytes | digest or size mismatch |
| `verify_signature(verifier, quorum)` | counts valid signatures from **distinct** keys | absent verifier with quorum ≥ 1; too few distinct keys; a verifier that raises counts as a refusal |

`build_inputs_digest` is a digest over sources, toolchain and flags. Two builds
sharing it and differing in `artefact_digest` are the definition of a
non-reproducible build.

---

## The node

### `node.py`

`SlotState`: `EMPTY` → `STAGED` → `VERIFIED` → `PENDING` → `ACTIVE`, or
`PENDING` → `FAILED` on revert.

| Method | Does | Refuses |
|---|---|---|
| `stage(version, digest)` | writes into the spare slot | while another slot is `PENDING` |
| `mark_verified(slot)` | promotes a staged slot | a slot that is not `STAGED` |
| `activate()` | sets `PENDING`, starts the deadline | nothing verified to activate |
| `confirm()` | commits; clears the deadline | nothing pending |
| `rollback(reason)` | marks the pending slot `FAILED`, restores the other | returns `None` if nothing pending |
| `tick()` | reverts if the deadline passed; returns whether it did | — |
| `state()` | node id, running version, slot states, `awaiting_confirmation` | — |

`history` records every transition with its reason, in order.

`tick()` takes no arguments and consults nothing: a node that can only roll back
when told to is a node that cannot roll back.

### `transport.py`

```python
class Transport(Protocol):
    def put(self, node_id: str, name: str, data: bytes) -> None: ...
    def get(self, node_id: str, name: str) -> bytes: ...
    def has(self, node_id: str, name: str) -> bool: ...
    def delete(self, node_id: str, name: str) -> None: ...
```

`InMemoryTransport` — the reference implementation.
`LocalDirTransport(root)` — a directory per node; refuses `/` and `..` in either
component; writes to `*.partial` and renames, so a process killed mid-write
leaves the previous blob intact.
`FlakyTransport(inner, fail_every, truncate_every, fail_nodes, truncate_nodes)` —
drops *and* truncates, because a digest check tested only against total failure
has not been tested.

---

## The update

### `update.py`

`update_node(node, artefact, manifest, transport, probe, verifier,
signature_quorum) -> UpdateOutcome`

The order is load-bearing:

1. transfer, and read back
2. **verify the signature** on the manifest
3. **verify the digest** of what was read back, against the now-authentic manifest
4. stage into the spare slot
5. activate provisionally
6. probe — pass confirms, fail or absent or raising rolls back

`UpdateOutcome` carries `node_id`, `ok`, `code`, `detail`, `from_version`,
`to_version`, `rolled_back`. Ordinary failures never raise.

### `rollout.py`

`Wave(name, node_ids, failure_budget)` with `tolerated()` = `int(len × budget)` —
truncating, so a five-node wave at 10 % tolerates nothing.

`RolloutPlan(artefact_name, version, waves)`, plus
`RolloutPlan.canary_then_rest(...)` for the default shape.

`Rollout(nodes, transport, probes, verifier, signature_quorum).run(plan,
artefact, manifest) -> RolloutReport`. `run` takes no override parameter, and
that absence is the control.

`RolloutReport`: `updated`, `failed`, `rolled_back`, `untouched`, `by_code()`,
`halted_at`, `halt_reason`, `outcomes`, and `as_dict()` producing
`fleet-ops/rollout-report/v1`.

### `reproducible.py`

`digest_tree(root, exclude=())` → sorted map of POSIX relative path to digest.
`compare_builds(a, b) -> ReproVerdict` with `matched`, `differing`, `only_in_a`,
`only_in_b`, `reproducible`, `summary`.

`COMMON_NON_DETERMINISM` lists the usual causes, for the person reading the
first failing verdict.

---

## Artefacts

| Schema | Produced by | Carries |
|---|---|---|
| `fleet-ops/manifest/v1` | `Manifest.as_dict()` | name, version, artefact digest, size, SBOM digest, build-inputs digest, metadata, signatures |
| `fleet-ops/sbom/v1` | `SBOM.as_dict()` | artefact, version, sorted components, metadata |
| `fleet-ops/rollout-report/v1` | `RolloutReport.as_dict()` | plan, counts, `halted_at`, `halt_reason`, `by_code`, per-node outcomes |
| `fleet-ops/repro-verdict/v1` | `ReproVerdict.as_dict()` | reproducible, matched, differing, only-in-a, only-in-b, summary |

All four identifiers are frozen. A breaking change gets `/v2`.

---

## Command line

| Command | Does | Exit codes |
|---|---|---|
| `fol demo` | runs the pinned scenario; `--out` writes the report | 0 |
| `fol sbom-diff a b` | prints the diff; `--json`; `--fail-on-change` for CI | 0, or 1 with `--fail-on-change` when anything changed |
| `fol repro a b` | compares two build trees | 0 if identical, 1 otherwise |

Any `FleetOpsError` reaching the top prints `code: message` on stderr and exits 2.

---

## Extending

**A new transport**: implement four methods; raise `TransportFailure` for
anything that did not arrive; refuse unsafe path components rather than
resolving them.

**A new failure mode**: a new exception in `errors.py` with a stable code, a row
in this table, and a row in [CONTROL_MAP.md](CONTROL_MAP.md) with its test.

**A new artefact**: new schema identifier, new version, never an edit.
