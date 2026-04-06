---
id: FE-001
title: Frontend Component and Styling Conventions
domain: frontend
rules: true
files: ["static/app/**/*.tsx", "static/app/**/*.ts", "static/gsApp/**/*.tsx", "static/gsApp/**/*.ts"]
---

## Context

The [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/) found that **component patterns and styling** appears in **35.0%** of high-friction PRs. The single most repeated review comment in the entire dataset is:

> "Can we avoid this inline style w/ prop of some kind?"

In [PR #111529](https://github.com/getsentry/sentry/pull/111529), the same reviewer left this exact comment **six separate times** on six different lines of one PR. This is the canonical example of friction that should be a lint rule, not a recurring review discussion.

Other recurring component pattern discussions:

- Whether to use `Stack` vs `Container` vs `Flex` for layout
- Whether to use the design system (Scraps) or build a custom styled component
- Whether `Stack` with `gap={0}` is meaningful, or whether a `Container` is the right choice
- Whether `Text` rendering as `<span>` requires a wrapper for grid layouts ([#111529](https://github.com/getsentry/sentry/pull/111529) again)

The bot reviewers also flag frontend patterns. From `sentry[bot]` on [#111490](https://github.com/getsentry/sentry/pull/111490): **"The form's saving state is not reset in the `catch` block on submission failure, leaving the submit button permanently busy and preventing retries."** This is a recurring async-state-management bug class that a try/finally convention would prevent.

**Alternatives considered:**

- **Free-form styling (status quo)** — Allows maximum flexibility but produces the recurring "no inline style" review comments. The cost is paid every PR.
- **Design system only — block all custom styling** — Would eliminate the discussion but is too restrictive. Sentry has many one-off layout needs that the design system doesn't cover.
- **CSS-in-JS via styled() only — block style props entirely** — Prevents inline styles but doesn't address the layout component choice debate (Stack vs Flex vs Container).

The chosen approach is **explicit conventions enforced by ESLint** for the patterns the review comments already enforce informally, plus an architectural rule about design-system-first.

## Decision

### 1. No inline `style=` props on React components

Inline `style=` props are forbidden in production component files except when the value is genuinely dynamic and depends on a runtime value that cannot be expressed as a CSS variable. Even then, an inline-style escape hatch comment is required.

```tsx
// FORBIDDEN
<div style={{ marginTop: 8, color: "red" }}>...</div>

// ALLOWED only with an escape hatch comment
// inline-style: progress bar width must reflect current upload percentage
<div style={{ width: `${percent}%` }}>...</div>
```

### 2. Design system first

Before creating a custom styled component, check whether a Scraps/design system component satisfies the need. If the design system component is insufficient:

1. Open a Linear issue requesting the design system extension
2. Build the one-off in your PR with a comment linking to the Linear issue
3. Reference the issue in the PR description

Do not silently build a one-off styled component without acknowledging the design system gap.

### 3. Layout component selection

Use the layout components for their intended purpose:

- **`Flex`** — single-axis layouts (row OR column with optional wrapping)
- **`Grid`** — two-axis layouts with explicit column/row tracks
- **`Stack`** — vertical stacking with consistent gaps; do not use with `gap={0}` (use a `Container` instead)
- **`Container`** — generic block-level wrapper with no inherent layout

`Stack` exists to enforce vertical layout with gap; if the gap is zero, the component is doing nothing useful.

### 4. Async state must use try/finally

Async event handlers (form submissions, button click handlers that fire requests) MUST reset their loading state in a `finally` block, not only in the `try` block:

```tsx
// GOOD
async function handleSubmit() {
  setSaving(true);
  try {
    await api.save(data);
    onSuccess();
  } finally {
    setSaving(false);  // runs on success AND error
  }
}

// FORBIDDEN
async function handleSubmit() {
  setSaving(true);
  try {
    await api.save(data);
    setSaving(false);  // never runs if save() throws
    onSuccess();
  } catch (err) {
    showError(err);
    // setSaving(false) missing — button stuck in loading state
  }
}
```

### 5. Prefer prop spreading over wrapper elements

When integrating with the design system's `containerProps` pattern, use prop spreading instead of an extra wrapper element when the wrapper adds nothing:

```tsx
// GOOD
<Flex area="cell1">
  {(containerProps) => (
    <Icon size="md" variant={isSelected ? "accent" : undefined} {...containerProps} />
  )}
</Flex>

// AVOID
<Flex area="cell1">
  <div>
    <Icon size="md" variant={isSelected ? "accent" : undefined} />
  </div>
</Flex>
```

## Do's and Don'ts

### Do

- Use props, styled components, or design system tokens for styling
- Use `Flex` for single-axis layouts and `Grid` for two-axis layouts
- Use `try/finally` for async loading state in event handlers
- Spread `containerProps` from layout components instead of adding wrapper divs
- Add an `// inline-style: <reason>` comment when an inline style is genuinely required
- File a Linear issue when extending the design system, and reference it in the PR

### Don't

- Don't use `style=` props for static styles — use a styled component or className
- Don't use `Stack` with `gap={0}` — use a `Container` instead
- Don't reset loading state only in the `try` block (the catch path leaves it stuck)
- Don't build a custom styled component when an equivalent design system component exists
- Don't add `as="span"` casts repeatedly in the same file — extract a typed wrapper instead
- Don't use `Stack` and `Container` interchangeably — they have distinct purposes

## Implementation Pattern

### Good Example

```tsx
// static/app/views/onboarding/scmStep.tsx
import {Flex, Stack, Container} from 'sentry/components/core/layout';
import {Icon} from 'sentry/components/core/icon';
import {Button} from 'sentry/components/core/button';

interface ScmStepProps {
  isSelected: boolean;
  onSubmit: () => Promise<void>;
}

function ScmStep({isSelected, onSubmit}: ScmStepProps) {
  const [saving, setSaving] = useState(false);

  async function handleClick() {
    setSaving(true);
    try {
      await onSubmit();
    } finally {
      setSaving(false);  // resets on both success and error
    }
  }

  return (
    <Stack gap="md">
      <Flex area="header" align="center">
        {(containerProps) => (
          <Icon
            size="md"
            variant={isSelected ? 'accent' : undefined}
            {...containerProps}
          />
        )}
      </Flex>
      <Button busy={saving} onClick={handleClick}>
        Continue
      </Button>
    </Stack>
  );
}
```

### Bad Example

```tsx
// FORBIDDEN: inline style for static value
<div style={{marginTop: 8, padding: 16}}>...</div>

// FORBIDDEN: Stack with gap={0}
<Stack gap={0}>
  <Text>One</Text>
  <Text>Two</Text>
</Stack>

// FORBIDDEN: loading state stuck on error path
async function handleSubmit() {
  setSaving(true);
  try {
    await api.save(data);
    setSaving(false);
  } catch (err) {
    showError(err);
    // setSaving(false) missing
  }
}
```

## Consequences

### Positive

- **Eliminates the most repeated review comment in the codebase** — "can we avoid this inline style" goes from a recurring review discussion to a lint error caught at edit time
- **Async state bugs caught at edit time** — the try/finally requirement prevents the form-stuck-loading bug class
- **Consistent layout component usage** — reviewers can trust that `Stack` always means vertical-with-gap and `Flex` always means single-axis
- **Design system adoption increases** — the explicit "file a Linear issue if you need to extend it" loop creates a feedback path

### Negative

- **Author friction during the migration period** — existing code with inline styles will trigger warnings until refactored. Mitigation: the rule applies to new and modified files only; existing files are not retroactively flagged.
- **The escape-hatch comment can be abused** — an author can add `// inline-style: needed` without a real reason. Mitigation: code reviewers verify the comment explains a genuine dynamic value need.

### Risks

- **`style=` allowed via prop name aliasing** — `<div {...{ style: x }}>` bypasses the literal `style=` pattern. Mitigation: the lint rule also matches spread expressions that contain a `style` key.
- **Layout component churn** — if Sentry refactors its layout components, the rule must be updated. Mitigation: the layout component names are extracted to a constant in the lint rule.

## Compliance and Enforcement

### Automated Enforcement

- **Archgate rule** `FE-001/no-inline-style`: Scans `.tsx` files for `style=` JSX attributes. Allows usage when an `// inline-style:` comment is on the same or previous line. Severity: `error`.
- **Archgate rule** `FE-001/no-stack-with-zero-gap`: Scans for `<Stack` JSX elements with `gap={0}` or `gap="0"`. Severity: `error`.
- **Archgate rule** `FE-001/async-state-try-finally`: Detects `setLoading(true)` / `setSaving(true)` (and similar boolean state setters) in async functions and verifies the `false` reset is in a `finally` block. Severity: `warning`.
- **Custom ESLint rule** in `.archgate/lint/eslint.js` provides edit-time feedback in the IDE — see `proposed-lint-rules/eslint-frontend-conventions.js`

### Manual Enforcement

Code reviewers MUST verify:

1. Inline style escape-hatch comments describe a genuine dynamic value need
2. New custom styled components either reference an existing design system gap or have a Linear issue filed
3. `Stack` is used for non-zero vertical gaps; `Container` is used for zero-gap wrappers
4. Async loading state is reset in `finally`, not in `try`

## References

- [Sentry PR Friction Study — Themes (Component Patterns)](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/)
- [PR #111529](https://github.com/getsentry/sentry/pull/111529) — six identical "no inline style" review comments in one PR
- [PR #111490](https://github.com/getsentry/sentry/pull/111490) — form state stuck in loading after error
- [Custom ESLint plugin (proposed)](../proposed-lint-rules/eslint-frontend-conventions.js) — edit-time enforcement
