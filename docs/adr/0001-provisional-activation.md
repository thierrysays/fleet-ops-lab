# ADR 0001 — Activation is provisional, and silence reverts

**Status:** accepted · 2026-08-21

## Context

The straightforward update sequence — write the new image, switch the boot slot,
reboot — is correct whenever the new image works. When it does not, recovery
requires the node to be reachable, which is the one thing a bad image most
reliably prevents. On a site with no engineer, that is a lorry journey.

## Decision

`activate()` puts the new slot in `PENDING` and starts a confirmation window.
`confirm()` commits. `tick()` reverts when the window expires. The node's own
timer does this; it consults no server.

The default outcome of doing nothing is rollback.

## Cost

Every deployment must supply a health probe and a supervisor that ticks, and a
node that is healthy but slow to confirm gets rolled back unnecessarily. The
window is a tunable with no universally right value, and setting it too short is
a self-inflicted outage.

Accepted, because the alternative failure — a fleet that installs a bad image
and cannot recover — is not recoverable at all, and this one is a redeploy.

## Consequence

`SlotState.PENDING` is the state that must survive a power cut, and it must
survive as `PENDING` rather than as `ACTIVE`. On a bootloader-based
implementation this falls out for free. On anything storing state in a file, the
write ordering is the whole implementation, and the first bench port should
prove it with the power switch.
