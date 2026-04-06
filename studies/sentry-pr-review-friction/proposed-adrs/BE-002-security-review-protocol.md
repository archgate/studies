---
id: BE-002
title: Security Review Protocol for Auth and Integration Changes
domain: backend
rules: true
files: ["src/sentry/integrations/**/*.py", "src/sentry/identity/**/*.py", "src/sentry/api/**/*.py", "src/sentry/auth/**/*.py", "src/sentry/web/frontend/auth_*.py"]
---

## Context

The [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/) found that **security and permissions** discussion appears in **20.0%** of high-friction PRs — a lower frequency than other themes, but with disproportionately high stakes. The `github` scope has the highest median review count (5.5) of any scope in the codebase, almost entirely due to security surface area in OAuth and pipeline code.

Specific bot and human findings from the study:

- **Unvalidated installation_id allows hijacking** — `sentry-warden[bot]` on [#111728](https://github.com/getsentry/sentry/pull/111728): "The `GithubOrganizationSelectionApiStep.handle_post` method accepts `installation_id` from POST data and binds it directly to pipeline state without validating that the authenticated user has access to that GitHub installation."
- **Defense-in-depth weakened** — `sentry-warden[bot]` on [#111663](https://github.com/getsentry/sentry/pull/111663): "Organization scoping removed from Group fetch — defense-in-depth weakened. The code change removes organization scoping from the `Group.objects.get()` call."
- **Missing permission checks on UI actions** — Human reviewer on [#111499](https://github.com/getsentry/sentry/pull/111499): "Should we put some permissions checks around this? Only admins will be able to edit integrations... I think we should hide or disable this button for regular users."
- **Pipeline state binding before validation** — Human reviewer on [#111728](https://github.com/getsentry/sentry/pull/111728): "Yeah I think this could be a valid attack since this is the first step in the pipeline. Like what if someone gives us someone else's installation_id?"

The shared root cause is that **security implications are discovered during review**, not declared upfront. A security-aware reviewer must spot the issue from reading the diff. When the reviewer is not security-focused (or the security-focused reviewer is not on the rotation that day), the issue ships.

**Alternatives considered:**

- **Mandatory security team review on all PRs** — Would catch everything but creates a serialization bottleneck on the security team. Doesn't scale.
- **Penetration testing post-merge** — Catches issues but at the most expensive point in the lifecycle.
- **Static analysis for security patterns (Semgrep, CodeQL)** — Effective for known vulnerability patterns. Sentry already runs these, and several of the bot findings above are exactly the kind of issue these tools target. The ADR complements static analysis with a human review checklist for the cases static analysis cannot catch.

The chosen approach is a **front-loaded declaration**: PRs touching security-sensitive paths must include a "Security Considerations" section in the PR description, plus CODEOWNERS-driven security reviewer assignment.

## Decision

### 1. Security-sensitive paths require a Security Considerations section

PRs that modify any of the following paths MUST include a `## Security Considerations` section in the PR description:

- `src/sentry/integrations/**` — Integration setup, OAuth flows, webhook handlers
- `src/sentry/identity/**` — Identity provider integrations
- `src/sentry/auth/**` — Authentication and SSO
- `src/sentry/api/**` — API endpoints (especially permission and serializer changes)
- `src/sentry/web/frontend/auth_*.py` — Auth-related views

The Security Considerations section MUST address:

1. **What user-controlled inputs are accepted?**
2. **What authorization checks are performed?**
3. **Could this change weaken existing defense-in-depth?**
4. **Is there a state-management window where invalid state could be exploited?**
5. **Does this change accept identifiers (installation_id, group_id, project_id) that need to be validated against the authenticated user's access?**

### 2. CODEOWNERS gating

The above paths MUST list a security-designated reviewer in CODEOWNERS. PRs cannot merge without approval from a CODEOWNERS-listed reviewer.

### 3. No silent defense-in-depth removal

Removing organization scoping, permission checks, or other access control mechanisms requires:

1. An explicit comment in the diff explaining why the removal is safe
2. Reviewer acknowledgment in the PR thread (not just an approval)
3. The Security Considerations section MUST mention the removal

### 4. User-supplied IDs must be validated against caller authorization

When an endpoint accepts an identifier from request data (`installation_id`, `external_id`, `team_id`, etc.), the endpoint MUST validate that the authenticated user has access to that resource **before** binding it to pipeline state, session state, or any other persisted location.

### 5. Pipeline state binding happens after validation

When using a pipeline pattern (`pipeline.bind_state(...)`), the bind MUST happen after authorization validation, not before. Binding before validation creates a window where an unauthenticated request can pollute pipeline state.

## Do's and Don'ts

### Do

- Include a `## Security Considerations` section in every PR touching security-sensitive paths
- Validate user-supplied identifiers against the authenticated user's access before binding to state
- Add explicit comments when removing defense-in-depth mechanisms
- Use organization-scoped queries (`Group.objects.filter(project__organization=org).get(id=group_id)`) instead of unscoped lookups
- Test the unauthorized case for every new endpoint
- Catch model lookup exceptions (`DoesNotExist`) in security-critical paths and return a generic error to avoid information disclosure

### Don't

- Don't remove `organization=` filters from model queries without explicit security justification
- Don't bind user-supplied identifiers to pipeline state before authorization validation
- Don't accept identifiers from POST data and trust them without validation
- Don't return 404 vs 403 differently for security-sensitive resources (timing/information disclosure)
- Don't catch all exceptions in auth code and return success — fail closed
- Don't add a new auth flow without paired tests for authorized AND unauthorized cases

## Implementation Pattern

### Good Example

```python
# src/sentry/integrations/github/integration_pipeline.py
from sentry.integrations.github.helpers import validate_user_has_installation_access

class GithubOrganizationSelectionApiStep(PipelineStep):
    def handle_post(self, request, pipeline):
        installation_id = request.data.get("installation_id")
        if not installation_id:
            return self.error_response("installation_id required")

        # Validate BEFORE binding to pipeline state
        if not validate_user_has_installation_access(
            user=request.user,
            installation_id=installation_id,
        ):
            return self.error_response("access denied", status=403)

        # Now safe to bind
        pipeline.bind_state("installation_id", installation_id)
        return pipeline.next_step()
```

```python
# src/sentry/api/endpoints/group_details.py
def get(self, request, group_id):
    try:
        # Organization-scoped query — defense in depth
        group = Group.objects.get(
            id=group_id,
            project__organization=self.organization,
        )
    except Group.DoesNotExist:
        # Generic 404 — don't leak whether the group exists in another org
        raise ResourceDoesNotExist
    return Response(serialize(group, request.user))
```

```markdown
## Security Considerations

This PR adds an API-driven GitHub integration setup flow.

- **User-controlled inputs**: `installation_id`, `state`, `code` from the
  GitHub OAuth callback
- **Authorization checks**: `installation_id` is validated against the
  authenticated user's GitHub installations via `validate_user_has_installation_access`
  before binding to pipeline state
- **Defense-in-depth changes**: None
- **State management**: Pipeline state is bound only after the user's
  access has been verified, preventing pollution from unauthenticated requests
- **Validated identifiers**: `installation_id` is validated against the
  user's GitHub access; `state` is validated against the pipeline signature
```

### Bad Example

```python
# BAD: binding user-supplied ID to pipeline state BEFORE validation
def handle_post(self, request, pipeline):
    installation_id = request.data["installation_id"]  # untrusted input
    pipeline.bind_state("installation_id", installation_id)  # bound first

    if validated_data["state"] != pipeline.signature:  # validation later
        return self.error_response("invalid state")
    # ... by now, pipeline state is already polluted
```

```python
# BAD: removing organization scoping with no comment or justification
def get(self, request, group_id):
    # OLD: Group.objects.get(id=group_id, project__organization=self.organization)
    # NEW (silently weakened):
    group = Group.objects.get(id=group_id)  # no scope check
    return Response(serialize(group))
```

```python
# BAD: catching all exceptions and returning success
def get_installation_info(installation_id):
    try:
        return github_client.get_installation(installation_id)
    except Exception:
        return None  # caller treats None as "no installations" — fail open
```

## Consequences

### Positive

- **Security review is front-loaded** — issues are surfaced in the PR description, not discovered mid-review
- **CODEOWNERS gating ensures security expertise on every relevant PR** — without serializing the entire team on the security team
- **The Security Considerations section creates a reviewable artifact** — future maintainers can see why a change was considered safe
- **Removing defense-in-depth requires explicit acknowledgment** — silent weakening of access controls becomes harder

### Negative

- **PR description overhead** — every security-sensitive PR has an additional section to write. Mitigation: the section is short for routine changes (often one bullet per question).
- **CODEOWNERS bottleneck risk** — security reviewers can become a serialization point. Mitigation: maintain a rotation of multiple security-designated reviewers per area.

### Risks

- **Authors filling in the section without thinking** — an author can write "no security implications" without genuine analysis. Mitigation: reviewers verify the answers; the section is a forcing function for thought, not a guarantee.
- **Over-broad path matching** — every API endpoint change triggers the security section, even truly trivial ones. Mitigation: the rule scope can be refined as the codebase teaches us which paths are routinely safe.

## Compliance and Enforcement

### Automated Enforcement

- **Archgate rule** `BE-002/security-considerations-section-required`: When a PR touches files matching the security-sensitive paths, requires a `## Security Considerations` section in the PR description. Severity: `error`.
- **Archgate rule** `BE-002/no-pipeline-bind-before-validation`: Detects `pipeline.bind_state(...)` calls that appear before any explicit `validate_*` or authorization check in the same function. Severity: `warning`.
- **Archgate rule** `BE-002/no-unscoped-model-get-in-api`: In `src/sentry/api/`, flags `Model.objects.get(id=...)` calls that don't include an `organization=` or `project__organization=` filter. Severity: `warning`.

### Manual Enforcement

Code reviewers MUST verify:

1. The Security Considerations section answers all 5 required questions
2. User-supplied identifiers are validated before pipeline state binding
3. Removed defense-in-depth has explicit justification, not silent removal
4. Tests cover the unauthorized case, not just the authorized case
5. Failed authorization returns appropriately without information disclosure

## References

- [Sentry PR Friction Study — Themes (Security)](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/)
- [PR #111728](https://github.com/getsentry/sentry/pull/111728) — primary evidence: 32 review events on GitHub OAuth pipeline security
- [PR #111663](https://github.com/getsentry/sentry/pull/111663) — defense-in-depth weakening detection
- [PR #111499](https://github.com/getsentry/sentry/pull/111499) — missing UI permission checks
- [BE-001 API Contract Evolution](./BE-001-api-contract-evolution.md) — Companion ADR; typed serializer fields support security review by making contract changes explicit
