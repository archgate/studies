---
id: GEN-001
title: PR Scope Boundaries and Size Budget
domain: general
rules: true
files: ["**/*"]
---

## Context

Analysis of 500 merged PRs in `getsentry/sentry` over a 90-day window (see the [Sentry PR Friction study](https://studies.archgate.dev/studies/sentry-pr-review-friction/baseline/)) shows that PR size is the strongest predictor of review friction:

- **Small PRs** (≤3 files, ≤80 churn): median TTM 1.66h, median 1 review event, 12.6% high-friction rate
- **Large PRs** (≥10 files OR ≥400 churn): median TTM 22.52h, median 5 review events, **57.4% high-friction rate**

Large PRs are 13.6x slower to merge and 4.6x more likely to land in the high-friction quartile. Feature PRs (`feat`) compound this — they hit 38.6% high friction vs 17.6% for fix PRs.

The [abandoned PR analysis](https://studies.archgate.dev/studies/sentry-pr-review-friction/abandoned/) further shows that abandoned high-discussion PRs and merged high-friction PRs have the same median file count (4 files). The friction comes from approach disagreement bundled into a single review surface, not from size alone — but size makes bundling more likely.

**Alternatives considered:**

- **Hard line-count limit (e.g., reject PRs > 500 LOC)** — A hard block on size has been used by other organizations (Google's mondrian, some Linux subsystems). It eliminates mega-PRs but also blocks legitimately large changes (migrations, codegen, large refactors). The friction of arguing for an exemption can be worse than the friction of reviewing the large PR.
- **Reviewer-assigned size labels (S/M/L/XL)** — Labels are a common pattern but require manual triage, drift over time, and don't change reviewer behavior on their own. They're a measurement, not a control.
- **Stack-based PRs (Graphite, ghstack)** — Splitting PRs into a stack of dependent commits is the most architecturally sound solution but requires tool adoption and team workflow change. Worth considering as a follow-up but out of scope for an ADR.

The chosen approach is a **soft warning with mandatory rationale**. PRs over the threshold are not blocked, but the author must explain why the change can't be split. This preserves flexibility for genuinely large changes while creating friction (the rationale itself) for unjustified bundling.

## Decision

PRs SHOULD stay within these soft size limits:

| Dimension | Soft Limit | Source |
|-----------|------------|--------|
| Files changed | **≤5** | Median is 2; soft limit at the 75th percentile |
| Churn (added + deleted lines) | **≤200** | Median is 51; soft limit at the 75th-80th percentile |
| Logical changes per PR | **1** | One feature, one refactor, or one fix |

PRs exceeding either dimension MUST include a "Scope Rationale" section in the PR description explaining why the change cannot be split.

PRs exceeding the **hard threshold** (≥10 files OR ≥400 churn) — the empirical "large PR" cutoff from the study data — trigger a CI warning regardless of rationale, surfacing the size signal to reviewers.

## Do's and Don'ts

### Do

- Keep PRs to a single logical change — one feature, one refactor, or one fix
- Aim for ≤5 files and ≤200 churn lines per PR
- Include a "Scope Rationale" section in the PR description when exceeding the soft limits, explaining specifically why the change can't be split
- Split mechanically large changes (renames, codegen output) into a separate PR from the logic changes that depend on them
- For features that span backend and frontend, open paired PRs (one backend, one frontend) rather than a single combined PR
- Use draft PRs to share work-in-progress for early feedback before the PR is review-ready

### Don't

- Don't bundle a refactor with a new feature in the same PR — they have different review concerns
- Don't combine an unrelated bug fix with feature work because "it was small and I noticed it"
- Don't justify a large PR with "the changes are all related" without explaining why they couldn't be sequenced
- Don't use the size warning as a reason to suppress the rule — fix the size, or write the rationale
- Don't open a 1000+ churn PR without first discussing the approach in a design doc, RFC, or Linear ticket

## Implementation Pattern

### Good Example

```markdown
## Summary
Add `defaultCodingAgent` org-level setting with three valid values:
`seer`, `cursor`, `claude`.

## Test plan
- Unit test: org option round-trip for each valid value
- Integration test: API rejects invalid values with 400

## Files (4)
- src/sentry/options/defaults.py — register the option
- src/sentry/api/serializers/organization.py — expose in serializer
- tests/sentry/api/test_organization.py — test coverage
- src/sentry/types/coding_agent.py — typed enum
```

### Bad Example

```markdown
## Summary
Add coding agent settings, fix unrelated migration bug, refactor
seer/handoff.py, and update test fixtures.

## Files (23, 612 churn)
[no scope rationale]
```

The bad example bundles four logical changes into a single PR. Each one would be reviewable in isolation; together they create a 23-file review surface with no clear scope. The reviewer cannot give a focused approval to the coding agent feature without also approving the migration fix and the refactor.

### Scope Rationale Example

```markdown
## Scope Rationale
This PR exceeds the 5-file/200-churn soft limit because it adds a new
serializer field (`defaultCodingAgent`) that requires coordinated changes
to the option registry, the serializer, the model migration, and the
test fixtures. Splitting the migration from the serializer would leave
the option registered but unreadable in production for the duration of
the deployment. The 8 files and 247 churn are the minimum coordinated
change.
```

A good rationale identifies the specific coupling that prevents splitting, not just "the changes are related."

## Consequences

### Positive

- **Reviewer attention is bounded** — A 5-file PR fits in working memory; a 25-file PR does not
- **Rationale section forces scope reflection** — The author must articulate why bundling is necessary, which often surfaces opportunities to split
- **Soft limits preserve flexibility** — Mechanical changes (renames, codegen) and coordinated multi-file changes (migrations + readers) can still ship as single PRs with justification
- **Hard threshold creates a visible signal** — Reviewers see the warning and adjust their review depth accordingly

### Negative

- **Splitting takes author time** — Some changes that could ship as one PR require sequencing as two, adding round-trip latency
- **Stack-based workflows require tooling** — Without `ghstack` or similar, splitting PRs into dependent stacks is manual and error-prone

### Risks

- **Authors gaming the limit** — A PR with 4 files at 199 churn is technically "small" but may still be a large logical change. Mitigation: the rule reports both dimensions and the soft limit applies a secondary check on logical scope.
- **Mechanical changes triggering false positives** — Codegen output, migration files, and snapshot test updates can inflate file count without adding review burden. Mitigation: the rule excludes paths matching `tests/snapshots/**`, `*.lock`, and `migrations/0*.py` from the file count.

## Compliance and Enforcement

### Automated Enforcement

- **Archgate rule** `GEN-001/pr-size-warning`: Computes the file count and churn from `git diff` against the merge base. Excludes snapshot, lock, and auto-generated migration files. Warns when soft limit exceeded; emits an info-level signal at the hard threshold (≥10 files or ≥400 churn). Severity: `warning`.
- **Archgate rule** `GEN-001/scope-rationale-required`: When the PR diff exceeds the soft limit, checks for a "## Scope Rationale" section in the PR description (`.git/PR_DESCRIPTION` or via the GitHub Actions context). Severity: `error`.

### Manual Enforcement

Code reviewers MUST verify:

1. PRs over the soft limit have a meaningful scope rationale (not just "related changes")
2. PRs that bundle a refactor with a new feature are split before review
3. The "single logical change" guideline is honored — one PR title should describe the whole PR

## References

- [Sentry PR Friction Study — Baseline Metrics](https://studies.archgate.dev/studies/sentry-pr-review-friction/baseline/)
- [Sentry PR Friction Study — Abandoned PRs](https://studies.archgate.dev/studies/sentry-pr-review-friction/abandoned/)
- [GEN-002 Test Evidence Matrix](./GEN-002-test-evidence-matrix.md) — Companion ADR for per-change-type test expectations
