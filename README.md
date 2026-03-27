# Archgate Studies

Reproducible studies on architecture governance, review friction, and ADR-driven standardization.

## Website

The studies website is published at:

- https://studies.archgate.dev

Static site sources are in `site/` and are deployed via GitHub Pages (`.github/workflows/deploy-pages.yml`).

## Studies

- `studies/sentry-pr-review-friction/` - 90-day analysis of pull request back-and-forth in `getsentry/sentry`, with a proposed ADR + rules pack.

## Peer review workflow

Each study should include:

- methodology code
- generated raw metrics output
- assumptions and thresholds
- interpretation notes

Re-run scripts and open pull requests with alternative thresholds or additional validations to challenge findings.
