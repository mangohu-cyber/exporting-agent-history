#!/usr/bin/env python3
"""Validate the exporting-agent-history skill with synthetic fixtures."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_command(args: list[str], expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True)
    if expect_success and result.returncode != 0:
        raise AssertionError(f"Command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    if not expect_success and result.returncode == 0:
        raise AssertionError(f"Command unexpectedly succeeded: {' '.join(args)}\n{result.stdout}")
    return result


def copy_fixtures(skill_root: Path, source: Path) -> None:
    fixtures = skill_root / "references" / "test-fixtures"
    shutil.copy2(fixtures / "sample-2026-01.jsonl", source / "sample-2026-01.jsonl")
    shutil.copy2(fixtures / "sample-2026-02.json", source / "sample-2026-02.json")


def read_stats(dest: Path) -> dict:
    return json.loads((dest / "export-stats.json").read_text(encoding="utf-8"))


def assert_contains(text: str, expected: str) -> None:
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in output:\n{text}")


def validate_export_flow(skill_root: Path, script: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-history-validate-") as temp:
        root = Path(temp)
        source = root / "source"
        dest = root / "out"
        source.mkdir()
        copy_fixtures(skill_root, source)

        dry_run = run_command([sys.executable, str(script), "--source", str(source), "--dest", str(dest), "--dry-run"])
        assert_contains(dry_run.stdout, "sourceFiles=2")
        assert_contains(dry_run.stdout, "matchedFiles=2")
        assert_contains(dry_run.stdout, "matchedGroups=2")
        if dest.exists():
            raise AssertionError("--dry-run created the destination directory")

        export = run_command([sys.executable, str(script), "--source", str(source), "--dest", str(dest)])
        assert_contains(export.stdout, "exportedFiles=2")
        assert_contains(export.stdout, "redactions=1")
        assert_contains(export.stdout, "sensitivePatternMatches=0")

        check = run_command([sys.executable, str(script), "--dest", str(dest), "--check-only"])
        assert_contains(check.stdout, "sensitivePatternMatches=0")

        stats = read_stats(dest)
        if stats["totalMessages"] != 4:
            raise AssertionError("Expected totalMessages=4")
        if stats["options"]["cleanDest"] is not False:
            raise AssertionError("Expected cleanDest=false for normal export")

        summaries = "\n".join(path.read_text(encoding="utf-8") for path in dest.rglob("summary.tsv"))
        assert_contains(summaries, "debug,build-verify")
        assert_contains(summaries, "state-cache,map-ui,workflow-skill")


def validate_destination_safety(skill_root: Path, script: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-history-safety-") as temp:
        root = Path(temp)
        source = root / "source"
        dest = root / "out"
        source.mkdir()
        dest.mkdir()
        copy_fixtures(skill_root, source)
        old_file = dest / "old.txt"
        old_file.write_text("old", encoding="utf-8")

        blocked = run_command([sys.executable, str(script), "--source", str(source), "--dest", str(dest)], expect_success=False)
        assert_contains(blocked.stderr + blocked.stdout, "--dest is not empty")
        if not old_file.exists():
            raise AssertionError("Blocked export removed old file")

        clean = run_command([sys.executable, str(script), "--source", str(source), "--dest", str(dest), "--clean-dest"])
        assert_contains(clean.stdout, "exportedFiles=2")
        if old_file.exists():
            raise AssertionError("--clean-dest did not remove old file")
        stats = read_stats(dest)
        if stats["options"]["cleanDest"] is not True:
            raise AssertionError("Expected cleanDest=true after --clean-dest")


def validate_failure_shape(script: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-history-failure-") as temp:
        root = Path(temp)
        source = root / "source"
        dest = root / "out"
        source.mkdir()
        (source / "bad.json").write_text('[{"timestamp":"2026-01-01T00:00:00Z",', encoding="utf-8")
        run_command([sys.executable, str(script), "--source", str(source), "--dest", str(dest)])
        stats = read_stats(dest)
        failed = stats["failedFiles"]
        if not failed:
            raise AssertionError("Expected failedFiles entry for malformed JSON")
        for key in ("file", "stage", "errorType", "message"):
            if key not in failed[0]:
                raise AssertionError(f"failedFiles entry missing {key}")


def main() -> int:
    skill_root = Path(__file__).resolve().parent.parent
    script = skill_root / "scripts" / "export_agent_history.py"
    validate_export_flow(skill_root, script)
    validate_destination_safety(skill_root, script)
    validate_failure_shape(script)
    print("exporting-agent-history validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
