# Functional specification

What this package does, for whom, and what counts as it working. Written so that
someone who will never read the source can tell whether a claim made about an
update process is true.

The technical counterpart is [TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md).
Every requirement below is discharged by a named test in
`tests/functional/test_requirements.py`.

---

## Purpose

Model the update of a fleet of constrained nodes such that **a bad update is
survivable without anybody being present**, and **a bad rollout stops before it
reaches everything**.

Explicitly **not** in scope: device enrolment, inventory, telemetry, dashboards,
signing, or running the artefact once it is installed.

## Actors

| Actor | Does | Cannot |
|---|---|---|
| **Release engineer** | Builds the artefact, produces the SBOM, describes the manifest | Describe an artefact without a bill of materials |
| **Signing authority** | Signs manifests with keys this package never sees | Be substituted by an absent verifier |
| **Rollout operator** | Writes the plan: waves, order, budgets | Continue a rollout past a halt |
| **Node** | Stages, verifies, activates provisionally, confirms or reverts | Keep an update it could not confirm; overwrite its own rollback target |
| **Health probe** | Answers one question about one node | Be absent and treated as a pass |
| **Auditor** | Reads the rollout report and the node history | Be required to trust the node's own account alone, see R-3 |

The separation that matters: **the party that ships an update is never the party
that decides it worked.** The probe is supplied by the deployment; the decision
to commit is taken by the node against a deadline it holds itself.

## Preconditions

A node may activate an image only if all of these hold. Each failure is a
refusal with a code, not a warning.

1. The bytes arrived. A dropped transfer is ordinary and is not an incident.
2. The manifest verifies at the required signature quorum, with a verifier the
   caller supplied.
3. The bytes read back from the node digest to the value the manifest binds, and
   are the size it declares.
4. There is a spare slot: meaning no other slot is pending confirmation.
5. The staged slot has been marked verified. An unverified image is never booted.

---

## Functional requirements

### FR-1, An update is provisional until the node confirms

Activation sets a slot to `PENDING` and starts a confirmation window. It does not
commit.

*Verified by* `test_fr1_an_update_is_provisional_until_the_node_confirms`.

### FR-2, A node that never confirms reverts on its own timer

`tick()` reverts an unconfirmed slot once the window expires, consulting no
server and requiring no operator.

*Verified by* `test_fr2_a_node_that_never_confirms_reverts_on_its_own_timer`.

### FR-3, Bytes that do not match the manifest never reach a slot

The digest is checked on the node, against what was read back after transfer.

*Verified by* `test_fr3_bytes_that_do_not_match_the_manifest_never_reach_a_slot`.

### FR-4, A missing health probe is a failed health probe

An absent probe rolls the node back. A node nobody can ask about does not keep a
change on the strength of silence.

*Verified by* `test_fr4_a_missing_health_probe_is_a_failed_probe`.

### FR-5, A required signature with no verifier is a failure

`verify_signature(None, quorum>=1)` raises. A check that cannot run is a check
that failed.

*Verified by* `test_fr5_a_required_signature_with_no_verifier_is_a_failure`.

### FR-6, An artefact without a bill of materials cannot be described

`Manifest.describing(artefact, None)` raises `SbomMissing`.

*Verified by* `test_fr6_an_artefact_without_a_bill_of_materials_cannot_be_described`.

### FR-7, A wave beyond its budget halts the rollout

Subsequent waves do not run. Untouched nodes stay on the version that was
working. There is no parameter that continues.

*Verified by* `test_fr7_a_wave_beyond_its_budget_halts_the_rollout` and
`test_fr7_there_is_no_parameter_that_continues_past_a_halt`.

### FR-8, Staging is refused while a slot is pending

The pending slot's counterpart is the rollback target; overwriting it is how a
pair of bad updates bricks a node.

*Verified by* `test_fr8_staging_is_refused_while_a_slot_is_pending`.

### FR-9, Every outcome carries a stable code

`updated`, `transport-failure`, `digest-mismatch`, `signature-invalid`,
`slot-unavailable`, `not-staged`, `health-probe-failed`.

*Verified by* `test_fr9_the_report_groups_outcomes_by_cause`.

### FR-10, An SBOM diff names what appeared, disappeared and changed

Components are keyed on `kind:name`. Licence changes at a version bump are
surfaced separately.

*Verified by* `test_fr10_an_sbom_diff_names_what_appeared` and
`test_fr10_a_relicensed_dependency_is_surfaced_separately`.

### FR-11, The SBOM diff can gate a pipeline

`fol sbom-diff a b --fail-on-change` exits 1 when anything changed, 0 otherwise.

*Verified by* `test_fr11_the_sbom_diff_can_gate_a_pipeline`.

### FR-12, A non-reproducible build names the files that differ

Not a verdict, a list of paths. Matching files are not named.

*Verified by* `test_fr12_a_non_reproducible_build_names_the_files_that_differ`.

### FR-13, The demo scenario holds its pinned counts

`fol demo` always reports 2 rolled back, 6 untouched, halted in the pilot wave.

*Verified by* `test_fr13_the_demo_scenario_holds_its_pinned_counts`.

### FR-14, A node records every transition it made

`history` carries an ordered list of events with their reasons.

*Verified by* `test_fr14_a_node_records_every_transition_it_made` and
`test_fr14_the_rollback_reason_is_carried_not_summarised`.

---

## Acceptance criteria

```
make smoke      # imports, CLI answers, demo runs
make test       # every tier green
make demo       # 2 rolled back, 6 untouched, halted in 'pilot'
make qa         # lint, strict types, SAST, advisories, coverage
```

`fol demo` printing anything other than **2 rolled back** and **6 untouched** is
a regression, not a new baseline.

## Non-functional requirements

| # | Requirement | How it is met |
|---|---|---|
| NFR-1 | Installs anywhere | No runtime dependencies |
| NFR-2 | Rollback deadlines are testable | Injectable clock; `ManualClock` in every timing test |
| NFR-3 | Failures are machine-readable | One exception per mode, each with a stable `code` |
| NFR-4 | The rollout report is shareable | Codes and counts, no payloads, no environment |
| NFR-5 | Transport-agnostic | Four methods; in-memory, local directory, and a deliberately flaky wrapper |
| NFR-6 | Crypto-agnostic | Signature verification is a caller-supplied callable |

## Out of scope, deliberately

- **Signing.** → [ADR 0003](adr/0003-no-bundled-cryptography.md).
- **Anti-rollback / downgrade protection.** No monotonic version counter.
  Residual risk R-1 in [THREAT_MODEL.md](THREAT_MODEL.md).
- **Attestation.** A node's reported version is its own account of itself. R-3.
- **Resumable transfers.** The interface has no vocabulary for a partial
  transfer; a 400 MB image over cellular needs one. See
  [PORTING.md](PORTING.md).
- **Coordinated groups.** Nodes that must update together are not modelled.
