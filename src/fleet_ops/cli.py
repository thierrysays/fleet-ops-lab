"""Command line: run a rollout, diff two bills of materials, check a build.

Each subcommand does one thing and prints what happened, including the counts
that matter, how many nodes rolled back, and how many were never touched
because the rollout stopped itself.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .demo import run_demo
from .errors import FleetOpsError
from .reproducible import compare_builds, digest_tree
from .sbom import SBOM, diff


def cmd_demo(args: argparse.Namespace) -> int:
    report, nodes = run_demo()
    print(f"  plan         : {report.plan.artefact_name} -> {report.plan.version}")
    print(f"  waves        : {', '.join(w.name for w in report.plan.waves)}")
    print(f"  updated      : {report.updated}")
    print(f"  failed       : {report.failed}")
    print(f"  rolled back  : {report.rolled_back}  <- the number that matters")
    print(f"  untouched    : {report.untouched}")
    if report.halted_at:
        print(f"  halted       : in wave {report.halted_at!r} — {report.halt_reason}")
    print()
    for outcome in report.outcomes:
        mark = "✓" if outcome.ok else "✗"
        print(f"  {mark} {outcome.node_id:<10} {outcome.code:<22} {outcome.detail}")
    print()
    still_old = sorted(
        n for n, node in nodes.items() if node.running_version == "2.3.0"
    )
    print(f"  still on 2.3.0: {len(still_old)} node(s)")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report.as_dict(), indent=2) + "\n")
        print(f"  written: {args.out}")
    return 0


def cmd_sbom_diff(args: argparse.Namespace) -> int:
    before = SBOM.from_dict(json.loads(Path(args.before).read_text()))
    after = SBOM.from_dict(json.loads(Path(args.after).read_text()))
    d = diff(before, after)
    if args.json:
        print(json.dumps(d.as_dict(), indent=2))
        return 0
    print(f"  {before.artefact} {before.version} -> {after.version}: {d.summary()}")
    for c in d.added:
        print(f"  + {c.kind}/{c.name} {c.version} ({c.licence or 'licence unstated'})")
    for c in d.removed:
        print(f"  - {c.kind}/{c.name} {c.version}")
    for a, b in d.changed:
        note = (
            f"  [licence {a.licence or '?'} -> {b.licence or '?'}]"
            if a.licence != b.licence
            else ""
        )
        print(f"  ~ {a.kind}/{a.name} {a.version} -> {b.version}{note}")
    # A new component nobody chose is the finding this command exists for.
    return 1 if (args.fail_on_change and not d.is_empty) else 0


def cmd_repro(args: argparse.Namespace) -> int:
    verdict = compare_builds(digest_tree(args.build_a), digest_tree(args.build_b))
    if args.json:
        print(json.dumps(verdict.as_dict(), indent=2))
    else:
        print(f"  {verdict.summary}")
        for path in verdict.differing:
            print(f"  ~ {path}")
        for path in verdict.only_in_a:
            print(f"  - {path}")
        for path in verdict.only_in_b:
            print(f"  + {path}")
    return 0 if verdict.reproducible else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fol", description="fleet operations for constrained nodes")
    p.add_argument("--version", action="version", version=f"fleet-ops-lab {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="run the deterministic rollout scenario")
    d.add_argument("--out", default=None, help="write the rollout report as JSON")
    d.set_defaults(func=cmd_demo)

    s = sub.add_parser("sbom-diff", help="diff two bills of materials")
    s.add_argument("before")
    s.add_argument("after")
    s.add_argument("--json", action="store_true")
    s.add_argument("--fail-on-change", action="store_true",
                   help="exit non-zero if anything changed, for a CI gate")
    s.set_defaults(func=cmd_sbom_diff)

    r = sub.add_parser("repro", help="compare two build output trees")
    r.add_argument("build_a")
    r.add_argument("build_b")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_repro)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except FleetOpsError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
