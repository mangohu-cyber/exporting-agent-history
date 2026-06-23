---
name: exporting-agent-history
description: Use when local agent or Codex conversation history must be exported, sanitized, grouped by month, summarized, or prepared as safe input for development retrospectives.
---

# Exporting Agent History

## Overview

Export local agent history into sanitized review inputs. The goal is a reproducible evidence pipeline: no raw secrets, no system/developer noise, and no retrospective built from unchecked data.

## Required Boundary

Before running exports, state the source, destination, grouping rule, and time scope. Do not print raw conversation lines while inspecting history; report counts, file names, and validation results only.

Use placeholders in documentation and examples:

- `<CODEX_HOME>` for the Codex data root.
- `<AGENTS_HOME>` for the agent data root.
- `<EXPORT_ROOT>` for the chosen export destination.

Do not write machine-specific absolute paths into skill docs or generated guidance.

## Standard Workflow

1. Choose source and destination.
   - Source is usually `<CODEX_HOME>/sessions`.
   - Destination is usually `<AGENTS_HOME>/development-learning/raw-history`.
2. Run `scripts/export_agent_history.py`.
3. Confirm `export-stats.json`, `manifest.md`, and month folders exist.
4. Choose `--group-by month`, `--group-by week`, or `--group-by day`. Default is `month`.
5. Run the script again with `--check-only` against the export destination.
6. Use the generated group summary for the period being reviewed.
7. Feed only sanitized Markdown, summaries, manifest, and stats into retrospective work.

## Script

Run help before first use:

```bash
python scripts/export_agent_history.py --help
```

Typical export:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<AGENTS_HOME>/development-learning/raw-history"
```

Group by ISO week:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --group-by week
```

Group by day:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --group-by day
```

Limit source sessions to months before grouping:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --month 2026-03 --month 2026-04
```

Limit exported groups after applying `--group-by`:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --group-by week \
  --period 2026-W12
```

Validation only:

```bash
python scripts/export_agent_history.py --dest "<EXPORT_ROOT>" --check-only
```

## Output Contract

The export directory must contain:

```text
<EXPORT_ROOT>/
  manifest.md
  export-stats.json
  GROUP/
    rollout-*.md
  GROUP-summary.tsv
```

Group names:

- `month`: `YYYY-MM`
- `week`: `YYYY-Www` using ISO week, Monday start
- `day`: `YYYY-MM-DD`

Markdown sessions must include only user and assistant messages. System, developer, tool, and event records are not review material.

## Data Rules

- Redact before writing exported Markdown.
- Redact common API keys, bearer tokens, JWT-like strings, cloud access keys, emails, phone numbers, private IPs, and obvious credential assignments.
- Count redactions in `export-stats.json`.
- Treat nonzero sensitive matches after export as a failure. Do not inspect by printing matching raw lines.
- Preserve source files. Never modify the original session directory.

## Retrospective Handoff

When handing data to `development-learning`, provide:

- Month and file counts.
- Message counts by role.
- Redaction counts.
- Sensitive scan result.
- Paths to manifest, stats, and monthly summary.

Do not provide raw snippets unless the user explicitly asks and the content is confirmed non-sensitive.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Printing matched sensitive lines | Report match counts only. |
| Reviewing raw sessions directly | Export and sanitize first. |
| Trusting keyword summaries without role-count checks | Verify role totals against `export-stats.json`. |
| Letting public project instructions dominate statistics | Filter common prefixes before retrospective analysis. |
| Writing absolute local paths in skill docs | Use placeholders such as `<AGENTS_HOME>`. |
