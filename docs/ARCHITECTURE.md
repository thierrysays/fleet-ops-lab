# Architecture

Why the package is shaped this way. The what is in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md); this is the argument.

---

## The failure that shapes everything

A node installs an update at three in the morning, on a site with no engineer,
and the image is bad. It might not bring up the network. It might bring up the
network and not the application. It might come up perfectly and fail an hour
later.

Recovery from that state cannot depend on reaching the node, because a bad image
is the thing most likely to prevent reaching it. Every design decision below
follows from taking that seriously.

## 1. Activation is a promise to try

The straightforward sequence (write the new image, switch the boot slot, reboot) is correct whenever the new image works. When it does not, it has produced a
node that needs a lorry.

So activation here sets `PENDING` and starts a deadline the node holds itself.
`confirm()` commits. `tick()` reverts. **The default outcome of doing nothing is
rollback.**

The consequence people underestimate: `PENDING` is the state that has to survive
a power cut, and it has to survive *as* `PENDING`. A file written in the wrong
order produces a node that boots the new image with no record that it is on
trial, which is the same as having no rollback at all. That is the first thing
[PORTING.md](PORTING.md) tells the bench to test, with the power switch.

This is the same argument as "silence is refusal" in oversight systems, arriving
from operations instead. An update nobody confirmed is not an update that
worked.

## 2. The fleet halts itself, and cannot be told not to

Waves and budgets are standard; an override flag on the halt is also standard,
and is the reason halts do not work. The flag exists for the one incident where
the halt fires correctly, and it is set by someone who has been awake for
nineteen hours.

`Rollout.run(plan, artefact, manifest)` takes no fourth parameter. Resuming a
halted rollout means writing a new plan, which is data, in a file, reviewable
before the rollout starts rather than typed during the incident. A permissive
plan is possible and that is fine: the judgement is visible in a diff.

## 3. The dangerous checks are the ones that get skipped

Three checks in this package are the ones an attacker most wants absent, and all
three fail closed rather than silently passing:

| Check | The accident it prevents |
|---|---|
| `verify_signature(None, quorum=1)` raises | A deployment that forgot to configure a verifier and believed it was verifying |
| An absent health probe rolls back | A node nobody can ask about keeping a change on the strength of silence |
| A verifier that *raises* counts as a refusal | An unreachable KMS crashing the rollout, which is then retried with the check switched off |

The third is the subtle one. A crashed rollout looks like an infrastructure
problem and gets worked around; a refused update looks like a decision and gets
investigated.

## 4. Signature before digest

Verifying the digest against a manifest whose signature has not been checked
proves the download was not corrupted. That was never the question, a hostile
manifest describes hostile bytes perfectly.

So `update_node` authenticates the manifest, then binds the bytes to it. The
order is a one-line difference in the source and the whole difference in what is
proven.

## 5. Nothing here knows what a node is

Slots, a digest, a probe, a transport. Whether that is a Linux SBC with two
rootfs partitions, an MCU with two flash banks, or a workload on a k3s cluster
belongs to the deployment, [ORCHESTRATORS.md](ORCHESTRATORS.md) maps the model
onto RAUC, Mender, SWUpdate, MCUboot, k3s and balena.

The same reasoning applies to cryptography and to transport: whoever runs a
fleet already has a key story and a network, and will not adopt second ones
because a package brought them.

---

## The shape that falls out

```
   build ──► Artefact (opaque bytes)
               │
               ├── SBOM ────────────► digest ──┐
               │                                │
               └── digest ─────────────────────►├──► Manifest ──► signed
                                                 │      │
                                                 └──────┘  binds bytes + components

   Manifest + Artefact ──► Transport ──► Node
                                          │  1. read back
                                          │  2. signature      ─┐
                                          │  3. digest          │ any failure:
                                          │  4. stage (spare)   │ old version,
                                          │  5. activate PENDING│ node untouched
                                          │  6. probe          ─┘
                                          │
                                     confirm ──► ACTIVE
                                     silence ──► tick() ──► FAILED, previous restored

   Rollout: wave ──► wave ──► wave
              │        │
              └────────┴──► failures > budget ──► HALT (remaining waves untouched)
```

## Decisions with their own files

| Decision | Where |
|---|---|
| Activation is provisional; silence reverts | [ADR 0001](adr/0001-provisional-activation.md) |
| The halt has no override | [ADR 0002](adr/0002-halt-is-not-optional.md) |
| No signing, no key store, no crypto dependency | [ADR 0003](adr/0003-no-bundled-cryptography.md) |

## What was considered and rejected

**A single-slot update with a backup copy.** Half the storage. Rejected: the
window in which neither copy is bootable is exactly the window in which power
fails.

**Rollback triggered by a central controller.** Rejected: it requires the node to
be reachable, which is the assumption the whole design exists to avoid.

**Retrying a failed node inside the same rollout.** Rejected: a node that failed
its probe and rolled back is evidence about the image, not about the node.
Retrying it converts one signal into noise, and the second attempt lands on a
node whose rollback target has already been used once.

**Storing the artefact in the rollout report.** Rejected: reports get shared, and
an image is not a thing to paste into a ticket.

**A `--force` flag, of any kind.** Rejected. There is no path in this package
that lets a refused thing proceed, and adding one is a defect rather than a
feature.
