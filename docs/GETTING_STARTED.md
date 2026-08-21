# Getting started

**From a machine with nothing installed to watching a fleet stop itself, in
about twenty minutes.**

This guide assumes nothing. If you have never opened a terminal, never installed
Python and have never used git, you are the reader it was written for. Every
command is given in full, and where a step can go wrong the failure and its fix
are written next to it.

You do **not** need any hardware. Every "node" here is a Python object.

If you already work in Python: `pip install -e ".[dev]" && make demo` and skip to
[What the demonstration shows](#what-the-demonstration-shows).

---

## Table of contents

- [Part 0 — What you are about to run, and why](#part-0--what-you-are-about-to-run-and-why)
- [Part 1 — Open a terminal](#part-1--open-a-terminal)
- [Part 2 — Install Python](#part-2--install-python)
- [Part 3 — Get the code](#part-3--get-the-code)
- [Part 4 — Make a virtual environment](#part-4--make-a-virtual-environment)
- [Part 5 — Install the project](#part-5--install-the-project)
- [Part 6 — Run the tests](#part-6--run-the-tests)
- [Part 7 — Run the demonstration](#part-7--run-the-demonstration)
- [What the demonstration shows](#what-the-demonstration-shows)
- [Part 8 — Watch a node rescue itself](#part-8--watch-a-node-rescue-itself)
- [Part 9 — Try to break the rules](#part-9--try-to-break-the-rules)
- [Part 10 — Diff two bills of materials](#part-10--diff-two-bills-of-materials)
- [Part 11 — Check a build is reproducible](#part-11--check-a-build-is-reproducible)
- [Troubleshooting](#troubleshooting)

---

## Part 0 — What you are about to run, and why

Imagine two hundred small computers in a factory, running software you wrote.
You have a new version. How do you install it on all two hundred, and what
happens when the new version turns out to be broken?

That second question is the whole subject. Software updates on servers are easy
to undo, because there is always somebody who can log in. On a machine bolted
inside a production line, on a site with no engineer, at three in the morning,
there may be nobody — and if the broken update also broke the network, there is
no way in at all.

This project models an update process built around that. Two rules:

1. **An update is provisional until the machine says it worked.** It installs,
   it boots, and it must check in within a few minutes. If it does not — because
   it crashed, because the network died, because somebody pulled the plug — it
   puts the old version back **by itself**, with nobody watching.

2. **The fleet stops itself.** Updates go out to a few machines first. If too
   many of them fail, the rollout stops and the rest keep running what they were
   running. There is no button to override this, on purpose.

You will run a simulation of twelve machines with four deliberate faults in it,
and watch both rules fire.

**Time:** about twenty minutes, most of it downloads.
**Cost:** nothing.
**Risk:** none. Everything happens in one folder you can delete afterwards.

---

## Part 1 — Open a terminal

A terminal is a window where you type commands instead of clicking.

**Windows** — press the Windows key, type `powershell`, press Enter.

**macOS** — press ⌘ + Space, type `terminal`, press Enter.

**Linux** — press Ctrl + Alt + T, or find "Terminal" in your applications.

You will see a prompt: some text ending in `>` or `$` or `%`. Commands go after
it. Type them exactly, then press Enter.

---

## Part 2 — Install Python

```bash
python3 --version
```

If you see `Python 3.10` or higher, skip to Part 3.

**If not:**

- **Windows** — [python.org/downloads](https://www.python.org/downloads/). Tick
  **"Add Python to PATH"** during installation; if you miss it the terminal will
  not find Python afterwards. Close and reopen PowerShell when done.
- **macOS** — the same site, or `brew install python@3.12`.
- **Linux (Debian/Ubuntu)** — `sudo apt update && sudo apt install -y python3 python3-venv python3-pip`.

On Windows the command is often `python` rather than `python3`.

---

## Part 3 — Get the code

```bash
git --version
```

If that errors, install git from [git-scm.com/downloads](https://git-scm.com/downloads)
and reopen the terminal. Then:

```bash
git clone https://github.com/thierrysays/fleet-ops-lab.git
cd fleet-ops-lab
```

---

## Part 4 — Make a virtual environment

A private copy of Python for this project, so nothing you install can affect
anything else on your machine.

```bash
python3 -m venv .venv
```

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows PowerShell:**
```bash
.venv\Scripts\Activate.ps1
```

Your prompt should now start with `(.venv)`.

> **If Windows says "running scripts is disabled":**
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, answer
> `Y`, then activate again.

**You must activate in every new terminal window.** "Command not found" later is
almost always this.

---

## Part 5 — Install the project

```bash
pip install -e ".[dev]"
fol --version
```

You should see `fleet-ops-lab 0.1.0`. `fol` is the command this project installs.

---

## Part 6 — Run the tests

```bash
make test
```

> **No `make` on Windows?** Use `python -m pytest`. Every `make` target has a
> plain equivalent in the `Makefile`.

Then try one tier:

```bash
make pentest
```

Those are the adversarial tests — deliberate attempts to break the two rules.
Three of them pass by *demonstrating a gap* rather than by winning; they are
named as limitations, and [THREAT_MODEL.md](THREAT_MODEL.md) lists each one.

---

## Part 7 — Run the demonstration

```bash
make demo
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

---

## What the demonstration shows

Twelve machines, in three groups: one **canary**, then a **pilot** of five, then
the remaining six. Four faults were planted in the pilot group.

**`node-03 transport-failure`** — the network dropped. The update never arrived,
so nothing happened. This is not an incident: the machine is still running the
version that works.

**`node-04 digest-mismatch`** — this is the interesting one. The download
*succeeded*. It just delivered the wrong bytes — half the file, in this case.
A check that asks "did the download work?" says yes. This project checks the
fingerprint of what actually landed on the machine, so it says no.

**`node-05 health-probe-failed`** — it installed, it booted, and it failed its
health check. It put the old version back.

**`node-06 health-probe-failed — no health probe supplied`** — nobody configured
a health check for this machine. It was rolled back anyway. A machine you cannot
ask "are you working?" does not get to keep a change on the strength of silence.

**`halted : in wave 'pilot'`** — four failures out of five, against a budget that
allowed one. The rollout stopped.

**`untouched : 6`** — the last group never got the update at all. They are still
running the old version, which is the version that works. **That is the rollout
succeeding**, not failing. If it had carried on, twelve machines would be broken
instead of four, and none of the four are actually broken — they all recovered.

---

## Part 8 — Watch a node rescue itself

The rollback in the demo happened because a health check failed. The more
important case is when nobody is there at all.

Create a file called `alone.py`:

```python
from fleet_ops.clock import ManualClock
from fleet_ops.node import Node

clock = ManualClock()                       # time we control, so this is instant
node = Node("node-99", confirm_window_s=300.0, clock=clock)

# It is running version 1.0.0 and everything is fine.
slot = node.stage("1.0.0", "sha256:old"); node.mark_verified(slot)
node.activate(); node.confirm()
print("running:", node.running_version)

# A new version is installed and booted.
slot = node.stage("2.0.0", "sha256:new"); node.mark_verified(slot)
node.activate()
print("running:", node.running_version, "— but not confirmed yet")

# Now nothing happens. Nobody logs in. The network is down. Five minutes pass.
clock.advance(301.0)
reverted = node.tick()

print("rolled back by itself:", reverted)
print("running:", node.running_version)
```

```bash
python alone.py
```

```
running: 1.0.0
running: 2.0.0 — but not confirmed yet
rolled back by itself: True
running: 1.0.0
```

Nothing was told to do that. No server was contacted, no operator was paged. The
machine reverted because nothing said it was working, and the design treats
silence as a failure rather than as consent.

---

## Part 9 — Try to break the rules

**Attempt one: force the rollout to continue past a halt.**

Look for the option:

```bash
python -c "import inspect, fleet_ops.rollout as r; print(inspect.signature(r.Rollout.run))"
```

```
(self, plan, artefact, manifest)
```

There is no `force`, no `continue_on_failure`, no `ignore_budget`. That absence is
deliberate — such a flag would be used at three in the morning by whoever wants
the deployment finished, which is precisely when continuing is worst. Restarting
a halted rollout means writing a new plan, which somebody can read first.

**Attempt two: install an update over one that has not been confirmed.**

```python
from fleet_ops.node import Node
node = Node("n1")
s = node.stage("1.0.0", "sha256:a"); node.mark_verified(s); node.activate(); node.confirm()
s = node.stage("2.0.0", "sha256:b"); node.mark_verified(s); node.activate()
node.stage("3.0.0", "sha256:c")     # <- boom
```

```
fleet_ops.errors.SlotUnavailable: n1: slot 'b' is pending confirmation;
staging now would destroy the rollback target
```

Two updates in a row, without waiting for the first to be confirmed, would use up
the copy the machine needs to go back to. That is how a machine gets bricked by a
process that was trying to be helpful.

**Attempt three: ship an update with no bill of materials.**

```python
from fleet_ops.artefact import Artefact, Manifest
Manifest.describing(Artefact("agent", "1.0", b"bytes"), None)
```

```
fleet_ops.errors.SbomMissing: agent 1.0 has no bill of materials;
an artefact that cannot be enumerated cannot be deployed
```

When a vulnerability is announced, "what is in the thing we shipped?" is asked on
a deadline. An image nobody can enumerate cannot answer it.

---

## Part 10 — Diff two bills of materials

A bill of materials — an **SBOM** — is a list of everything inside a release that
somebody else wrote. Producing one is a compliance exercise. Comparing two is an
engineering one.

```bash
fol sbom-diff examples/sbom-2.3.0.json examples/sbom-2.4.0.json
```

```
  inspection-agent 2.3.0 -> 2.4.0: 1 added, 0 removed, 3 changed
  + library/telemetry-shim 0.2.0 (BUSL-1.1)
  ~ library/libwebsockets 4.3.2 -> 4.3.3
  ~ library/tflite-micro 1.2.0 -> 1.3.0
  ~ model/inspection-model 6 -> 7
```

The first line is the one to look at. A component appeared that was not there
before, and its licence is BUSL-1.1 — a source-available licence with commercial
restrictions, in a product being shipped to customers. Nobody chose that; it
arrived as somebody else's dependency.

For a CI pipeline:

```bash
fol sbom-diff old.json new.json --fail-on-change
echo $?        # 1 if anything changed, 0 if nothing did
```

---

## Part 11 — Check a build is reproducible

"Reproducible" means building the same source twice gives byte-identical output.
When it does not, "is the version in the field the version in the repository?"
has no answer, and every incident starts with an argument about it.

```bash
mkdir -p /tmp/build-a/bin /tmp/build-b/bin
echo "ELF" > /tmp/build-a/bin/agent && echo "ELF" > /tmp/build-b/bin/agent
echo "2026-08-21 14:02" > /tmp/build-a/build-stamp.txt
echo "2026-08-21 16:47" > /tmp/build-b/build-stamp.txt

fol repro /tmp/build-a /tmp/build-b
```

```
  not reproducible: 1 file(s) differ
  ~ build-stamp.txt
```

It names the file. That is the entire value: `bin/agent` is identical, and the
only difference is an embedded build timestamp — which is a morning's work to
fix, and invisible if the tool had only said "not reproducible".

---

## Troubleshooting

**`command not found: fol`**
The virtual environment is not active. Run the activate command from Part 4.

**`command not found: python3`**
On Windows try `python`. Otherwise Python is not installed, or was installed
without "Add to PATH".

**`No module named venv`**
On Debian/Ubuntu: `sudo apt install python3-venv`.

**`make: command not found`**
Windows does not ship `make`. Use `python -m pytest` and
`python -m fleet_ops.cli demo`.

**`error: externally-managed-environment`**
You are installing outside a virtual environment. Do Part 4 first. Do not use
`--break-system-packages`; the name is accurate.

**The demo prints different numbers**
The scenario is pinned at 2 rolled back and 6 untouched, and a test enforces it.
Different numbers mean the version has moved on, or something regressed — either
way it is worth reporting.

**Where do I go next?**
[BARE_METAL.md](BARE_METAL.md) for a real board with two slots,
[ORCHESTRATORS.md](ORCHESTRATORS.md) if you already use RAUC, Mender or k3s, and
[THREAT_MODEL.md](THREAT_MODEL.md) for what this does not protect against.
