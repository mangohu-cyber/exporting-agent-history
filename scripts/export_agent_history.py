#!/usr/bin/env python3
"""Export local agent conversation history into sanitized review inputs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROLE_ALLOWLIST = {"user", "assistant"}
SOURCE_FORMATS = ("codex", "claude")


REDACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_ghp", re.compile(r"ghp_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("cn_phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("private_ip", re.compile(r"(?<!\d)(?:10|172\.(?:1[6-9]|2\d|3[0-1])|192\.168)\.\d{1,3}\.\d{1,3}(?!\d)")),
    ("credential_assignment", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key)\b\s*[:=]\s*[^\s`'\"<>]+")),
]


COMMON_PREFIX_PATTERNS = [
    re.compile(r"<agents-instructions>.*?</agents-instructions>", re.IGNORECASE | re.DOTALL),
    re.compile(r"# AGENTS\.md instructions.*?</INSTRUCTIONS>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<environment_context>.*?</environment_context>", re.IGNORECASE | re.DOTALL),
    re.compile(r"# Project Instructions \(root\).*?(?=## user|## assistant|\Z)", re.IGNORECASE | re.DOTALL),
]


@dataclass
class GroupStats:
    files: int = 0
    messages: int = 0
    user: int = 0
    assistant: int = 0
    redactions: int = 0


@dataclass
class ExportStats:
    source: str
    destination: str
    generated_at: str
    group_by: str
    options: dict[str, Any] = field(default_factory=dict)
    total_session_files: int = 0
    exported_markdown_files: int = 0
    failed_files: list[dict[str, str]] = field(default_factory=list)
    total_messages: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    redactions: int = 0
    groups: dict[str, GroupStats] = field(default_factory=dict)


@dataclass(frozen=True)
class TagRule:
    pattern: re.Pattern[str]
    min_hits: int


def default_tag_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "tag-rules.json"


def load_tag_patterns(path: Path | None) -> dict[str, TagRule]:
    rules_path = path or default_tag_rules_path()
    try:
        loaded = json.loads(rules_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"无法读取标签规则文件: {rules_path} ({error})") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"标签规则文件不是有效 JSON: {rules_path} ({error})") from error
    if not isinstance(loaded, dict) or not loaded:
        raise ValueError(f"标签规则文件必须是非空对象: {rules_path}")

    patterns: dict[str, TagRule] = {}
    for name, rule in loaded.items():
        if not isinstance(rule, dict):
            raise ValueError(f"标签规则必须包含 pattern 和 minHits: {name}")
        pattern = rule.get("pattern")
        min_hits = rule.get("minHits")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"标签规则 pattern 必须是非空字符串: {name}")
        if not isinstance(min_hits, int) or min_hits < 1:
            raise ValueError(f"标签规则 minHits 必须是正整数: {name}")
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"标签规则正则无效: {name} ({error})") from error
        patterns[str(name)] = TagRule(pattern=compiled, min_hits=min_hits)
    return patterns


def match_tags(text: str, tag_patterns: dict[str, TagRule]) -> set[str]:
    return {
        name
        for name, rule in tag_patterns.items()
        if sum(1 for _ in rule.pattern.finditer(text)) >= rule.min_hits
    }


def redact_text(text: str) -> tuple[str, int]:
    redactions = 0
    result = text
    for name, pattern in REDACTION_PATTERNS:
        result, count = pattern.subn(f"[REDACTED:{name}]", result)
        redactions += count
    return result, redactions


def strip_common_prefix(text: str) -> str:
    result = text
    for pattern in COMMON_PREFIX_PATTERNS:
        result = pattern.sub("", result)
    return result


def iter_json_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        first = handle.read(1)
        handle.seek(0)
        if first == "[":
            data = json.load(handle)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        yield item
            return
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item


def extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(extract_text(item.get("text") or item.get("content") or item.get("value")))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if "text" in value:
            return extract_text(value["text"])
        if "content" in value:
            return extract_text(value["content"])
        if "value" in value:
            return extract_text(value["value"])
    return ""


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    if isinstance(payload, dict):
        return payload
    item = record.get("item")
    if isinstance(item, dict):
        return item
    return record


def role_from_payload(item: dict[str, Any]) -> str | None:
    role = item.get("role")
    if role in ROLE_ALLOWLIST:
        return str(role)
    item_type = item.get("type")
    if item_type == "user_message":
        return "user"
    if item_type == "agent_message":
        return "assistant"
    return None


def extract_codex_message(record: dict[str, Any]) -> tuple[str, str] | None:
    item = normalize_record(record)
    role = role_from_payload(item)
    if not role:
        return None
    text = extract_text(item.get("content") or item.get("text") or record.get("content") or record.get("text"))
    if not text.strip():
        return None
    return role, text.strip()


def extract_claude_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append(extract_text(item.get("text")))
    return "\n".join(part for part in parts if part)


def extract_claude_message(record: dict[str, Any]) -> tuple[str, str] | None:
    if record.get("type") not in ROLE_ALLOWLIST:
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if role not in ROLE_ALLOWLIST:
        return None
    text = extract_claude_text(message.get("content"))
    if not text.strip():
        return None
    return str(role), text.strip()


def extract_message(record: dict[str, Any], source_format: str) -> tuple[str, str] | None:
    if source_format == "claude":
        return extract_claude_message(record)
    return extract_codex_message(record)


def date_from_record_or_path(path: Path, records: list[dict[str, Any]]) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if match:
        return match.group(1)
    for record in records:
        for key in ("timestamp", "created_at", "time"):
            value = record.get(key)
            if isinstance(value, str):
                match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
                if match:
                    return match.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def date_group_parts(date_text: str) -> dict[str, str]:
    parsed = datetime.strptime(date_text, "%Y-%m-%d").date()
    iso = parsed.isocalendar()
    return {
        "year": date_text[:4],
        "month": date_text[:7],
        "week": f"{iso.year}-W{iso.week:02d}",
        "day": date_text,
    }


def group_key_from_date(date_text: str, group_by: str) -> str:
    parts = date_group_parts(date_text)
    if group_by == "hierarchy":
        return "/".join([parts["year"], parts["month"], parts["week"], parts["day"]])
    if group_by == "year":
        return parts["year"]
    if group_by == "week":
        return parts["week"]
    if group_by == "day":
        return parts["day"]
    return parts["month"]


def group_dir_from_key(dest: Path, group_key: str) -> Path:
    return dest.joinpath(*group_key.split("/"))


def period_matches(date_text: str, group_by: str, group_key: str, allowed_periods: set[str] | None) -> bool:
    if not allowed_periods:
        return True
    if group_by != "hierarchy":
        return group_key in allowed_periods
    parts = date_group_parts(date_text)
    candidates = set(parts.values())
    candidates.add(group_key)
    return bool(candidates & allowed_periods)


def markdown_name(path: Path, date: str) -> str:
    stem = path.stem
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "session"
    if date not in safe_stem:
        safe_stem = f"{date}-{safe_stem}"
    return f"{safe_stem}.md"


def export_one(path: Path, dest: Path, stats: ExportStats, allowed_periods: set[str] | None, allowed_months: set[str] | None, source_format: str) -> None:
    records = list(iter_json_records(path))
    date = date_from_record_or_path(path, records)
    month = date[:7]
    group_key = group_key_from_date(date, stats.group_by)
    if allowed_months and month not in allowed_months:
        return
    if not period_matches(date, stats.group_by, group_key, allowed_periods):
        return

    messages: list[tuple[str, str]] = []
    redactions = 0
    for record in records:
        message = extract_message(record, source_format)
        if not message:
            continue
        role, text = message
        redacted, count = redact_text(text)
        redactions += count
        messages.append((role, redacted))

    if not messages:
        return

    group_dir = group_dir_from_key(dest, group_key)
    group_dir.mkdir(parents=True, exist_ok=True)
    output_path = group_dir / markdown_name(path, date)

    lines = [f"# Session {date}", "", f"Source file: `{path.name}`", ""]
    for role, text in messages:
        lines.extend([f"## {role}", "", text, ""])
    output_path.write_text("\r\n".join(lines).rstrip() + "\r\n", encoding="utf-8")

    user_count = sum(1 for role, _ in messages if role == "user")
    assistant_count = sum(1 for role, _ in messages if role == "assistant")

    group_stats = stats.groups.setdefault(group_key, GroupStats())
    group_stats.files += 1
    group_stats.messages += len(messages)
    group_stats.user += user_count
    group_stats.assistant += assistant_count
    group_stats.redactions += redactions

    stats.exported_markdown_files += 1
    stats.total_messages += len(messages)
    stats.user_messages += user_count
    stats.assistant_messages += assistant_count
    stats.redactions += redactions


def stats_to_json(stats: ExportStats) -> dict[str, Any]:
    data = {
        "source": stats.source,
        "destination": stats.destination,
        "generatedAt": stats.generated_at,
        "groupBy": stats.group_by,
        "options": stats.options,
        "totalSessionFiles": stats.total_session_files,
        "exportedMarkdownFiles": stats.exported_markdown_files,
        "failedFiles": stats.failed_files,
        "totalMessages": stats.total_messages,
        "userMessages": stats.user_messages,
        "assistantMessages": stats.assistant_messages,
        "redactions": stats.redactions,
        "groups": {
            group: {
                "files": item.files,
                "messages": item.messages,
                "user": item.user,
                "assistant": item.assistant,
                "redactions": item.redactions,
            }
            for group, item in sorted(stats.groups.items())
        },
    }
    if stats.group_by == "month":
        data["months"] = data["groups"]
    return data


def write_manifest(dest: Path, stats: ExportStats) -> None:
    lines = ["# Agent History Export Manifest", "", f"Generated: {stats.generated_at}", ""]
    lines.extend(["## Totals", "", f"- Group by: {stats.group_by}", f"- Files: {stats.exported_markdown_files}", f"- Messages: {stats.total_messages}", f"- Redactions: {stats.redactions}", ""])
    lines.extend(["## Groups", ""])
    for group, item in sorted(stats.groups.items()):
        lines.append(f"- {group}: files={item.files}, messages={item.messages}, user={item.user}, assistant={item.assistant}, redactions={item.redactions}")
    lines.append("")
    (dest / "manifest.md").write_text("\r\n".join(lines), encoding="utf-8")


def write_group_summary(dest: Path, group: str, tag_patterns: dict[str, TagRule]) -> Path:
    group_dir = group_dir_from_key(dest, group)
    output_path = group_dir / "summary.tsv" if "/" in group else dest / f"{group}-summary.tsv"
    rows = ["file\tdate\tuserTurns\tassistantTurns\tbytes\ttags"]
    if not group_dir.exists():
        output_path.write_text("\r\n".join(rows) + "\r\n", encoding="utf-8")
        return output_path

    for file in sorted(group_dir.glob("*.md")):
        text = file.read_text(encoding="utf-8", errors="replace")
        content = strip_common_prefix(text)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", file.name)
        matched_tags = match_tags(content, tag_patterns)
        tags = [name for name in tag_patterns if name in matched_tags]
        rows.append(
            "\t".join(
                [
                    file.name,
                    date_match.group(1) if date_match else "",
                    str(len(re.findall(r"(?m)^##\s+user\s*$", text))),
                    str(len(re.findall(r"(?m)^##\s+assistant\s*$", text))),
                    str(file.stat().st_size),
                    ",".join(tags),
                ]
            )
        )
    output_path.write_text("\r\n".join(rows) + "\r\n", encoding="utf-8")
    return output_path


def scan_sensitive(dest: Path) -> int:
    matches = 0
    for file in dest.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in {".md", ".tsv", ".json"}:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        for _, pattern in REDACTION_PATTERNS:
            matches += len(pattern.findall(text))
    return matches


def collect_session_files(source: Path) -> list[Path]:
    return sorted([p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in {".json", ".jsonl"}])


def destination_has_files(dest: Path) -> bool:
    return dest.exists() and any(dest.iterdir())


def clean_destination(dest: Path) -> None:
    if not dest.exists():
        return
    for child in dest.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def export_options(args: argparse.Namespace, tag_rules_path: Path) -> dict[str, Any]:
    return {
        "sourceFormat": args.source_format,
        "groupBy": args.group_by,
        "months": list(args.month or []),
        "periods": list(args.period or []),
        "tagRules": str(tag_rules_path),
        "cleanDest": bool(args.clean_dest),
    }


def run_dry_run(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()
    session_files = collect_session_files(source)
    allowed_periods = set(args.period or []) or None
    allowed_months = set(args.month or []) or None
    matched_groups: dict[str, int] = {}
    failed_files: list[dict[str, str]] = []

    for path in session_files:
        try:
            records = list(iter_json_records(path))
            date = date_from_record_or_path(path, records)
            month = date[:7]
            group_key = group_key_from_date(date, args.group_by)
            if allowed_months and month not in allowed_months:
                continue
            if not period_matches(date, args.group_by, group_key, allowed_periods):
                continue
            matched_groups[group_key] = matched_groups.get(group_key, 0) + 1
        except Exception as error:
            failed_files.append(
                {
                    "file": path.name,
                    "stage": "dry-run",
                    "errorType": type(error).__name__,
                    "message": str(error),
                }
            )

    existing_output = destination_has_files(dest)
    print(f"source={source}")
    print(f"destination={dest}")
    print(f"sourceFormat={args.source_format}")
    print(f"groupBy={args.group_by}")
    print(f"sourceFiles={len(session_files)}")
    print(f"matchedFiles={sum(matched_groups.values())}")
    print(f"matchedGroups={len(matched_groups)}")
    print(f"destinationExists={dest.exists()}")
    print(f"destinationHasExistingFiles={existing_output}")
    if allowed_months:
        print(f"monthFilter={','.join(sorted(allowed_months))}")
    if allowed_periods:
        print(f"periodFilter={','.join(sorted(allowed_periods))}")
    for group, count in sorted(matched_groups.items()):
        print(f"group={group}\tfiles={count}")
    if failed_files:
        print("failedFiles=" + json.dumps(failed_files, ensure_ascii=False))
    return 1 if failed_files else 0


def run_export(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    dest = Path(args.dest).expanduser().resolve()
    if destination_has_files(dest):
        if not args.clean_dest:
            raise SystemExit("--dest is not empty. Use --dry-run first, then pass --clean-dest to replace it.")
        clean_destination(dest)
    dest.mkdir(parents=True, exist_ok=True)
    tag_rules_path = Path(args.tag_rules).expanduser().resolve() if args.tag_rules else default_tag_rules_path()
    stats = ExportStats(
        source=args.source,
        destination=args.dest,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        group_by=args.group_by,
        options=export_options(args, tag_rules_path),
    )
    session_files = collect_session_files(source)
    stats.total_session_files = len(session_files)
    allowed_periods = set(args.period or []) or None
    allowed_months = set(args.month or []) or None
    try:
        tag_patterns = load_tag_patterns(tag_rules_path)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    for path in session_files:
        try:
            export_one(path, dest, stats, allowed_periods, allowed_months, args.source_format)
        except Exception as error:
            stats.failed_files.append(
                {
                    "file": path.name,
                    "stage": "export",
                    "errorType": type(error).__name__,
                    "message": str(error),
                }
            )

    for group in sorted(stats.groups):
        write_group_summary(dest, group, tag_patterns)
    write_manifest(dest, stats)
    (dest / "export-stats.json").write_text(json.dumps(stats_to_json(stats), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    matches = scan_sensitive(dest)
    print(f"sourceFiles={stats.total_session_files}")
    print(f"exportedFiles={stats.exported_markdown_files}")
    print(f"messages={stats.total_messages}")
    print(f"userMessages={stats.user_messages}")
    print(f"assistantMessages={stats.assistant_messages}")
    print(f"redactions={stats.redactions}")
    print(f"sensitivePatternMatches={matches}")
    return 1 if matches else 0


def run_check(args: argparse.Namespace) -> int:
    dest = Path(args.dest).expanduser().resolve()
    matches = scan_sensitive(dest)
    print(f"sensitivePatternMatches={matches}")
    return 1 if matches else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export and sanitize local agent conversation history.")
    parser.add_argument("--source", help="Source session directory. Required unless --check-only is used.")
    parser.add_argument("--dest", required=True, help="Export destination directory.")
    parser.add_argument("--source-format", choices=SOURCE_FORMATS, default="codex", help="Input history format. Use codex for Codex sessions and claude for Claude Code project JSONL.")
    parser.add_argument("--group-by", choices=("hierarchy", "year", "month", "week", "day"), default="hierarchy", help="Directory grouping rule. hierarchy creates YYYY/YYYY-MM/YYYY-Www/YYYY-MM-DD. week uses ISO week, e.g. 2026-W03.")
    parser.add_argument("--month", action="append", help="Limit source sessions to YYYY-MM before grouping. Can be repeated.")
    parser.add_argument("--period", action="append", help="Limit exported groups after applying --group-by. hierarchy accepts year, month, week, day, or full relative path.")
    parser.add_argument("--tag-rules", help="Optional JSON file mapping tag names to regex patterns. Defaults to references/tag-rules.json beside this skill.")
    parser.add_argument("--clean-dest", action="store_true", help="Clean a non-empty destination before export. Without this flag, export refuses to write into a non-empty destination.")
    parser.add_argument("--dry-run", action="store_true", help="Preview source file count, matched groups, filters, and destination state without writing files.")
    parser.add_argument("--check-only", action="store_true", help="Only scan destination for sensitive patterns.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_only:
        return run_check(args)
    if args.dry_run:
        if not args.source:
            raise SystemExit("--source is required when --dry-run is used")
        return run_dry_run(args)
    if not args.source:
        raise SystemExit("--source is required unless --check-only is used")
    return run_export(args)


if __name__ == "__main__":
    raise SystemExit(main())
