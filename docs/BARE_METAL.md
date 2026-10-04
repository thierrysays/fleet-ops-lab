# Running on bare metal

No container, no orchestrator, no control plane. A board with two slots, a
bootloader that can be told to try one, and a watchdog that resets it when the
try fails.

Everything before this point runs as Python objects on a laptop. This page is
about the day the board arrives, and it is deliberately specific about the parts
that are usually got wrong.

---

## 1. What "two slots" actually requires

| Layer | What it needs | If you skip it |
|---|---|---|
| Storage | Two full copies of the payload, plus room to stage | The staging write lands on the only working copy |
| Bootloader | A "try once" flag it clears on the next boot | Nothing reverts a bad image |
| State | Somewhere durable for `PENDING` | A power cut turns a trial into a commitment |
| Watchdog | Something that resets a hung node | `PENDING` never ends, so the revert never happens |

The last row is the one most often missing. On Linux the confirmation deadline
can be a timer in a supervisor process, but a node hung hard enough not to run
the supervisor is also hung enough not to revert. A hardware watchdog is what
turns "the deadline expired" into an actual reset.

## 2. Linux with U-Boot

U-Boot's `bootcount` and `altbootcmd` implement provisional activation directly,
and the mapping is one to one:

```bash
# stage: write the image to the inactive partition, then
fw_setenv boot_targetslot B          # which slot to try
fw_setenv bootcount 0
fw_setenv bootlimit 3                # three failed boots -> altbootcmd
fw_setenv altbootcmd "setenv boot_targetslot A; boot"   # the rollback
```

On a successful application start, **after** the health probe passes, not at
the end of `rc.local`:

```bash
fw_setenv bootcount 0                # this is confirm()
```

Two details that decide whether this works:

- **`fw_setenv` must be atomic.** Use a redundant environment (two copies with a
  flag). A power cut during a non-redundant write leaves a node with no
  bootloader environment, which is unrecoverable in the field.
- **Confirmation belongs after the probe.** A `systemd` unit that clears the
  bootcount on `multi-user.target` confirms an image that booted, which is not
  the same as an image that works.

```ini
# /etc/systemd/system/fleet-confirm.service
[Unit]
Description=Confirm the running slot once the application is healthy
After=my-application.service
Requires=my-application.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/health-probe --strict
ExecStart=/usr/bin/fw_setenv bootcount 0
```

`ExecStart` runs in order and the unit fails on the first non-zero exit, so a
failing probe means the bootcount is never cleared, which means the next reset
reverts. The rollback needs no code at all.

## 3. Microcontrollers with MCUboot

Stronger than Linux, because the bootloader enforces it rather than a process:

| Model | MCUboot |
|---|---|
| `stage()` | write to the secondary slot |
| `mark_verified()` | image validated: signature and hash |
| `activate()` | `boot_set_pending()`, a **test** image |
| `confirm()` | `boot_write_img_confirmed()` |
| `tick()` expiry | the next reset reverts, because nothing confirmed |

Note the difference from Linux: the revert happens on **reset**, not on a timer.
Something must reset a hung node, and on an MCU that is the independent watchdog
peripheral, enabled before the application starts, kicked only from a path that
proves the application is alive. A design without one has a `PENDING` state it
can never leave.

## 4. Wiring this package in

Three things are yours to supply:

```python
from fleet_ops.node import Node
from fleet_ops.rollout import Rollout, RolloutPlan

class UBootTransport:
    """put/get/has/delete against the staging partition, over your link."""

def probe(node: Node) -> bool:
    """One inference against a known input, or one request to the app's health
    endpoint. Probe the OUTPUT, not the process: a probe that answers 'the
    process is running' confirms an image whose inference returns nothing."""

def verifier(key_id: str, signature: str, payload: bytes) -> bool:
    """Your KMS, TPM, HSM or key file. It must bind the signature to `payload`."""

report = Rollout(nodes, UBootTransport(), probes, verifier, signature_quorum=2).run(
    RolloutPlan.canary_then_rest("agent", "2.4.0", node_ids), artefact, manifest
)
```

## 5. Sizing the confirmation window

Measure, do not guess. Take the slowest node in the fleet, in its worst case (a
filesystem check after an unclean shutdown, a cold page cache, a model loading
from eMMC, an NTP sync the probe depends on) and take the longest cold boot to a
passing probe. Then double it.

A window set too short is a self-inflicted outage, and the operator's first fix
is to disable rollback entirely. That is worse than any bad image.

## 6. The power-cut test

Before this package is worth anything on that board, run this:

1. Update a node. Let it reach `PENDING`.
2. **Cut the power.** Not a reboot: the switch.
3. Restore power.

**Pass:** it comes back on the old slot.
**Fail:** it comes back on the new one, or does not come back.

Repeat twenty times, and repeat with the cut placed at different points: during
the staging write, between staging and activation, between activation and the
probe, and during the confirmation write itself. That last one is where the
write-ordering bug lives, and it is why `PENDING` must be durable *before* the
boot flag changes.

Record the result in the build log either way. A model that has not met a power
switch is a hypothesis.

## 7. Storage arithmetic, honestly

A 4 GB device with a 1.5 GB image does not fit two slots plus staging. The
honest answers are a smaller image or a bigger part. A single slot with a
promise to be careful is not an answer, and the promise is always made by
someone who will not be on site.

## 8. What still will not be true

- **No anti-rollback.** An older signed image is accepted (R-1).
- **The probe is sampled once.** Continuous health is monitoring (R-2).
- **No attestation.** Nothing proves the running image is the verified one (R-3).
- **Transfers are not resumable.** A large image over a poor link restarts (R-6).

All four are in [THREAT_MODEL.md](THREAT_MODEL.md) with the tests that
demonstrate them.
