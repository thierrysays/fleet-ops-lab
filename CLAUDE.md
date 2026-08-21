# fleet-ops-lab — project instructions

A working model of updating a fleet of constrained nodes without bricking it.
The product of this repository is **an update that reverts itself**, not a
deployment tool.

## Commands

```bash
pip install -e ".[dev]"
make test          # 134 tests across five tiers, ~1s
make smoke         # 6 tests — run this first on a new machine
make demo          # the deterministic rollout scenario
make qa            # ruff, strict mypy, bandit, pip-audit, coverage >= 90%
python -m pytest tests/unit/test_node.py -k rolls_itself_back   # single test
python -m pytest -m pentest                                     # one tier
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
| `tests/smoke/` | Does it start at all. Subprocess-level. |
| `tests/unit/` | One behaviour of one module, at its boundary. |
| `tests/functional/` | One test per requirement in the functional spec. |
| `tests/security/` | Untrusted input, path safety, checks that cannot run. |
| `tests/pentest/` | Attacks on the two rules, including three that succeed. |
| `docs/GETTING_STARTED.md` | Neophyte path: no terminal experience assumed. |
| `docs/FUNCTIONAL_SPEC.md` | Actors, FR-1…FR-14, acceptance criteria. |
| `docs/TECHNICAL_REFERENCE.md` | Module by module, every artefact field. |
| `docs/ARCHITECTURE.md` | Why it is shaped this way; what was rejected. |
| `docs/BARE_METAL.md` | U-Boot, MCUboot, watchdogs, the power-cut test. |
| `docs/THREAT_MODEL.md` | Adversaries A1–A4, residual risks R-1…R-6. |
| `docs/CONTROL_MAP.md` | Control → implementation → the test that proves it. |
| `docs/TEST_STRATEGY.md` | The five tiers and what each is for. |
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

## The delivery standard

Every deliverable in this repository ships with all of the following. This is the
standing default, not a per-task decision — a change that adds behaviour without
its documentation and its tiers is unfinished, not fast.

1. **Technical documentation** — module by module, every artefact field.
2. **Functional documentation** — actors, numbered requirements, acceptance
   criteria, written so someone who never reads the source can check a claim.
3. **A neophyte path** — a guide assuming no terminal, no Python, no git.
4. **A bare-metal run** — how it works on real hardware with no container.
5. **A full test harness** — smoke, unit, functional, security and pen-test
   tiers, each selectable, each with a stated purpose.
6. **A QA gate** — lint, strict types, SAST, dependency advisories, coverage.
   Everything in it fails the build.
7. **A threat model with residual risks**, each pinned by a test that
   demonstrates the gap rather than hiding it.

## Conventions

**Tests assert on node state, not on the log.** `node.running_version ==
"1.0.0"` after a failed update, not "a rollback was logged".

**Write the negative test first.** Roughly three quarters of the suite asserts
that an update was refused or reverted.

**A pen-test that only passes is a pen-test written afterwards.** Where an attack
succeeds, the test says so and names the residual risk. Three currently do.

**The tier is the directory.** `tests/<tier>/` gets the marker automatically at
collection. Do not add `pytestmark` by hand.

**A signature test needs a verifier that binds the payload.** A verifier that
ignores its `payload` argument makes every transplant test pass and prove
nothing. `tests/pentest` writes one out for this reason.

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
