/// <reference path="./rules.d.ts" />

/**
 * BE-001 — API Contract and Configuration Evolution
 *
 * Codifies recurring bot findings about Sentry's option registration and
 * serializer patterns:
 *   - `str | None` UnionType used as a callable type parameter
 *   - Inline string-literal option keys (writer/reader mismatch bug class)
 *   - `default=None` without explanation of the null semantic
 *
 * The patterns and severity targets are derived from the Sentry PR
 * Friction Study (see automated-review.mdx, Pattern 4 and Pattern 5).
 */

export default {
  rules: {
    "no-union-type-in-option-registration": {
      description:
        "Option registration must use a concrete callable type, never a UnionType (str | None)",
      severity: "error",
      async check(ctx) {
        const optionFiles = ctx.scopedFiles.filter(
          (f) => f.includes("/options/") && f.endsWith(".py")
        );

        // Look for `register(...)` or `define(...)` calls with a `type=`
        // argument that contains a union (`|` or `Union[`).
        // The pattern is conservative: it matches `type=X | Y` and `type=Union[`.
        const matches = await Promise.all(
          optionFiles.map((file) =>
            ctx.grep(file, /\btype\s*=\s*[A-Za-z_][A-Za-z0-9_\[\]]*\s*\|\s*[A-Za-z_]/)
          )
        );

        for (const fileMatches of matches) {
          for (const m of fileMatches) {
            ctx.report.violation({
              message:
                "Option registration uses a UnionType (e.g., `str | None`). UnionType is not callable and will raise TypeError when the serializer tries to convert the value.",
              file: m.file,
              line: m.line,
              fix: "Use a concrete type like `str` and handle the optional case in the validator, or use FLAG_ALLOW_EMPTY.",
            });
          }
        }

        // Also flag explicit `Union[X, None]` syntax
        const unionMatches = await Promise.all(
          optionFiles.map((file) =>
            ctx.grep(file, /\btype\s*=\s*(?:typing\.)?Union\[/)
          )
        );

        for (const fileMatches of unionMatches) {
          for (const m of fileMatches) {
            ctx.report.violation({
              message:
                "Option registration uses `Union[...]`. Union types are not callable as constructors.",
              file: m.file,
              line: m.line,
              fix: "Use a concrete type and handle optional values via flags or a validator.",
            });
          }
        }
      },
    },

    "option-keys-must-use-constants": {
      description:
        "options.get/set and OrganizationOption.set_value calls must use a typed key constant, not a string literal",
      severity: "error",
      async check(ctx) {
        // Apply to all backend Python files except the keys registry itself
        const pyFiles = ctx.scopedFiles.filter(
          (f) =>
            f.endsWith(".py") &&
            !f.endsWith("/options/keys.py") &&
            !f.endsWith("/options/defaults.py") &&
            !f.includes("/tests/")
        );

        // Match calls like:
        //   options.get("sentry:foo")
        //   options.set("sentry:foo", x)
        //   OrganizationOption.objects.set_value(..., "sentry:foo", ...)
        //   ProjectOption.objects.set_value(..., "sentry:foo", ...)
        //   org.get_option("sentry:foo")
        //   project.update_option("sentry:foo", ...)
        const stringKeyPattern =
          /(?:options\.(?:get|set|delete)|set_value|get_option|update_option|delete_option)\s*\(\s*[^,)]*?["']sentry:[a-z_]+["']/;

        const matches = await Promise.all(
          pyFiles.map((file) => ctx.grep(file, stringKeyPattern))
        );

        for (const fileMatches of matches) {
          for (const m of fileMatches) {
            ctx.report.violation({
              message:
                "Option key passed as a string literal. Use the typed constant from sentry.options.keys to prevent writer/reader mismatch bugs.",
              file: m.file,
              line: m.line,
              fix: "Import the key constant from sentry.options.keys and use it instead of the string literal.",
            });
          }
        }
      },
    },

    "no-none-default-without-nullable-comment": {
      description:
        "Option registration with default=None must have a comment explaining the null semantic",
      severity: "warning",
      async check(ctx) {
        const optionFiles = ctx.scopedFiles.filter(
          (f) => f.includes("/options/") && f.endsWith(".py")
        );

        for (const file of optionFiles) {
          const content = await ctx.readFile(file);
          const lines = content.split(/\r?\n/);

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!/\bdefault\s*=\s*None\b/.test(line)) continue;

            // Look for a comment within the previous 5 lines that mentions
            // "None means" or "null means" or "nullable" or "inherit".
            const window = lines.slice(Math.max(0, i - 5), i + 1).join("\n");
            const hasExplanation =
              /#.*\b(None means|null means|nullable|inherit|opt[ -]?out|not.*configured)\b/i.test(
                window
              );

            if (!hasExplanation) {
              ctx.report.warning({
                message:
                  "Option registered with default=None has no comment explaining what None means semantically.",
                file,
                line: i + 1,
                fix: "Add a comment explaining whether None means 'inherit from parent', 'not configured', or 'explicitly opted out' — or use a non-None default.",
              });
            }
          }
        }
      },
    },
  },
} satisfies RuleSet;
