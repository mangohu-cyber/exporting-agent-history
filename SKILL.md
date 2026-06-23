---
name: exporting-agent-history
description: Use when local agent or Codex conversation history must be exported, sanitized, organized by year/month/week/day, summarized, or prepared as safe input for development retrospectives.
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
   - Destination is usually `<AGENTS_HOME>/data/exporting-agent-history/raw-history`.
2. Run `scripts/export_agent_history.py`.
3. Confirm `export-stats.json`, `manifest.md`, and hierarchy folders exist.
4. Use the default hierarchy grouping unless the user explicitly asks for a single-level export.
5. Run the script again with `--check-only` against the export destination.
6. Use the generated group summary for the period being reviewed.
7. Feed only sanitized Markdown, summaries, manifest, and stats into retrospective work.

Default summary tags come from `references/tag-rules.json`. Use `--tag-rules` only when a specific review needs a temporary tag set.

## Script

Run help before first use:

```bash
python scripts/export_agent_history.py --help
```

Typical export:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<AGENTS_HOME>/data/exporting-agent-history/raw-history"
```

Default output is hierarchical:

```text
<EXPORT_ROOT>/
  YYYY/
    YYYY-MM/
      YYYY-Www/
        YYYY-MM-DD/
          rollout-*.md
          summary.tsv
```

Single-level export, when explicitly needed:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --group-by month
```

Other single-level choices are `year`, `week`, and `day`. Week uses ISO week, Monday start.

Limit source sessions to months before grouping:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --month 2026-03 --month 2026-04
```

Limit exported hierarchy periods after grouping:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --period 2026-03
```

Hierarchy `--period` accepts a year, month, ISO week, day, or full relative path.

Single-level period filtering:

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

Custom tag rules:

```bash
python scripts/export_agent_history.py \
  --source "<CODEX_HOME>/sessions" \
  --dest "<EXPORT_ROOT>" \
  --tag-rules "<PATH_TO_TAG_RULES_JSON>"
```

## Output Contract

The export directory must contain:

```text
<EXPORT_ROOT>/
  manifest.md
  export-stats.json
  YYYY/
    YYYY-MM/
      YYYY-Www/
        YYYY-MM-DD/
          rollout-*.md
          summary.tsv
```

Group names:

- `hierarchy`: `YYYY/YYYY-MM/YYYY-Www/YYYY-MM-DD`
- `year`: `YYYY`
- `month`: `YYYY-MM`
- `week`: `YYYY-Www` using ISO week, Monday start
- `day`: `YYYY-MM-DD`

Single-level exports write `GROUP/rollout-*.md` and `GROUP-summary.tsv`.

Markdown sessions must include only user and assistant messages. System, developer, tool, and event records are not review material.

`summary.tsv` tags should remain broad review cues, not final conclusions. The default tag set covers debug, requirements, state/cache, map/UI, build/verify, workflow/skill, multi-end requirements, and document/PDF work.

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
- Paths to manifest, stats, and relevant period summaries.

Do not provide raw snippets unless the user explicitly asks and the content is confirmed non-sensitive.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Printing matched sensitive lines | Report match counts only. |
| Reviewing raw sessions directly | Export and sanitize first. |
| Trusting keyword summaries without role-count checks | Verify role totals against `export-stats.json`. |
| Letting public project instructions dominate statistics | Filter common prefixes before retrospective analysis. |
| Writing absolute local paths in skill docs | Use placeholders such as `<AGENTS_HOME>`. |
