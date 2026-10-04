# Test strategy

Five tiers, each answering a different question. The tier a test belongs to is
the directory it lives in, the marker is applied from the path at collection
time, so a test cannot be moved between tiers and keep an old label.

```
make smoke        # does it start at all                     ~2 s
make unit         # each part at its boundary                ~1 s
make functional   # the specification, end to end            ~3 s
make security     # input and paths it did not create        ~1 s
make pentest      # attacks on the two rules                 ~1 s
make test         # all of the above
make qa           # lint, strict types, SAST, advisories, coverage
```

---

## `tests/smoke/`, does it start

Imports the package, runs the CLI as a **subprocess**, runs the demo, parses the
report it wrote. A deployment tool that only works when imported by its own test
suite is a tool nobody can deploy with.

## `tests/unit/`, one behaviour, at its boundary

A node that never confirms reverts at the deadline and not a second before.
Staging while pending is refused. A signature from one key twice is one
signature. Fast, deterministic, `ManualClock` throughout.

The house rule: **assert on node state, not on the log.** `node.running_version
== "1.0.0"` after a failed update, never "a rollback was logged".

## `tests/functional/`, does it meet the specification

One test per requirement in [FUNCTIONAL_SPEC.md](FUNCTIONAL_SPEC.md), named for
the requirement it discharges (`test_fr7_...`), written from the specification
rather than from the code, and run through the CLI wherever an operator would.

Includes the demo's pinned counts. The demo is a fixture, not a decoration: `2
rolled back, 6 untouched, halted in 'pilot'` is part of the contract.

## `tests/security/`, input and paths it did not create

An update system is the highest-value target in a fleet. The properties under
test: untrusted input can make it **refuse** and nothing else; a path component
from a plan file cannot escape a node's directory; a check that cannot run counts
as failed; and nothing in the package executes what it reads, including the
artefact it just downloaded, which stays opaque bytes.

## `tests/pentest/`, attacks on the two rules

Silence is a rollback; the fleet halts itself. Each test takes the position of an
adversary from [THREAT_MODEL.md](THREAT_MODEL.md): a compromised build pipeline
(A1), a network position (A2), a rushed insider (A3), a hostile node (A4).

The signature tests use a verifier that genuinely binds the signature to the
payload, written out in the module. The mistake being pinned is a verifier that
ignores the payload, with one of those, every transplant test passes and proves
nothing.

**Three tests pass by demonstrating a gap**: an older signed release replays
successfully (R-1), a probe that passes then fails leaves a bad version committed
(R-2), and a node that lies about its version is not detectable (R-3). A pen-test
suite in which the system always wins is a suite written afterwards.

## `make qa`, the gate

| Step | Tool | Fails on |
|---|---|---|
| Lint | `ruff` | any finding |
| Types | `mypy --strict` | any error |
| SAST | `bandit -r src` | any unjustified finding |
| Advisories | `pip-audit` | any known vulnerability |
| Coverage | `pytest --cov` | below 90 % |

Everything in the gate fails the build.

---

## Hardware tests

The `hardware` marker is reserved for tests needing a real board with two slots.
They are deselected unless `FOL_HARDWARE=1`, and CI never sets it. The first one
to be written is the power-cut test in [PORTING.md](PORTING.md), cut power
between activation and confirmation, and assert the node comes back on the old
slot.

## What the tiers do not cover

- **Real storage.** No test pulls power, wears out flash, or corrupts a slot
  after staging (R-5).
- **Real networks.** `FlakyTransport` drops and truncates deterministically. It
  does not reorder, delay, or partially deliver over hours.
- **Scale.** The largest fleet in the suite is twenty nodes.
- **Concurrency.** Nodes update sequentially within a wave.
