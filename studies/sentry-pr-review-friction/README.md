# Sentry PR Review Friction Study

Evidence-based analysis of review friction in `getsentry/sentry`. This study collects PR data, analyzes discussion themes from actual comment threads, and proposes ADRs grounded in real evidence.

## Published narrative

The study is published as a multi-page article at:

- [studies.archgate.dev/studies/sentry-pr-review-friction](https://studies.archgate.dev/studies/sentry-pr-review-friction/)

Source files are in `src/content/docs/studies/sentry-pr-review-friction/`.

## Included assets

- `analyze_sentry_prs.py` — Three-phase pipeline: collect, analyze, report
- `theme_dictionary.json` — Externalized keyword definitions for theme coding (auditable)
- `output/` — Generated JSON data artifacts

## Run the methodology

The pipeline has three phases, each producing JSON artifacts in `output/`:

```bash
# Phase 1: Collect PR data + deep comments (~2 min for comment fetching)
python analyze_sentry_prs.py collect --repo getsentry/sentry --days 90 --limit 500

# Phase 2: Analyze collected data (baseline, domain map, themes, predictors)
python analyze_sentry_prs.py analyze

# Phase 3: Generate narrative-ready JSON
python analyze_sentry_prs.py report
```

### Options

```
collect:
  --repo REPO       GitHub repo in owner/name format (default: getsentry/sentry)
  --days DAYS       Trailing days to query (default: 90)
  --limit LIMIT     Max PRs per state (default: 500)
  --top-n TOP_N     Top friction PRs for deep comment analysis (default: 50)
  --delay DELAY     Delay between API calls in seconds (default: 0.5)
```

### Requirements

- Python 3.11+
- GitHub CLI (`gh`) authenticated with access to the target repository

## Methodology notes

- Source of truth is GitHub API via `gh pr list` and `gh api`
- Three PR cohorts: merged, closed-unmerged, open
- Deep comment analysis fetches issue comments, review bodies, and inline review comments for top-N friction PRs
- Friction score is a composite of normalized review events + normalized TTM
- Theme coding uses keyword matching against an externalized dictionary (no LLM in the pipeline)
- Bot comments and automated messages (CI reports, Linear links) are filtered from theme analysis
- All approach choices are intentionally simple and auditable
