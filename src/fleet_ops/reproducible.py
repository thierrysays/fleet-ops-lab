"""Did the build produce the same bytes twice, and if not, which file changed.

Reproducibility is usually presented as a supply-chain security property, which
it is. It is more immediately an operations property: without it, "the version
in the field differs from the version in the repository" is unanswerable, and
every field incident begins with an argument about what is actually deployed.

The check is unglamorous (hash every file in two build outputs, compare the
maps) and the value is entirely in the report. "Not reproducible" is useless.
"``build/timestamp.txt`` and ``lib/foo.so`` differ, the rest match" is a
morning's work, and usually turns out to be an embedded build date, an absolute
path, or a directory iteration order.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Files that differ between builds for reasons nobody intends to fix, and that
#: a first pass should be able to set aside without pretending they matched.
COMMON_NON_DETERMINISM = (
    "embedded build timestamp",
    "absolute path baked into a binary",
    "archive member order",
    "hash-seed-dependent iteration order",
    "compiler temporary file name",
)


@dataclass(frozen=True, slots=True)
class ReproVerdict:
    """Two builds compared, file by file."""

    reproducible: bool
    matched: tuple[str, ...]
    differing: tuple[str, ...]
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]

    @property
    def summary(self) -> str:
        if self.reproducible:
            return f"reproducible: {len(self.matched)} file(s) identical"
        parts = []
        if self.differing:
            parts.append(f"{len(self.differing)} file(s) differ")
        if self.only_in_a:
            parts.append(f"{len(self.only_in_a)} only in the first build")
        if self.only_in_b:
            parts.append(f"{len(self.only_in_b)} only in the second")
        return "not reproducible: " + ", ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "fleet-ops/repro-verdict/v1",
            "reproducible": self.reproducible,
            "matched": list(self.matched),
            "differing": list(self.differing),
            "only_in_a": list(self.only_in_a),
            "only_in_b": list(self.only_in_b),
            "summary": self.summary,
        }


def digest_tree(root: str | Path, exclude: tuple[str, ...] = ()) -> dict[str, str]:
    """Map every file under ``root`` to its digest, keyed by relative path.

    Sorted output, POSIX separators: a build-output map whose order depends on
    the filesystem is a map that compares unequal to itself on another machine.
    """
    base = Path(root)
    out: dict[str, str] = {}
    for path in sorted(p for p in base.rglob("*") if p.is_file()):
        rel = path.relative_to(base).as_posix()
        if any(part in rel for part in exclude):
            continue
        out[rel] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(out.items()))


def compare_builds(a: Mapping[str, str], b: Mapping[str, str]) -> ReproVerdict:
    """Compare two build-output maps and name every file that differs."""
    keys_a, keys_b = set(a), set(b)
    both = keys_a & keys_b
    matched = tuple(sorted(k for k in both if a[k] == b[k]))
    differing = tuple(sorted(k for k in both if a[k] != b[k]))
    only_a = tuple(sorted(keys_a - keys_b))
    only_b = tuple(sorted(keys_b - keys_a))
    return ReproVerdict(
        reproducible=not (differing or only_a or only_b),
        matched=matched,
        differing=differing,
        only_in_a=only_a,
        only_in_b=only_b,
    )
