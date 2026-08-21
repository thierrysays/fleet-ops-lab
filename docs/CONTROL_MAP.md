# Control map

Every control this package implements, and the test that proves it fires.
Adding a control adds a row plus its test. Deleting a test deletes the row.

A control with no test is a claim; a test with no control is a habit.

---

## Controls that are enforced

| # | Control | Implementation | Proven by |
|---|---|---|---|
| K-1 | Activation is provisional | `Node.activate` sets `PENDING` | `test_activation_is_provisional_not_committed` |
| K-2 | Silence reverts, on the node's own timer | `Node.tick` | `test_a_node_that_never_confirms_rolls_itself_back` |
| K-3 | Confirming within the window commits | `Node.confirm` | `test_confirming_within_the_window_commits_the_new_version` |
| K-4 | The rollback target survives a failed activation | `Node.rollback` | `test_the_rollback_target_survives_the_failed_activation` |
| K-5 | Staging never touches the running slot | `Node._spare` | `test_staging_never_writes_to_the_running_slot` |
| K-6 | Staging is refused while a slot is pending | `Node._spare` | `test_staging_while_a_slot_is_pending_is_refused` |
| K-7 | An unverified image is never activated | `Node.activate` | `test_an_unverified_image_is_never_activated` |
| K-8 | The manifest binds the artefact digest | `Manifest.verify_artefact` | `test_bytes_that_do_not_match_the_manifest_are_refused` |
| K-9 | Size is checked as well as digest | `Manifest.verify_artefact` | `test_size_is_checked_as_well_as_digest` |
| K-10 | A truncated transfer is caught | digest on read-back | `test_a_truncated_transfer_is_caught_even_when_it_looks_successful` |
| K-11 | Substituted bytes are caught | digest on read-back | `test_swapping_the_bytes_between_write_and_read_is_caught` |
| K-12 | A required signature with no verifier fails | `Manifest.verify_signature` | `test_a_required_signature_with_no_verifier_is_a_failure_not_a_skip` |
| K-13 | A verifier that raises is a refusal, not a crash | `Manifest.verify_signature` | `test_a_verifier_that_raises_is_treated_as_a_refusal_not_a_crash` |
| K-14 | A signature cannot be transplanted between manifests | `to_be_signed` binds digest and SBOM | `test_a_signature_cannot_be_transplanted_onto_a_different_image` |
| K-15 | One key cannot form a quorum of two | distinct key ids | `test_two_signatures_from_one_key_do_not_make_a_quorum_of_two` |
| K-16 | Signature is checked before digest | order in `update_node` | `test_the_signature_is_checked_before_the_digest` |
| K-17 | An absent health probe rolls back | `update_node` | `test_an_absent_probe_is_a_failed_probe` |
| K-18 | A probe that raises rolls back | `update_node` | `test_a_probe_that_raises_is_a_failed_probe` |
| K-19 | `confirm()` is unreachable without a passing probe | single call site | `test_the_update_path_never_confirms_without_a_passing_probe` |
| K-20 | No artefact without a bill of materials | `Manifest.describing` | `test_an_artefact_without_a_bill_of_materials_cannot_be_described` |
| K-21 | An unknown SBOM schema is refused | `SBOM.from_dict` | `test_an_sbom_with_an_unknown_schema_is_refused` |
| K-22 | An unknown SBOM field is refused, not dropped | `SBOM.from_dict` | `test_an_unknown_component_field_is_refused_not_dropped` |
| K-23 | SBOM digests do not depend on scan order | `SBOM.of` sorts | `test_the_digest_does_not_depend_on_scan_order` |
| K-24 | A wave beyond budget halts the rollout | `Rollout.run` | `test_one_failure_beyond_budget_halts` |
| K-25 | There is no override on the halt | absence of a parameter | `test_there_is_no_flag_that_continues_past_a_halt` |
| K-26 | A canary tolerates nothing | `Wave.tolerated` truncates | `test_a_canary_wave_cannot_be_configured_to_tolerate_a_failure` |
| K-27 | Untouched nodes stay on the working version | halt semantics | `test_the_untouched_nodes_stay_on_the_version_that_was_working` |
| K-28 | Path components cannot escape the node directory | `LocalDirTransport._path` | `test_a_node_id_cannot_escape_the_transport_root` |
| K-29 | A killed write leaves the previous blob intact | write-then-rename | `test_a_partial_write_never_replaces_a_good_blob` |
| K-30 | The package executes nothing it reads | source-level check | `test_the_package_never_evaluates_what_it_reads` |
| K-31 | Reports carry no payloads and no environment | `RolloutReport.as_dict` | `test_a_rollout_report_carries_no_environment_and_no_payloads` |
| K-32 | Every transition is recorded with its reason | `Node.history` | `test_the_history_records_every_transition` |

## Claims deliberately not made

| Not claimed | Why | Demonstrated by |
|---|---|---|
| A signed image is a current image | No anti-rollback counter | `test_replaying_an_older_signed_release_is_accepted` (R-1) |
| The node stays healthy | The probe is sampled once, at confirmation | `test_a_probe_that_passes_then_fails_leaves_a_confirmed_bad_version` (R-2) |
| The node runs what it says it runs | No attestation; that needs measured boot | `test_a_node_that_reports_a_version_it_is_not_running_is_not_detectable` (R-3) |
| Signatures are actually checked | The verifier is the caller's | R-4 in [THREAT_MODEL.md](THREAT_MODEL.md) |
| A staged slot is still intact at boot | Verified once, at staging | R-5 |
| A large image will land over a poor link | Transfers are not resumable | R-6 |
