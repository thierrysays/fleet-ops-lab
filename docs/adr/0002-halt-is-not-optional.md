# ADR 0002 — The rollout halts itself, and there is no override

**Status:** accepted · 2026-08-21

## Context

Waved rollouts are standard. A halt rule is standard. An override flag on the
halt rule is also, unfortunately, standard — and it exists because during the
one incident where the halt fires legitimately, somebody senior is asking why the
deployment is not finished.

## Decision

`Rollout.run` stops when a wave exceeds its budget. There is no parameter that
continues past a halt. Resuming means running a new plan, deliberately, with the
failed nodes visible in the previous report.

## Cost

A halt caused by a genuinely unrelated failure — a site link down during the
pilot wave — forces a manual restart of a rollout that would have been fine. That
is real friction, and it will happen.

## Consequence

The budget is where the judgement lives, and it belongs in the plan file, which
is diffable and reviewable before the rollout starts, rather than in a flag
typed at the moment of maximum pressure. `Wave.failure_budget` defaults to zero
for a canary because one canary failure is the canary doing its job.
