# fleet-ops-lab

**Updating a fleet of constrained nodes without bricking it.**

Every conversation about edge AI eventually reaches the buyer's actual
questions, and none of them are about the model. How do you update two hundred
of these. What happens when an update is bad. What is inside the image. Can you
rebuild the version that is running in the field today. The demonstrations are
about inference; the procurement is about these four.

This repository is the unglamorous half, built as a working model rather than a
slide: A/B slots with automatic rollback, digest-bound manifests, SBOM diffing,
reproducible-build checking, and a waved rollout that halts itself.

```
pip install -e .
fol demo
```

```
  plan         : inspection-agent -> 2.4.0
  waves        : canary, pilot, fleet
  updated      : 2
  failed       : 4
  rolled back  : 2  <- the number that matters
  untouched    : 6
  halted       : in wave 'pilot' — 4/5 failed in wave 'pilot', budget was 20% (1 node(s))

  ✓ node-01    updated                health probe passed
  ✓ node-02    updated                health probe passed
  ✗ node-03    transport-failure      node-03: link dropped during transfer
  ✗ node-04    digest-mismatch        manifest says sha256:ceba2163…, bytes hash to sha256:c1735458…
  ✗ node-05    health-probe-failed    health probe failed
  ✗ node-06    health-probe-failed    no health probe supplied
```

Six nodes were never touched. That is the rollout working, not the rollout
failing.

---

## The two rules

**An update is provisional until the node says otherwise.** Activation starts a
confirmation window. A node that boots a new image and does not check in — bad
image, dead network, someone pulled the power — reverts to the slot it was
running before, on its own timer, with nobody available to intervene. The state
that survives a power cut is `PENDING`, and `PENDING` reverts. Silence is a
rollback, never a success.

**The fleet halts itself.** A wave that exceeds its failure budget stops the
rollout, and there is no flag to continue. The flag would be enabled at three in
the morning by whoever has been awake for nineteen hours and wants the
deployment finished, which is precisely when continuing is worst.

Everything else follows from those two.

---

## What is modelled

| Concern | What is here | The failure it is aimed at |
|---|---|---|
| **A/B slots** | `node.py` — stage into the spare, activate provisionally, confirm or revert | An update that overwrites the only working copy |
| **Digest binding** | `artefact.py` — the manifest carries the artefact's digest, checked on the node after transfer | A transfer that *succeeds* and delivers the wrong bytes |
| **Signature quorum** | `Manifest.verify_signature` with a caller-supplied verifier | An unsigned image, and — the subtler one — a check that was skipped because no verifier was configured |
| **Health probes** | `update.py` — pass confirms, fail rolls back, **absent rolls back** | A node nobody can ask about keeping a change on the strength of silence |
| **Waves and budgets** | `rollout.py` — canary at zero budget, then widening waves | A fleet-wide outage from one bad build |
| **SBOM diff** | `sbom.py` — added, removed, version-changed, and licence changes called out | "What is in this image" asked on a deadline, sixty days too late |
| **Reproducible builds** | `reproducible.py` — hash both trees, name every file that differs | An argument about what is actually deployed, at the start of every incident |

None of it knows what a node is. A node has slots, a digest, a health probe and
a transport. Whether that is a Linux SBC with two rootfs partitions, an MCU with
two flash banks, or a workload on a k3s cluster at the edge belongs to the
deployment — see [docs/ORCHESTRATORS.md](docs/ORCHESTRATORS.md) for how the
model maps onto RAUC, Mender, SWUpdate, balena and k3s.

---

## Failure codes

Every stopping point has a stable code, because these are what end up grouped on
a dashboard and quoted in an incident report:

```
transport-failure     the bytes did not arrive; ordinary, and not an incident
digest-mismatch       the bytes arrived and are not the bytes described
signature-invalid     unsigned, under-signed, or no verifier was configured
slot-unavailable      staging now would destroy the rollback target
not-staged            activation attempted with nothing verified
health-probe-failed   failed, raised, or absent
rollout-halted        a wave exceeded its budget
```

`fol demo --out run/rollout.json` writes them as `fleet-ops/rollout-report/v1`.

---

## Using it against a real fleet

Three things are yours to supply, and all three are deliberately not bundled:

```python
transport = MyTransport()                       # put / get / has / delete
probe     = lambda node: my_client.healthy(node.node_id)
verifier  = lambda key_id, sig, payload: my_kms.verify(key_id, sig, payload)

report = Rollout(nodes, transport, probes, verifier, signature_quorum=2).run(
    RolloutPlan.canary_then_rest("agent", "2.4.0", node_ids), artefact, manifest
)
```

No cryptography ships here. Whoever runs a fleet already has a key story — a
TPM, a cloud KMS, an HSM, an Ed25519 key in a file — and this package will not
choose one on their behalf. What it insists on is that an *absent* verifier with
a required quorum is a failure and never a skip.

---

## What this is not

- **Not a device management platform.** No enrolment, no inventory, no
  telemetry, no dashboard. Those are products and there are good ones.
- **Not a container orchestrator.** The waved rollout with a halt rule overlaps
  with what a Kubernetes rollout does; where you have k3s, use it, and read
  `docs/ORCHESTRATORS.md` for what it does not give you on a constrained node.
- **Not a signing service.** See above.
- **Not tested against hardware.** Every node here is a Python object. The model
  is the deliverable at this stage, and the first bench port will find something
  wrong with it — `docs/PORTING.md` records what to expect.

## Licence

Apache-2.0.
