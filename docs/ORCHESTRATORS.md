# Mapping onto the tools people actually run

This package is a model of an update process, not a replacement for the systems
that implement one. The mapping matters because the model's two rules (silence
is a rollback, and the fleet halts itself) are supported to very different
degrees by the obvious tools.

## RAUC / SWUpdate / Mender (Linux SBCs with A/B rootfs)

The closest fit, and the model was written with them in mind.

| Model | Tool |
|---|---|
| `Slot` | RAUC slot, SWUpdate partition, Mender rootfs A/B |
| `stage()` | bundle written to the inactive slot |
| `activate()` | bootloader flag set to try-once (`BOOT_ORDER` / `upgrade_available`) |
| `confirm()` | `rauc status mark-good` / `mender commit` |
| `tick()` expiry | bootloader boot-attempt counter reaching zero |

The confirmation window is the piece most often left out. All three tools
support it; a surprising number of deployments configure the slot swap and skip
the mark-good, which produces a fleet that can install a bad image but cannot
recover from one.

**What the model adds:** waves and budgets. These tools update a node. The
decision to stop updating the *rest* of the fleet lives above them, and is
usually a script.

## Microcontrollers with two flash banks (MCUboot, Zephyr)

Also a close fit, with the confirmation window enforced in the bootloader rather
than by a supervisor process, which is stronger, because a hung application
cannot confirm.

`SlotState.PENDING` is MCUboot's *test* image; `confirm()` is
`boot_write_img_confirmed()`; the expiry path is the bootloader reverting on the
next reset. Note the difference from Linux: on an MCU the revert happens on
**reset**, not on a timer, so something must reset a hung node. That something is
a hardware watchdog, and a design that omits it has a `PENDING` state it can
never leave.

## k3s at the edge

k3s is a reasonable choice on a node with a few gigabytes of RAM and a
filesystem that tolerates writes. Its rollout machinery covers part of this:

| Model | k3s / Kubernetes |
|---|---|
| Health probe | readiness and liveness probes |
| Provisional activation | `maxUnavailable` / `maxSurge` during a rolling update |
| Rollback | `kubectl rollout undo` |
| Waves | separate Deployments, or a progressive-delivery controller |

What it does not give you on a constrained edge node:

- **Nothing rolls back the node.** Kubernetes rolls back a workload. If the
  update that broke the node was the k3s agent, the kernel, or the base image,
  the cluster is not in a position to fix it, and you are back to A/B slots
  underneath.
- **A rollback needs the registry.** `rollout undo` on a node whose site link is
  down works only if the previous image is still in the local containerd store.
  It frequently is not, because that is what image garbage collection is for.
- **`imagePullPolicy` is not a digest check.** Pulling by tag on a flaky link is
  the case `digest-mismatch` exists for. Pin by digest.
- **The control plane is a dependency.** A single-server k3s at a site is a
  single point of failure that the A/B model does not have.

The honest architecture on a constrained edge site is usually both: A/B slots for
the base image, k3s for the workloads on top, and the halt rule applied across
sites rather than across pods.

## balena, Azure IoT Edge, AWS IoT Greengrass

Managed equivalents with their own rollout controls. The model translates, and
the part worth checking in each is the same: what happens to a device that
installs the update, comes up, and then cannot reach the service that would tell
it to roll back. If the answer is "an operator notices", that is not rollback,
it is monitoring.
