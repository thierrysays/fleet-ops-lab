"""Deterministic bytes, for anything that gets hashed or compared.

A manifest digest, an SBOM digest and a reproducibility verdict all depend on
two objects that should be equal serialising identically. Sorted keys, compact
separators, non-finite floats refused.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _reject_non_finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite float {value!r} cannot be canonicalised")
    if isinstance(value, dict):
        return {k: _reject_non_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_reject_non_finite(v) for v in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(
        _reject_non_finite(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()
