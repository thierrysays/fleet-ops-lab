"""Fail the build when a documented test count no longer matches the suite.

A count written next to a command is stale the moment somebody adds a test, and
nothing else in the gate notices. This repository documents seven of them: one
per tier plus the total, in `README.md` and `CLAUDE.md`. That is seven chances
to be quietly wrong about the only figure a reader can check without cloning.

The tier of a test is the directory it sits in, which is the same rule
`tests/conftest.py` uses to apply the markers. Counting by path rather than by
marker keeps this check independent of hook ordering, and means it still works
if the marker mechanism is ever replaced.

The count comes from pytest's own collection rather than from parsing its
output, so a future pytest release that rewords its summary line does not break
the gate.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Files that quote a count as current guidance, and must therefore be right.
#: Dated records are deliberately not watched: a gate that rewrites history to
#: match today produces a worse record than no gate at all.
WATCHED = ("README.md", "CLAUDE.md")

TIERS = ("smoke", "unit", "functional", "security", "pentest")

#: `make unit  # each part at its boundary  54 tests` and
#: `make test  # 111 tests across five tiers, ~5s` both match.
DOCUMENTED = re.compile(r"^\s*make\s+([a-z-]+)\b.*?(\d+)\s+tests\b")


class _CollectionCounter:
    """Records what pytest collected, without running any of it."""

    def __init__(self) -> None:
        self.items: list[Any] = []

    def pytest_collection_modifyitems(self, items: list[Any]) -> None:
        self.items = list(items)


def collected_counts() -> dict[str, int]:
    """Collected tests per tier, plus ``test`` for the whole suite."""
    counter = _CollectionCounter()
    # Collection prints a line per test file. A gate step should say whether it
    # passed and nothing else, so the listing is swallowed unless it fails.
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        status = pytest.main(
            [
                "--collect-only",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                str(ROOT / "tests"),
            ],
            plugins=[counter],
        )
    if status != 0:
        print(captured.getvalue(), file=sys.stderr)
        raise SystemExit(f"collection failed with pytest exit status {status}")

    counts = dict.fromkeys(TIERS, 0)
    for item in counter.items:
        # `item.path` since pytest 7, which is the floor this project declares.
        # `item.fspath` was removed in pytest 9.
        for part in Path(str(item.path)).parts:
            if part in TIERS:
                counts[part] += 1
                break
    counts["test"] = len(counter.items)
    return counts


def documented_counts() -> list[tuple[Path, int, str, int]]:
    """Every documented count, as (path, line number, target, value)."""
    found: list[tuple[Path, int, str, int]] = []
    for name in WATCHED:
        path = ROOT / name
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            match = DOCUMENTED.match(line)
            if match:
                found.append((path, lineno, match.group(1), int(match.group(2))))
    return found


def main() -> int:
    actual = collected_counts()
    documented = documented_counts()
    problems: list[str] = []

    if not documented:
        print(
            "no documented test count found in "
            + ", ".join(WATCHED)
            + "\nthis check passes vacuously once the number it guards is deleted, "
            "so an empty result is a failure rather than a pass",
            file=sys.stderr,
        )
        return 1

    for path, lineno, target, value in documented:
        where = f"{path.relative_to(ROOT)}:{lineno}"
        if target not in actual:
            problems.append(
                f"{where}: documents a count for {target!r}, which is not a tier "
                f"or the whole suite; known: {', '.join(sorted(actual))}"
            )
        elif value != actual[target]:
            problems.append(
                f"{where}: documented {value} tests for {target!r}, "
                f"the suite collects {actual[target]}"
            )

    documented_targets = {target for _, _, target, _ in documented}
    for tier in (*TIERS, "test"):
        if tier not in documented_targets:
            problems.append(
                f"no documented count for {tier!r} in {' or '.join(WATCHED)}; "
                "a tier nobody documents is a tier nobody notices emptying"
            )

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        counts = ", ".join(f"{k} {actual[k]}" for k in (*TIERS, "test"))
        print(f"\nthe suite collects: {counts}", file=sys.stderr)
        return 1

    print(
        "documented counts are current: "
        + ", ".join(f"{k} {actual[k]}" for k in (*TIERS, "test"))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
