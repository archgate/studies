# Sentry PR Review Friction Study

This study analyzes 90 days of merged pull requests in `getsentry/sentry` to quantify review friction and propose ADR/rule candidates that can reduce repeated review debate.

## Included assets

- `analyze_sentry_prs.py` - reproducible data collection and aggregation script
- `report.md` - human-readable findings and proposed ADR pack
- `output/` - generated JSON metrics snapshots

## Run the methodology

```bash
python studies/sentry-pr-review-friction/analyze_sentry_prs.py --repo getsentry/sentry --days 90 --limit 500
```

## Methodology notes

- Source of truth is GitHub API via `gh pr list`.
- Review friction uses review events, merge latency, and PR size segmentation.
- High-friction candidates are selected by review-event volume and merge latency.
- This approach is intentionally simple so peers can audit and challenge assumptions.
