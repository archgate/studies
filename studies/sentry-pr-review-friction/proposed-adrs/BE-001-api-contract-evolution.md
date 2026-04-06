---
id: BE-001
title: API Contract and Configuration Evolution
domain: backend
rules: true
files: ["src/sentry/**/*.py", "src/sentry/options/**/*.py", "src/sentry/api/serializers/**/*.py"]
---

## Context

The [Sentry PR Friction Study](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/) identified **API design and defaults** as the top discussion theme — appearing in **38.3%** of high-friction PRs in the deep comment sample. Reviewers repeatedly debate:

- Whether new fields should be nullable or required with defaults
- How defaults propagate across scopes (org → project → runtime)
- Whether conflicting options should be force-overwritten, ignored, or rejected at validation time
- Whether the type annotation on a registered option matches the runtime type

The study also captured several recurring bot findings that map directly to API contract issues:

- **`UnionType not callable`** — `sentry-warden[bot]` on [#111697](https://github.com/getsentry/sentry/pull/111697): "The `defaultCodingAgent` option uses `str | None` as the type parameter. The code calls `type_(data[key])` to convert the value. However, `str | None` is a `types.UnionType` which cannot be called as a function."
- **Pydantic Literal mismatch** — same PR: "The Pydantic model's `target` field is `Literal['cursor_background_agent', 'claude_code_agent', ...]` which excludes `'seer'`."
- **Option key mismatch between writer and reader** — same PR: "The new option registers with key `sentry:default_automated_run_stopping_point` but the code that consumes this value reads from key `sentry:default_stopping_point`."
- **`None` saved as explicit value** — same PR: "The removal of the truthiness check for `stopping_point` causes `None` to be explicitly saved as a project option, overriding the intended default value of `code_changes`."

These findings recur because there is no enforced contract for how new options and serializer fields should be declared.

**Alternatives considered:**

- **Pure runtime validation (Pydantic everywhere)** — Replace the existing `(name, default, type)` tuple-based option registration with Pydantic models. This is the most type-safe approach but requires migrating hundreds of existing options. Out of scope for an incremental ADR.
- **Documentation-only convention** — Write a style guide and rely on review enforcement. The study data shows this is exactly what's failing today: reviewers are catching the issues, but each catch is a discussion cycle.
- **External schema registry** — Use a JSON Schema or Protobuf-based registry for all org options. Highest correctness but requires substantial tooling.

The chosen approach is to **codify the existing implicit conventions** (each new option has explicit nullability semantics, scope resolution, and validation behavior) and add **mechanical checks** for the patterns the bots already catch.

## Decision

New API fields and configuration options MUST follow these conventions:

### 1. Explicit defaults

Every new field must have an explicit default value. Document whether the default is "safe off" (feature disabled) or "safe on" (feature active). Prefer "safe off" for new features behind flags.

### 2. Nullability has semantic meaning

A field is nullable **only if `null` has a distinct semantic meaning** — e.g., "inherit from parent scope," "not yet configured," "explicitly opted out." If `null` just means "use the default," use the default directly instead.

When a field is nullable, document what `null` means in the docstring or registration comment.

### 3. Concrete callable types in option registration

Option registration tuples MUST use a concrete callable type, not a `UnionType`. `str | None` is **not** a valid option type — it is a `types.UnionType` and cannot be called as a constructor. Use `str` with `flags=FLAG_ALLOW_EMPTY` or a custom validator instead.

### 4. Option keys are typed identifiers

Option keys (e.g., `sentry:default_automated_run_stopping_point`) MUST be defined in a single registry as typed string constants. All read sites (`get_value`, `get_from_cache`) and write sites (`set_value`) MUST reference the constant, not a string literal. This eliminates the "writer/reader key mismatch" bug class.

### 5. Pydantic Literals are validated at write time

When a Pydantic model field uses `Literal[...]`, the construction site MUST guarantee the value is in the literal set. If the value is computed dynamically (e.g., from a default), the default itself must be in the literal set.

### 6. Scope resolution is documented

When a setting exists at multiple scopes (org, project, user), the resolution order MUST be documented in the option's registration comment. State whether child scopes can override, and what happens when parent and child conflict.

### 7. Conflicting options are rejected at validation time

If a serializer accepts multiple options whose combinations are invalid, the conflict MUST be caught in the serializer's `validate()` method with a clear error message. Silent resolution is forbidden.

### 8. `None` is not silently saved

Setters MUST reject `None` unless the option's schema explicitly allows it. Removing a truthiness check that previously prevented `None` from being saved is a behavior change that requires explicit opt-in.

## Do's and Don'ts

### Do

- Define option keys as typed string constants in a single registry (e.g., `src/sentry/options/keys.py`)
- Reference option keys via the constant at every read and write site
- Use concrete types (`str`, `int`, `bool`) in option registration
- Document the meaning of `None` in nullable field docstrings
- Use Pydantic `Literal` types when the field has a fixed enumeration of valid values
- Catch conflicting option combinations in serializer `validate()` methods with clear error messages
- Add a docstring to every new option explaining the default rationale ("safe off" / "safe on")

### Don't

- Don't use `str | None` (or any `types.UnionType`) as the type parameter in option registration tuples
- Don't reference option keys as inline string literals — use the registry constant
- Don't make a field nullable when `None` and the default mean the same thing
- Don't remove a truthiness check on a setter without explicitly handling `None`
- Don't silently resolve conflicting options — reject them in `validate()`
- Don't construct a Pydantic model with a value that isn't in the field's `Literal` type — even via a default
- Don't add a Pydantic model field as `Optional[X]` unless `None` has a documented meaning

## Implementation Pattern

### Good Example

```python
# src/sentry/options/keys.py — single source of truth for option keys
from typing import Final

DEFAULT_AUTOMATED_RUN_STOPPING_POINT: Final = "sentry:default_automated_run_stopping_point"
DEFAULT_CODING_AGENT: Final = "sentry:default_coding_agent"
```

```python
# src/sentry/options/defaults.py — concrete callable type
from sentry.options import register
from sentry.options.keys import DEFAULT_CODING_AGENT

# GOOD: concrete `str` type, explicit default, documented as "safe off"
register(
    DEFAULT_CODING_AGENT,
    type=str,                    # not str | None
    default="seer",              # explicit, not None
    flags=FLAG_AUTOMATOR_MODIFIABLE,
)
```

```python
# src/sentry/api/serializers/organization.py — typed enum + Literal
from typing import Literal

CodingAgent = Literal["seer", "cursor_background_agent", "claude_code_agent"]

class OrganizationSerializer(serializers.Serializer):
    defaultCodingAgent = serializers.ChoiceField(
        choices=["seer", "cursor_background_agent", "claude_code_agent"],
        required=False,
        default="seer",  # matches the option default — never None
    )

    def validate(self, attrs):
        # Reject conflicting options at validation time
        if attrs.get("autoOpenPRs") and attrs.get("stoppingPoint") not in ("open_pr", "code_changes"):
            raise serializers.ValidationError(
                "stoppingPoint must be 'open_pr' or 'code_changes' when autoOpenPRs is enabled"
            )
        return attrs
```

```python
# src/sentry/seer/handoff.py — read uses the constant
from sentry.options.keys import DEFAULT_CODING_AGENT
from sentry import options

agent = options.get(DEFAULT_CODING_AGENT)  # not options.get("sentry:default_coding_agent")
```

### Bad Example

```python
# BAD: UnionType is not callable
register(
    "sentry:default_coding_agent",
    type=str | None,             # TypeError at runtime in OrganizationSerializer.save()
    default=None,                # None means... what?
)

# BAD: writer and reader use different string literals — typo bug
options.set("sentry:default_automated_run_stopping_point", value)
# ... in another file ...
agent = options.get("sentry:default_stopping_point")  # silently returns nothing
```

```python
# BAD: removing a truthiness check causes None to be saved as an explicit value
def save(self, validated_data):
    # OLD: if validated_data.get("stopping_point"):
    #          self._project.update_option(KEY, validated_data["stopping_point"])
    # NEW (broken):
    self._project.update_option(KEY, validated_data["stopping_point"])  # saves None
```

```python
# BAD: Pydantic Literal mismatch via dynamic default
class HandoffConfig(BaseModel):
    target: Literal["cursor_background_agent", "claude_code_agent"]

# Construction with the org's default value, which is "seer" — not in the Literal
config = HandoffConfig(target=org.default_coding_agent)  # validation error
```

## Consequences

### Positive

- **Eliminates the writer/reader key mismatch bug class** — typos are caught at edit time by the type system
- **Eliminates the `UnionType not callable` runtime crash** — caught by mypy strict mode and the lint rule
- **Clearer reviewer expectations** — when reviewing a new option, the conventions are explicit and codified
- **Reduces theme-1 (API design) discussions** — the most common debates have pre-decided answers

### Negative

- **Migration cost for existing options** — fully migrating Sentry's existing option surface to typed keys requires touching many files. The ADR applies to **new** options; existing options can be migrated incrementally.
- **Pydantic Literal validation can be brittle** — when the literal set changes, every construction site must be reviewed. Mitigation: use a typed enum that the literal references.

### Risks

- **Authors bypassing the registry by importing strings from another file** — A determined author could re-export a string constant from somewhere else. Mitigation: the lint rule scans for any `options.get(...)` or `options.set(...)` call where the argument is a string literal, not a name.
- **`type=str` accepting unintended values** — Without a Literal-backed type, an option registered as `type=str` will accept any string. Mitigation: high-stakes options should use a custom validator function.

## Compliance and Enforcement

### Automated Enforcement

- **Archgate rule** `BE-001/no-union-type-in-option-registration`: Scans option registration calls and flags any `type=` argument containing `|` or `Union[`. Severity: `error`.
- **Archgate rule** `BE-001/option-keys-must-use-constants`: Scans `options.get()`, `options.set()`, `options.delete()`, `OrganizationOption.objects.set_value()`, and `ProjectOption.objects.set_value()` calls and flags string literal arguments. Severity: `error`.
- **Archgate rule** `BE-001/no-none-default-without-nullable-comment`: Scans option registrations with `default=None` and requires an adjacent comment explaining what `None` means. Severity: `warning`.
- **mypy strict mode** on `src/sentry/options/` and `src/sentry/api/serializers/` catches Pydantic Literal mismatches at type-check time

### Manual Enforcement

Code reviewers MUST verify:

1. New options use a typed key constant from the registry
2. New nullable fields have a documented `None` semantic
3. Serializer `validate()` methods reject conflicting option combinations explicitly
4. Removed truthiness checks have explicit `None` handling

## References

- [Sentry PR Friction Study — Themes](https://studies.archgate.dev/studies/sentry-pr-review-friction/themes/)
- [Sentry PR Friction Study — Automated Review (Pattern 4: Type System Misuse)](https://studies.archgate.dev/studies/sentry-pr-review-friction/automated-review/)
- [PR #111697](https://github.com/getsentry/sentry/pull/111697) — primary evidence source: 47 review events, multiple bot findings about option keys and Pydantic Literals
- [GEN-003 Bot Finding Promotion](./GEN-003-bot-finding-promotion.md) — Companion ADR establishing the workflow that produced this rule
