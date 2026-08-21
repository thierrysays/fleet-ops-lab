# fleet-ops-lab — project instructions

A working model of updating a fleet of constrained nodes without bricking it.
The product of this repository is **an update that reverts itself**, not a
deployment tool.

## Commands

```bash
pip install -e ".[dev]"
make test          # 67 tests, ~0.3s
make demo          # the deterministic rollout scenario
make qa            # ruff, strict mypy, coverage gate
python -m pytest tests/test_node.py -k rolls_itself_back   # single test
```

`fol demo` must always print **2 rolled back** and **6 untouched**. If it does
not, something regressed — do not adjust the scenario to match the new output.

## Where things are

| Path | Role |
|---|---|
| `canonical.py` | Deterministic bytes for anything hashed or compared. |
| `clock.py` | Injectable time. Confirmation deadlines are why it exists. |
| `errors.py` | One exception per refusal, each with a stable `code`. |
| `artefact.py` | Bytes, and the manifest that binds them to a digest and an SBOM. |
| `sbom.py` | Bill of materials, and the diff that is the useful part. |
| `transport.py` | Four methods, plus `FlakyTransport` so tests live in the real world. |
| `node.py` | A/B slots and the provisional-activation state machine. |
| `update.py` | One node through the six ways it is allowed to stop. |
| `rollout.py` | Waves, budgets, and the halt that has no override. |
| `reproducible.py` | Two build trees compared, differing files named. |
| `demo.py` | The pinned scenario, with four planted failures. |
| `docs/ORCHESTRATORS.md` | Mapping onto RAUC, Mender, MCUboot, k3s, balena. |
| `docs/PORTING.md` | What the first bench port will find wrong. |

## Invariants — do not break these without an ADR

1. **Silence is a rollback.** `PENDING` reverts on deadline, by the node's own
   timer, consulting nothing. There is no path where doing nothing commits.
2. **An absent health probe is a failed probe.** Never a skip.
3. **An absent signature verifier with a required quorum is a failure.** A check
   that cannot run is a check that failed.
4. **Signature before digest.** A digest checked against an unauthenticated
   manifest answers the wrong question.
5. **Staging never touches the running slot**, and is refused while another slot
   is pending — that slot is the rollback target.
6. **The halt has no override.** Resuming means running a new plan.
7. **A canary's budget is zero.** One canary failure is the canary working.
8. **No cryptography ships here.** → ADR 0003.
9. **No runtime dependencies.**

## Conventions

**Tests assert on node state, not on the log.** `node.running_version ==
"1.0.0"` after a failed update, not "a rollback was logged".

**Write the negative test first.** Roughly three quarters of the suite asserts
that an update was refused or reverted.

**Docstrings carry the argument, not the mechanics.**

**ADRs are immutable.** A reversal supersedes, never edits.

## Traps

- `FlakyTransport.truncate_nodes` delivers *successfully* with the wrong bytes.
  That is the case a "did the download succeed" check misses, and the reason
  `digest-mismatch` is a separate code from `transport-failure`.
- SBOM components are keyed on `kind:name`, so a library and a model with the
  same name are different components. Collapsing them hides a model swap inside
  a dependency bump.
- `Wave.tolerated()` truncates: 10% of ten nodes is one, and 10% of five is
  zero. That is deliberate — a small wave tolerates nothing.
- Nothing here has run against hardware. Every node is a Python object.

## The next milestone

1. The power-cut test on a real board with two slots. Everything else is theory
   until a node that lost power mid-confirmation comes back on the old slot.
   Start at `docs/PORTING.md`.
2. A resumable transport: the current interface has no vocabulary for a partial
   transfer, and a 400 MB image over cellular needs one.
3. Coordinated groups — nodes that must update together because they share a
   protocol version.
