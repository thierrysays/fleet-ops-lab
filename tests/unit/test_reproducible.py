"""Comparing two build outputs, and naming what moved."""

from pathlib import Path

from fleet_ops.reproducible import compare_builds, digest_tree


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


def test_identical_trees_are_reproducible(tmp_path):
    files = {"bin/agent": "ELF...", "lib/foo.so": "SO..."}
    a = _tree(tmp_path / "a", files)
    b = _tree(tmp_path / "b", files)
    verdict = compare_builds(digest_tree(a), digest_tree(b))
    assert verdict.reproducible is True
    assert len(verdict.matched) == 2


def test_a_differing_file_is_named_rather_than_summarised(tmp_path):
    # "Not reproducible" is useless. The path is the whole deliverable.
    a = _tree(tmp_path / "a", {"bin/agent": "ELF", "build/stamp.txt": "2026-08-21"})
    b = _tree(tmp_path / "b", {"bin/agent": "ELF", "build/stamp.txt": "2026-08-22"})
    verdict = compare_builds(digest_tree(a), digest_tree(b))
    assert verdict.reproducible is False
    assert verdict.differing == ("build/stamp.txt",)
    assert verdict.matched == ("bin/agent",)


def test_a_file_present_in_only_one_build_is_reported_on_its_own_side(tmp_path):
    a = _tree(tmp_path / "a", {"bin/agent": "ELF", "bin/leftover.o": "junk"})
    b = _tree(tmp_path / "b", {"bin/agent": "ELF"})
    verdict = compare_builds(digest_tree(a), digest_tree(b))
    assert verdict.only_in_a == ("bin/leftover.o",)
    assert verdict.only_in_b == ()
    assert "only in the first build" in verdict.summary


def test_excluded_paths_are_skipped_rather_than_pretended_to_match(tmp_path):
    a = _tree(tmp_path / "a", {"bin/agent": "ELF", "build/stamp.txt": "one"})
    b = _tree(tmp_path / "b", {"bin/agent": "ELF", "build/stamp.txt": "two"})
    verdict = compare_builds(
        digest_tree(a, exclude=("stamp.txt",)), digest_tree(b, exclude=("stamp.txt",))
    )
    assert verdict.reproducible is True
    assert "build/stamp.txt" not in verdict.matched


def test_the_digest_map_is_sorted_and_uses_posix_separators(tmp_path):
    root = _tree(tmp_path / "a", {"z/last": "1", "a/first": "2"})
    keys = list(digest_tree(root))
    assert keys == sorted(keys)
    assert all("\\" not in k for k in keys)
