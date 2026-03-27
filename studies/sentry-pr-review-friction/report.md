# Study: Sentry PR Friction and ADR Standardization

## Objective

Identify where review back-and-forth concentrates in `getsentry/sentry` and propose ADRs/rules that standardize recurring debate topics.

## Scope

- Window: last 90 days
- Sample: up to 500 merged PRs
- Metrics: review events, merge latency, file count, churn
- Deep-dive: highest-friction PRs by review volume and latency

## Baseline (from 90-day run)

- Median time-to-merge: `4.12h`
- p75/p90 time-to-merge: `21.87h / 69.71h`
- Median review events per PR: `2` (mean `3.19`)
- Formal `CHANGES_REQUESTED`: `1%`
- Small PR median TTM: `2.07h`
- Large PR median TTM: `21.44h`

### Coverage caveat

This baseline is merge-biased and misses two important cohorts:

- PRs with high discussion that were closed unmerged
- Open PRs with significant discussion that became stale

## Missing-signal extension: abandoned and stale PRs

### Closed-unmerged traction

- Queried: 500 closed-unmerged PRs (API list cap)
- Median discussion volume: `2`
- High-discussion abandoned share (`>=10` discussion items): `2.4%`

High-traction closed-unmerged examples:

- https://github.com/getsentry/sentry/pull/109150
- https://github.com/getsentry/sentry/pull/108406
- https://github.com/getsentry/sentry/pull/109526
- https://github.com/getsentry/sentry/pull/111112

### Open stale traction

- Open PRs sampled: `286`
- Stale 14+ days: `36`
- Stale 30+ days: `9`

Examples:

- https://github.com/getsentry/sentry/pull/108533
- https://github.com/getsentry/sentry/pull/109781

### Why this matters

Merged-only studies can make governance look healthier than it is. Tracking abandoned high-discussion PRs and stale high-discussion PRs exposes hidden decision debt and unresolved consensus points.

## High-friction examples

- https://github.com/getsentry/sentry/pull/111160
- https://github.com/getsentry/sentry/pull/111192
- https://github.com/getsentry/sentry/pull/111306
- https://github.com/getsentry/sentry/pull/111454
- https://github.com/getsentry/sentry/pull/110956

## Recurring discussion themes

- API contract and compatibility
- Type/nullability and error paths
- UI flow invariants and behavior semantics
- Test evidence expectations
- Reliability and permission guardrails

## Proposed ADR pack

1. PR Slice Boundaries and Risk Budget
2. API Contract Evolution Protocol
3. Test Evidence Matrix by Change Type
4. UI/Flow Behavioral Invariants
5. Permission and Reliability Guardrails

## Why Archgate fits

These topics are repeated decision classes, not one-off implementation details. ADRs can encode each decision and rules can enforce them pre-review, reducing repetitive reviewer negotiation.
