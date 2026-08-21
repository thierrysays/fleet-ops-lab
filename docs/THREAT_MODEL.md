# Threat model

Who this defends against, who it does not, and where the line is. Every claim is
either pinned by a test in `tests/security/` and `tests/pentest/`, or listed as
residual.

An update system is the highest-value target in a fleet: it writes to every node,
and whoever controls what it installs controls everything downstream.

---

## Assets

| Asset | Why it is worth attacking |
|---|---|
| The **artefact** | It is the code that will run on every node |
| The **manifest** | It says which bytes are legitimate |
| The **signing keys** | They are not here — but whoever holds them admits anything |
| The **rollback target** | Destroying it turns a recoverable node into a brick |
| The **rollout plan** | The budgets decide how far a bad update travels |
| The **SBOM** | It is the answer to "what is in the thing you shipped" |

## Adversaries

| # | Adversary | Capability assumed |
|---|---|---|
| **A1** | A compromised build pipeline | Produces any artefact and any manifest. Cannot sign, unless no verifier was configured |
| **A2** | A network position | Drops, delays, truncates, substitutes or replays anything in transit. Cannot forge a signature |
| **A3** | A rushed insider | Edits plan files, reruns the tool, wants tonight's deployment finished |
| **A4** | A hostile or broken node | Controls what its own probe answers and what it reports about itself |

---

## What is defended, and by what

### A1 — the build pipeline is owned

| Attack | Control | Pinned by |
|---|---|---|
| Ship an unsigned image | Quorum enforced with a caller-supplied verifier | `test_an_unsigned_artefact_cannot_be_slipped_past_a_quorum` |
| Lift a signature from a good build onto a bad one | The signature covers the artefact digest | `test_a_signature_cannot_be_transplanted_onto_a_different_image` |
| Ship an image whose component list omits what was added | The signature covers the SBOM digest | `test_a_signature_cannot_be_transplanted_onto_a_different_bill_of_materials` |
| Reach a quorum with one compromised key | Distinct key ids required | `test_one_key_signing_twice_does_not_reach_a_quorum_of_two` |
| Sign with a key nobody trusts | The verifier decides, not the envelope | `test_an_untrusted_key_does_not_count_towards_a_quorum` |
| Ship without a bill of materials | `Manifest.describing` raises | `test_fr6_an_artefact_without_a_bill_of_materials_cannot_be_described` |

### A2 — the network is hostile

| Attack | Control | Pinned by |
|---|---|---|
| Truncate the transfer so it "succeeds" | Digest checked against what was read back | `test_a_truncated_transfer_that_reports_success_is_still_caught` |
| Substitute the bytes between write and read | The check is on the read-back copy, not the sender's | `test_swapping_the_bytes_between_write_and_read_is_caught` |
| Drop the link mid-update | Nothing was activated; the node is untouched | `test_a_dropped_link_leaves_the_node_exactly_where_it_was` |
| Cut the link after activation to strand a bad image | The node reverts on its own timer | `test_cutting_the_link_after_activation_still_ends_in_a_rollback` |
| Make the KMS unreachable so the check is skipped | A verifier that raises counts as a refusal | `test_a_verifier_that_raises_is_treated_as_a_refusal_not_a_crash` |

### A3 — the insider is in a hurry

| Attack | Control | Pinned by |
|---|---|---|
| Continue past a halt | No parameter exists | `test_there_is_no_flag_that_continues_past_a_halt` |
| Widen a canary's tolerance | `tolerated()` truncates; a small wave tolerates nothing | `test_a_canary_wave_cannot_be_configured_to_tolerate_a_failure` |
| Push a second update over an unconfirmed one | Staging refused while pending | `test_two_updates_in_quick_succession_cannot_consume_the_rollback_target` |
| Loosen the budget quietly | Possible — and it is a diff in a plan file, before the rollout | `test_widening_the_budget_is_a_visible_edit_to_a_plan_not_a_hidden_flag` |
| Slip a component past review | Unknown SBOM fields refused, not dropped | `test_an_unknown_component_field_is_refused_not_dropped` |

### A4 — the node lies

| Attack | Control | Pinned by |
|---|---|---|
| A probe that always passes rescues a bad image | The digest check runs before any probe | `test_a_node_whose_probe_always_passes_still_needs_a_valid_image` |
| Reach `confirm()` without a passing probe | One call site, after the failure branch | `test_the_update_path_never_confirms_without_a_passing_probe` |

### The process itself

| Attack | Control | Pinned by |
|---|---|---|
| A manifest or SBOM that executes on load | No `eval`, `exec`, `pickle` or `subprocess` in the package | `test_the_package_never_evaluates_what_it_reads` |
| The tool runs what it downloaded | The payload is opaque bytes; installing is the deployment's job | `test_the_package_never_executes_a_downloaded_artefact` |
| A node id or blob name escaping its directory | Path components refused, not resolved | `test_a_node_id_cannot_escape_the_transport_root` |
| A process killed mid-write leaving a truncated image | Write to `*.partial`, then rename | `test_a_partial_write_never_replaces_a_good_blob` |
| A rollout report carrying the image or the build machine | Codes and counts only | `test_a_rollout_report_carries_no_environment_and_no_payloads` |

---

## Residual risks

Accepted, not deferred. Each is pinned by a test that demonstrates the gap.

### R-1 — No anti-rollback protection

An adversary who can replay traffic can serve an older, correctly signed image
with known vulnerabilities. Every check here is about authenticity and integrity;
none is about freshness.

Closing it means a monotonic version counter the node refuses to go below, which
needs durable storage and a policy for authorised downgrades — both of which are
deployment decisions.

*Pinned by* `test_replaying_an_older_signed_release_is_accepted`.

### R-2 — The health probe is sampled once

A node healthy at confirmation time and unhealthy a minute later keeps the new
image. Continuous health is monitoring, and this package does not pretend to
cover it. What it guarantees is that an image which was *never* healthy is never
committed.

*Pinned by* `test_a_probe_that_passes_then_fails_leaves_a_confirmed_bad_version`.

### R-3 — No attestation

`running_version` is the node's own account of itself. Nothing proves the image
in the active slot is the image whose digest was verified. That needs measured
boot, which is hardware.

*Pinned by* `test_a_node_that_reports_a_version_it_is_not_running_is_not_detectable`.

### R-4 — The verifier is the caller's

The most security-critical check in the package is implemented outside it. A
caller who writes `lambda *_: True` has a system that verifies nothing while
appearing to. Nothing here can prevent that; what is prevented is the accidental
version — a missing verifier — which is the one that happens by mistake.

### R-5 — Storage is assumed reliable

Flash wears out. The interesting failure is a staging write that succeeds and
reads back differently a week later. The digest is checked at staging time only;
nothing re-verifies a slot before boot.

### R-6 — Transfers are not resumable

The `Transport` interface has no vocabulary for a partial transfer, so a large
image over a poor link restarts from zero. Operationally this is the difference
between an update that lands overnight and one that never lands.

---

## Claims deliberately not made

- **Not a secure boot chain.** Nothing here measures or attests what runs (R-3).
- **Not freshness-checked.** Signed does not mean current (R-1).
- **Not a monitoring system.** One probe, once (R-2).
- **Not tested against hardware.** Every node is a Python object; the model is
  the deliverable at this stage. See [PORTING.md](PORTING.md).
