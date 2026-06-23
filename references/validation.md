# Validation Notes

Use a synthetic fixture before running on real history. The fixture should include:

- A user message with a token-like string.
- An assistant message with normal content.
- A developer/system/tool record that must not appear in Markdown output.
- At least two months when testing hierarchy grouping.

Expected checks:

- `scripts/validate_export_agent_history.py` passes.
- `--dry-run` reports sourceFiles, matchedFiles, matchedGroups, destinationExists, and destinationHasExistingFiles without creating output files.
- Export refuses to write into a non-empty destination unless `--clean-dest` is passed.
- `--clean-dest` replaces the destination contents before export.
- `export-stats.json` includes an `options` object with groupBy, months, periods, tagRules, and cleanDest.
- Exported Markdown contains only `## user` and `## assistant` sections.
- `manifest.md` and `export-stats.json` exist.
- `summary.tsv` exists in hierarchy leaf directories.
- `--check-only` prints `sensitivePatternMatches=0`.
- The script output reports redactions greater than zero for the fixture.
- Default export creates hierarchy groups such as `2026/2026-01/2026-W01/2026-01-02`.
- `--group-by year` creates groups such as `2026`.
- `--group-by month` creates groups such as `2026-01`.
- `--group-by week` creates ISO week groups such as `2026-W01`.
- `--group-by day` creates groups such as `2026-01-02`.
- `summary.tsv` tags include configured categories from `references/tag-rules.json` when fixture content matches them.
- `failedFiles` entries include file, stage, errorType, and message when a source file cannot be exported.
