# Porting to something with a power switch

Every node in this repository is a Python object, and the model is worth exactly
as much as the first bench port says it is. What follows is what to test, in
order, and what is expected to be wrong.

## 1. The power-cut test

The only test that matters first. Update a node, let it reach `PENDING`, and cut
power before it confirms.

**Pass:** it comes back on the old slot.
**Fail:** it comes back on the new one, or does not come back.

If persisted state is a file, the write ordering is the entire implementation:
the record saying "trying the new slot" must be durable *before* the boot flag
changes, or a power cut in between produces a node that boots the new image with
no record that it is on trial. Expect to get this wrong once.

## 2. The confirmation window on a slow node

Pick a window, then measure how long a cold boot actually takes on the slowest
node in the fleet, under the worst case — a filesystem check after an unclean
shutdown, a model that loads from eMMC, an NTP sync the probe depends on. The
window has to exceed that with margin, or the fleet rolls itself back for no
reason and the operator's first fix is to disable rollback.

## 3. The health probe that lies

A probe that answers "the process is running" confirms an image whose inference
returns nothing. Probe the output, not the process. The most useful probe on an
inference node is one inference against a known input with a known answer.

## 4. Storage for two slots

The uncomfortable arithmetic: two copies of everything, plus room to stage a
third. On a 4 GB device with a 1.5 GB image this does not fit, and the honest
answers are a smaller image or a bigger part — not a single slot with a promise
to be careful.

## 5. What the model is expected to get wrong

- **Transfer is atomic here and resumable in reality.** A 400 MB image over a
  cellular link needs range requests and a partial-transfer record; the
  `Transport` interface has no vocabulary for that yet.
- **Nodes update independently here.** Real fleets have nodes that must update
  together — a cell where the vision node and the controller share a protocol
  version — and there is no notion of a coordinated group.
- **Time is monotonic and singular here.** Real nodes lose their clock across a
  power cut, and a confirmation deadline stored as wall time is a deadline that
  can be in the past on boot.
- **Storage never fails here.** Flash wears out, and the interesting failure is
  a staging write that succeeds and reads back differently a week later. The
  digest is checked at staging time only.

Each of these is a real gap. They are listed rather than fixed because a model
that quietly grows features nobody has tested against hardware is how the model
stops being trustworthy.
