---
id: GEN-002
title: Test Evidence Matrix by Change Type
domain: general
rules: true
files: ["src/**/*.py", "src/**/*.ts", "src/**/*.tsx", "static/**/*.tsx"]
---

## Context

The [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/) found that **test evidence and coverage** is tied for the top discussion theme — appearing in **38.3%** of high-friction PRs. The pattern is striking: reviewers are not asking authors to "add more tests" in the abstract. They are asking for **specific tests** that the author didn't think to write:

- Rendering tests that verify provider context propagation ([#111554](https://github.com/getsentry/sentry/pull/111554))
- Error path tests for circuit breakers when the underlying request fails ([#111723](https://github.com/getsentry/sentry/pull/111723))
- Specific exception handling tests when error matching is fragile ([#111691](https://github.com/getsentry/sentry/pull/111691))
- Edge case tests for sentinel values like `installation_id == "-1"` ([#111728](https://github.com/getsentry/sentry/pull/111728))

The bot reviewers find similar gaps. From `sentry[bot]` on [#111697](https://github.com/getsentry/sentry/pull/111697): **"Test asserts wrong default value for coding agent — `test_default_coding_agent_default` asserts `response.data['defaultCodingAgent'] is None`, but the serializer returns `'seer'`."** The test was passing for the wrong reason.

The shared root cause is that **each reviewer applies their own mental model of "sufficient" test evidence**, and that model isn't written down. A senior backend engineer expects different test evidence than a senior frontend engineer, and both are correct for their domains. Without an explicit matrix, every PR re-derives the expectation from scratch.

**Alternatives considered:**

- **Coverage thresholds (require 80% line coverage)** — Coverage thresholds measure quantity, not quality. A PR can hit 100% line coverage with tests that exercise the happy path and miss every error case. The bot findings are consistently about untested error paths and edge cases — not about uncovered lines.
- **Mandatory pair programming for high-risk changes** — Effective for the highest-risk changes (auth, migrations) but doesn't scale to the volume of routine PRs.
- **Test-first / TDD requirement** — Strong correctness benefits but a significant workflow change. Too large for an ADR; better as a team practice decision.

The chosen approach is a **per-change-type test matrix**: an explicit table listing the minimum test scenarios for common change types. The matrix is published, the PR template references it, and reviewers can verify against it instead of re-deriving the expectation each time.

## Decision

Every PR's test plan MUST address the minimum test scenarios for its change type, drawn from this matrix:

| Change Type | Minimum Test Evidence |
|-------------|----------------------|
| **New API endpoint** | Happy path (200/201) + auth failure (401/403) + validation error (400) + rate limit (429) when applicable |
| **Modified API endpoint** | Tests for the modified behavior + at least one regression test for the previous contract |
| **New React component** | Mount/render + props variations + error state + accessibility (axe assertions for non-trivial components) |
| **Modified React component** | Updated tests covering the modified behavior + snapshot diff if visual change |
| **Provider/context change** | Nested consumer test + context propagation verification |
| **Error handling change** | Each error path + recovery behavior + logging/metric verification |
| **Configuration/option change** | Default value + override + invalid value rejection + scope resolution (org→project) |
| **Integration/webhook** | Success + auth failure + timeout + malformed payload + idempotency |
| **Migration (data)** | Forward migration + rollback (if applicable) + idempotency on partial failure |
| **Migration (schema)** | Forward + rollback + zero-downtime compatibility window check |
| **Circuit breaker / resilience** | Open state + closed state + half-open transition + underlying failure types |
| **Permission/RBAC change** | Authorized user happy path + unauthorized user denial + role boundary case |
| **Refactor (no behavior change)** | Existing test suite passes + at least one assertion that the refactored code path is exercised |

The PR description MUST include a "Test Plan" section that maps each item from the matrix to the test(s) added or updated.

## Do's and Don'ts

### Do

- Identify the change type(s) for your PR before opening it
- Write tests that exercise the *minimum* matrix entries for your change type, even if coverage tools report the lines as already covered
- For multi-type PRs (e.g., new endpoint that touches a serializer and a context provider), satisfy the matrix for each type
- Include the Test Plan section in the PR description with explicit test name references
- For circuit breaker / retry / resilience changes, include a test where the underlying call fails — not just where it succeeds
- For permission changes, include a test for the unauthorized case, not just the authorized case

### Don't

- Don't rely on line coverage as proof of sufficient test evidence — coverage measures whether code ran, not whether the right scenarios ran
- Don't write a test that asserts the wrong default value (the [#111697](https://github.com/getsentry/sentry/pull/111697) bug — test passed for the wrong reason)
- Don't skip the unauthorized-user test on a permission change because "the happy path test covers most of the code"
- Don't catch a generic `Exception` in a test and call it "error path coverage"
- Don't claim "covered by integration tests" without naming the specific integration test

## Implementation Pattern

### Good Example

```markdown
## Test Plan

Change types: **New API endpoint**, **Permission/RBAC change**

- Happy path: `tests/sentry/api/endpoints/test_org_coding_agent.py::test_get_default_returns_seer`
- Auth failure: `test_get_unauthorized_returns_401`
- Validation error: `test_post_invalid_value_returns_400`
- Authorized user (admin): `test_admin_can_set_default_coding_agent`
- Unauthorized user (member): `test_member_cannot_set_default_coding_agent`
- Default value: `test_default_value_is_seer_when_unset`
- Override: `test_org_setting_overrides_default`
- Invalid value rejection: `test_invalid_agent_returns_400`
```

```python
# tests/sentry/api/endpoints/test_org_coding_agent.py
# GOOD: explicit test that asserts the actual default value, not None
def test_default_value_is_seer_when_unset(self):
    response = self.get_success_response(self.organization.slug)
    assert response.data["defaultCodingAgent"] == "seer"  # not `is None`

# GOOD: explicit test for the unauthorized case
def test_member_cannot_set_default_coding_agent(self):
    self.login_as(self.member_user)
    response = self.get_error_response(
        self.organization.slug,
        method="put",
        data={"defaultCodingAgent": "claude_code_agent"},
    )
    assert response.status_code == 403
```

### Bad Example

```markdown
## Test Plan
- Added unit tests
- Coverage is 87%
```

This test plan provides no information about *which* scenarios were tested. A reviewer must read every test file to verify the minimum matrix is satisfied.

```python
# BAD: test passes for the wrong reason (real bug from #111697)
def test_default_coding_agent_default(self):
    response = self.get_success_response(self.organization.slug)
    assert response.data["defaultCodingAgent"] is None
    # But the serializer actually returns "seer" — this assertion is wrong
    # and the test passes only because the test fixture has a bug
```

```python
# BAD: error path "tested" by catching any exception
def test_circuit_breaker_handles_errors(self):
    try:
        circuit_breaker.call(failing_func)
    except Exception:
        pass  # Was the right exception raised? Did the breaker open? Unknown.
```

## Consequences

### Positive

- **Reviewer expectations are pre-aligned** — instead of negotiating "is this test enough?" on every PR, both author and reviewer reference the same matrix
- **Test correctness is checkable** — the matrix surfaces missing scenarios that coverage tools cannot
- **Bot finding categories shift** — bot reviewers stop catching "missing error path test" because authors include them by default

### Negative

- **More tests mean more PR work** — for routine changes that previously shipped with one happy-path test, the matrix may add 2-3 additional tests. Mitigation: the matrix entries are minimums, and the time to write a 3-line test for an authorization denial is small relative to the cost of catching the bug in production.
- **The matrix will need maintenance** — as new change types emerge (e.g., new framework patterns), the matrix must be updated. Mitigation: changes to the matrix go through the same ADR review process.

### Risks

- **Authors checking the matrix without applying it** — Listing test names in the Test Plan section without actually writing them. Mitigation: the rule cross-references named tests against the test file changes in the diff.
- **Matrix becoming a checkbox exercise** — Reviewers approving PRs because the matrix was "satisfied" without verifying test quality. Mitigation: the matrix is a floor, not a ceiling — reviewer judgment still governs whether the tests are meaningful.

## Compliance and Enforcement

### Automated Enforcement

- **Archgate rule** `GEN-002/test-plan-section-required`: Scans the PR description for a `## Test Plan` section. Severity: `error`.
- **Archgate rule** `GEN-002/test-plan-references-must-exist`: Cross-references test names listed in the Test Plan against actual test files added or modified in the diff. Severity: `warning` (some tests may be in files outside the diff).
- **Archgate rule** `GEN-002/no-bare-except-in-tests`: Flags bare `except:` and `except Exception:` blocks in test files that contain only `pass` — these are usually fake error path tests. Severity: `warning`.

### Manual Enforcement

Code reviewers MUST verify:

1. The Test Plan section identifies the change type and lists the matrix entries
2. The named tests actually exist in the diff (or in clearly referenced files)
3. Error path tests assert specific exceptions, not bare `except`
4. Permission changes include both authorized and unauthorized test cases
5. The test assertions match the actual production behavior — no "passing for the wrong reason"

## References

- [Sentry PR Friction Study — Themes (Test Evidence)](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/)
- [Sentry PR Friction Study — Automated Review Pattern 4 (Test correctness)](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/)
- [PR #111554](https://github.com/getsentry/sentry/pull/111554) — context propagation test gap
- [PR #111723](https://github.com/getsentry/sentry/pull/111723) — circuit breaker error path test gap
- [PR #111697](https://github.com/getsentry/sentry/pull/111697) — test assertion mismatch (passing for wrong reason)
- [GEN-001 PR Scope Boundaries](./GEN-001-pr-scope-boundaries.md) — Companion ADR; smaller PRs make the test matrix easier to satisfy
