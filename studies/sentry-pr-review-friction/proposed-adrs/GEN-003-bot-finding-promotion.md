---
id: GEN-003
title: Convert Recurring Bot Findings to Deterministic Rules
domain: general
rules: false
files: []
---

## Context

Sentry runs three automated reviewers on its PRs: `sentry[bot]` (bug prediction), `sentry-warden[bot]` (correctness/security checking), and `cursor[bot]` (Cursor's agentic review). The [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/) found that:

- Bot reviewers account for **23.7%** of substantive review comments
- **68.3%** of high-friction PRs have bot review activity
- The average bot review comment is **1,565 characters** — far longer and more substantive than human review comments
- One PR ([#111689](https://github.com/getsentry/sentry/pull/111689)) had **100% bot reviews and zero human comments**

The bots are not noise — they find real bugs (Pydantic type errors, missing exception handlers, key mismatches, security holes). The problem is that **the same bug categories repeat across different PRs**. The study identified at least 10 recurring patterns, including:

- Missing `Model.DoesNotExist` handling on `.objects.get()` (≥3 PRs)
- `.filter().first()` with unreachable `except DoesNotExist`
- Direct dict access on external API responses
- `str | None` UnionType used as a callable in serializers
- Option key mismatch between writer and reader
- Companion list updates missed (one PR had this finding **4 times** for 4 different lists in a single review pass)
- High-cardinality metric tags
- Form state not reset in error catch blocks

Every recurring pattern is detectable by a deterministic check (Ruff/Semgrep rule, mypy strict mode, ESLint rule, schema validation, or refactor to a typed registry). **Running expensive agentic LLM review on every commit to catch a bug pattern that has already been identified is the wrong tool.** Agentic review is the right tool for *discovering* novel bug shapes; once a pattern recurs, it should graduate to a cheap deterministic check that runs at edit time in the IDE.

**Alternatives considered:**

- **Status quo: keep accepting recurring bot findings** — The study shows this costs roughly 70-140 minutes of cumulative developer attention across just 60 PRs in our sample. Extrapolated to Sentry's full PR volume, the time investment is significant. Beyond cost, the inconsistent triage protocol (some developers respond, some silently ignore) creates ambiguity that itself drives friction.
- **Disable the bots entirely** — Throws away the genuine value of agentic review for first-time pattern discovery and cross-file semantic reasoning. Wrong direction.
- **Bot finding triage protocol** — A previous version of this ADR proposed a workflow for acknowledging and dismissing bot findings (Fixed / False positive / Follow-up / Won't fix). This addresses the symptom (bot comments cluttering PRs) but not the root cause (recurring patterns wastefully re-detected).

The chosen approach is **promotion**: when a bot finding category recurs, commit to writing a deterministic check that catches the pattern before the bot can fire on it. As deterministic coverage grows, the bot's per-PR finding count drops, and its remaining findings shift toward genuinely novel patterns.

## Decision

### 1. Track bot finding categories

Each substantive bot finding is tagged with a category label (manual or semi-automated) — e.g., `missing-doesnotexist-handler`, `direct-dict-access`, `companion-list-miss`. The categories live in a shared tracker (Linear project, GitHub project board, or a markdown registry in `.archgate/`).

### 2. Recurrence triggers promotion

When a category accumulates **≥3 occurrences across distinct PRs within 90 days**, the team commits to evaluating it for promotion to a deterministic check. The recurrence threshold is the trigger — not "is it possible to write a check?" but "is it economically justified yet?"

### 3. Promotion targets

In order of preference:

1. **Static type check** (mypy/pyright strict mode) — for patterns the type system can detect
2. **AST lint rule** (Ruff custom rule, Semgrep pattern, ESLint rule) — for patterns that are syntactically detectable
3. **Schema/registry validation** (typed enum for option keys, single-source-of-truth for platform lists) — for data-driven patterns
4. **Test fixture** (assert that all writers and readers of an option key agree) — for patterns requiring runtime introspection
5. **ADR with PR description requirement** — for patterns that are genuinely human-judgment-dependent

### 4. Track the conversion

When a pattern is promoted to a deterministic check, the corresponding bot finding category is suppressed in agentic review. This prevents double-flagging and frees the bot's attention budget for novel patterns.

### 5. Bots stay focused on novel cases

The explicit goal is that the bot's findings should shift over time toward patterns that **don't yet have a deterministic check**:

- First-time pattern discovery
- Cross-file semantic reasoning
- Novel attack surfaces
- Intent-correctness findings ("this code does the wrong thing for the documented requirement")

As deterministic coverage grows, the bot's per-PR finding count should drop. A growing bot finding count is a signal that **promotion is falling behind**.

### 6. Quarterly promotion review

A quarterly meeting reviews:

- New categories that crossed the recurrence threshold
- Promotions in progress
- Categories that have been suppressed via deterministic checks
- The trend in bot finding volume per PR (should be decreasing in mature areas)

## Do's and Don'ts

### Do

- Tag every substantive bot finding with a category label when you triage it
- File a `bot-finding-promotion` ticket when a category crosses the recurrence threshold
- Suppress the bot category when the deterministic check ships, to avoid double-flagging
- Treat the bots as **discovery** tools, not as front-line review
- Refer back to the [Sentry PR Friction Study automated review page](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/) for the initial pattern catalog

### Don't

- Don't silently dismiss bot findings without categorizing them — you lose the recurrence signal
- Don't try to write a deterministic check for every bot finding — only the recurring ones
- Don't suppress a bot category before the replacement check is shipped and verified
- Don't treat bot findings as ground truth — they have false positives; verify before fixing
- Don't let the bot become the only reviewer on a PR (see [BE-002](./BE-002-security-review-protocol.md) for the security-side concern)

## Pilot Promotions from the Sentry Friction Study

The following promotions are directly justified by findings in the study sample. Each is shipped as a deterministic check (proposed in a companion ADR or lint rule):

| Bot Finding Category | Promotion Target | Companion ADR / Rule | Cost |
|----------------------|------------------|---------------------|------|
| Missing `DoesNotExist` handling | Custom Ruff rule | `proposed-lint-rules/ruff_doesnotexist.py` | Low |
| `.filter().first()` + unreachable except | Custom Ruff rule | `proposed-lint-rules/ruff_doesnotexist.py` | Trivial |
| `UnionType` not callable in option registration | Archgate rule | [BE-001](./BE-001-api-contract-evolution.md) | Low |
| Pydantic `Literal` mismatch | mypy strict mode | [BE-001](./BE-001-api-contract-evolution.md) | Trivial |
| Option key mismatch (writer/reader) | Typed `OptionKey` registry + lint rule | [BE-001](./BE-001-api-contract-evolution.md) | Medium |
| High-cardinality metric tags | Custom Ruff rule + allowlist | `proposed-lint-rules/ruff_high_cardinality_metrics.py` | Low |
| Form state not reset on error | ESLint rule + ADR | [FE-001](./FE-001-frontend-component-conventions.md) | Trivial |
| Inline style props | ESLint rule + ADR | [FE-001](./FE-001-frontend-component-conventions.md) | Trivial |
| `None` saved as explicit value | Schema validation | [BE-001](./BE-001-api-contract-evolution.md) | Low |
| Platform companion list miss | Refactor to typed registry | (not yet drafted) | Medium |

These ten promotions, if shipped, would eliminate the majority of recurring substantive bot findings in the study sample — without removing the bots themselves.

## Consequences

### Positive

- **Bot review cost decreases over time** — as patterns are promoted, the bot fires on fewer findings per PR
- **Catching bugs at edit time is ~100x cheaper than catching them in PR review** — the deterministic checks surface in the IDE before the PR is opened
- **Bot attention is freed for novel cases** — the bots earn their compute by finding new patterns, not re-finding known ones
- **The promotion workflow creates an institutional memory** — the category tracker becomes a record of which bug classes have been eliminated

### Negative

- **The promotion workflow requires ongoing investment** — quarterly review, category tagging, and deterministic-check authoring all take time. Mitigation: each promoted check pays back its authoring cost within a small number of PRs.
- **Not all bot findings are promotable** — some patterns are genuinely too contextual for deterministic detection. These are the cases where bot review is the right tool indefinitely.

### Risks

- **Promotion falls behind bot finding rate** — if new pattern categories emerge faster than they're promoted, the bot finding volume grows. Mitigation: the quarterly review surfaces this trend; staffing the promotion work is a budgetary decision.
- **False positives in the promoted checks** — a deterministic check that's overly aggressive will create lint noise. Mitigation: every promoted check ships with a documented escape hatch (comment annotation or allowlist) for the legitimate edge cases.
- **Bot suppression configuration drift** — if a bot category is suppressed but the deterministic check is later removed, the pattern goes uncaught. Mitigation: link the bot suppression to the rule file in the `.archgate/adrs/` registry; deleting the rule file removes the suppression.

## Compliance and Enforcement

This ADR is a workflow ADR with no companion `.rules.ts` file. Enforcement is procedural:

### Procedural enforcement

- The bot finding category tracker is a public artifact (Linear project or `.archgate/bot-findings/` markdown files)
- Each promoted check links back to the original bot finding category in its ADR or rule comment
- The quarterly promotion review is on the engineering calendar

### Automated enforcement (indirect)

- Each promoted check is itself an `.archgate` rule or external lint rule and runs automatically
- The bot finding tracker can be cross-referenced against the ADR registry to identify gaps

## References

- [Sentry PR Friction Study — Automated Review](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/) — Full pattern catalog and cost analysis
- [BE-001 API Contract Evolution](./BE-001-api-contract-evolution.md) — Promotion target for option/serializer findings
- [FE-001 Frontend Component Conventions](./FE-001-frontend-component-conventions.md) — Promotion target for inline-style and form-state findings
- [BE-002 Security Review Protocol](./BE-002-security-review-protocol.md) — Promotion target for defense-in-depth findings
- [Custom Ruff rules (proposed)](../proposed-lint-rules/) — DoesNotExist, .filter().first(), high-cardinality metrics
- [Custom ESLint plugin (proposed)](../proposed-lint-rules/eslint-frontend-conventions.js) — Inline styles, form state try/finally
