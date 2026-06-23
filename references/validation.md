# Validation Notes

Use a synthetic fixture before running on real history. The fixture should include:

- A user message with a token-like string.
- An assistant message with normal content.
- A developer/system/tool record that must not appear in Markdown output.
- At least two months when testing month grouping.

Expected checks:

- Exported Markdown contains only `## user` and `## assistant` sections.
- `manifest.md` and `export-stats.json` exist.
- `GROUP-summary.tsv` exists for exported groups.
- `--check-only` prints `sensitivePatternMatches=0`.
- The script output reports redactions greater than zero for the fixture.
- `--group-by month` creates groups such as `2026-01`.
- `--group-by week` creates ISO week groups such as `2026-W01`.
- `--group-by day` creates groups such as `2026-01-02`.
