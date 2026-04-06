# Proposed Lint Rules for Sentry

This folder contains custom lint plugin rules that complement the [proposed ADRs](../proposed-adrs/). They target the recurring bot finding patterns identified in the [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/).

## Where these would live in Sentry

In an archgate-governed project, custom lint rules belong in `.archgate/lint/`. The archgate convention (see [archgate's lint folder README](https://github.com/archgate/cli/blob/main/.archgate/lint/README.md)) is:

```
.archgate/
  adrs/                    ← ADR markdown + .rules.ts files
  lint/
    eslint.js              ← Custom ESLint plugin rules (frontend)
    ruff.toml              ← Custom Ruff config + rule pointers (backend)
    semgrep/               ← Custom Semgrep rules (Python AST patterns)
    README.md
```

For Sentry specifically, the proposed lint rules would be installed as:

```
.archgate/lint/
  eslint.js                ← FE-001: inline styles, Stack gap=0, async state try/finally
  semgrep/
    doesnotexist.yaml      ← BE-001 / BE-002: missing exception handlers on .objects.get()
    filter_first_unreachable.yaml  ← unreachable except DoesNotExist after .filter().first()
    high_cardinality_metrics.yaml  ← high-cardinality metric tags
    direct_dict_access_api.yaml    ← direct dict access on external API responses
```

The rules in this folder are reference implementations that the Sentry team could drop into `.archgate/lint/` directly.

## Why both archgate `.rules.ts` AND lint rules?

The two layers serve different purposes:

| Layer | When it runs | What it catches |
|-------|-------------|-----------------|
| **Lint rules** (ESLint, Ruff, Semgrep) | At edit time in the IDE; on every CI run | Syntactic and shallow semantic patterns |
| **archgate `.rules.ts`** | At PR check time (`archgate check`) | PR-level concerns (description sections, file scope, cross-file consistency) |

A pattern like "no inline style" is best caught at edit time (the developer sees the error in their editor before committing). The same ADR's `.rules.ts` file provides a backstop at PR check time and verifies the broader architectural intent.

For maximum effectiveness, both layers ship together: the lint rule for fast feedback, the archgate rule as the governance backstop.

## Files in this folder

- **`eslint-frontend-conventions.js`** — Custom ESLint plugin implementing FE-001 patterns
- **`semgrep-doesnotexist.yaml`** — Semgrep rule for missing `Model.DoesNotExist` handling
- **`semgrep-filter-first-unreachable.yaml`** — Semgrep rule for `.filter().first()` with unreachable `except DoesNotExist`
- **`semgrep-high-cardinality-metrics.yaml`** — Semgrep rule for unbounded-cardinality metric tags
- **`semgrep-direct-dict-access-api.yaml`** — Semgrep rule for direct dict access on external API responses

Each rule includes:

- The pattern it detects
- The ADR it implements
- The bot finding category it replaces
- An example positive match (the bug)
- An example negative match (the correct pattern)

## How to install in a Sentry-like repo

```bash
# Copy the rules into the repo's archgate lint folder
mkdir -p .archgate/lint/semgrep
cp proposed-lint-rules/eslint-frontend-conventions.js .archgate/lint/eslint.js
cp proposed-lint-rules/semgrep-*.yaml .archgate/lint/semgrep/

# Wire ESLint to load the plugin
# (in eslint.config.js)
import frontendPlugin from "./.archgate/lint/eslint.js";
export default [
  { plugins: { archgate: frontendPlugin } },
  { rules: { "archgate/no-inline-style": "error" } },
];

# Run Semgrep against the repo
semgrep --config .archgate/lint/semgrep/ src/
```
