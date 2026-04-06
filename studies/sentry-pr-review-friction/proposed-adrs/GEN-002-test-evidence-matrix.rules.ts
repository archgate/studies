/// <reference path="./rules.d.ts" />

/**
 * GEN-002 — Test Evidence Matrix by Change Type
 *
 * Validates that PR descriptions include a Test Plan section and that
 * test files don't use the bare-except anti-pattern that fakes error
 * path coverage. The matrix itself is documented in the ADR; the rule
 * enforces the procedural minimum (the section exists) and one common
 * test smell (bare except with pass).
 */

export default {
  rules: {
    "test-plan-section-required": {
      description:
        "PR description must include a `## Test Plan` section",
      severity: "error",
      async check(ctx) {
        // The CI integration writes the PR body to .git/PR_DESCRIPTION.
        // For local runs without a PR, skip the check.
        let body: string;
        try {
          body = await ctx.readFile(".git/PR_DESCRIPTION");
        } catch {
          return;
        }

        if (!/##\s*Test Plan/i.test(body)) {
          ctx.report.violation({
            message:
              "PR description has no '## Test Plan' section. Identify the change type(s) and list the test scenarios from the GEN-002 matrix.",
            fix: "Add a '## Test Plan' section that maps the change type to specific test names.",
          });
        }
      },
    },

    "no-bare-except-pass-in-tests": {
      description:
        "Test files should not use `except Exception: pass` to fake error path coverage",
      severity: "warning",
      async check(ctx) {
        const testFiles = ctx.scopedFiles.filter(
          (f) =>
            f.endsWith(".py") &&
            (f.includes("/tests/") || f.includes("/test_"))
        );

        // Match `except Exception:` or `except:` followed (within 3 lines)
        // by a lone `pass`. The pattern is approximate; multiline ripgrep
        // would be more precise but the line-based grep is what archgate
        // exposes.
        for (const file of testFiles) {
          const content = await ctx.readFile(file);
          const lines = content.split(/\r?\n/);
          for (let i = 0; i < lines.length; i++) {
            if (!/\bexcept(?:\s+Exception)?\s*:/.test(lines[i])) continue;

            // Look at the next 3 lines for a lone `pass`
            const window = lines.slice(i + 1, i + 4);
            const onlyPass = window.find((l) => l.trim() === "pass");
            const otherStatements = window.find(
              (l) => l.trim() && l.trim() !== "pass" && !l.trim().startsWith("#")
            );

            if (onlyPass && !otherStatements) {
              ctx.report.warning({
                message:
                  "Bare `except: pass` in a test file. This often masks a missing assertion. Catch a specific exception and assert against it.",
                file,
                line: i + 1,
                fix: "Replace with `with pytest.raises(SpecificException): ...` or assert on the exception type and message.",
              });
            }
          }
        }
      },
    },

    "test-plan-references-must-exist": {
      description:
        "Test names listed in the Test Plan section should be findable in the changed test files",
      severity: "warning",
      async check(ctx) {
        let body: string;
        try {
          body = await ctx.readFile(".git/PR_DESCRIPTION");
        } catch {
          return;
        }

        // Extract test names of the form `test_*` or `it("...")` from the
        // Test Plan section. Conservative regex: only match function-style
        // identifiers immediately after a colon or backtick.
        const testPlanMatch = body.match(/##\s*Test Plan([\s\S]*?)(?:\n##|$)/i);
        if (!testPlanMatch) return;

        const planText = testPlanMatch[1];
        const referencedTests = new Set<string>();
        for (const m of planText.matchAll(/`(test_[a-zA-Z0-9_]+)`/g)) {
          referencedTests.add(m[1]);
        }
        for (const m of planText.matchAll(/::(test_[a-zA-Z0-9_]+)/g)) {
          referencedTests.add(m[1]);
        }

        if (referencedTests.size === 0) return;

        const testFiles = ctx.changedFiles.filter(
          (f) =>
            (f.endsWith(".py") || f.endsWith(".ts") || f.endsWith(".tsx")) &&
            (f.includes("/tests/") || f.includes("/test_") || f.includes(".test."))
        );

        const found = new Set<string>();
        for (const file of testFiles) {
          const content = await ctx.readFile(file);
          for (const name of referencedTests) {
            if (content.includes(name)) found.add(name);
          }
        }

        for (const name of referencedTests) {
          if (!found.has(name)) {
            ctx.report.warning({
              message: `Test '${name}' referenced in Test Plan but not found in any changed test file.`,
              fix: `Verify that '${name}' exists in the diff, or update the Test Plan section.`,
            });
          }
        }
      },
    },
  },
} satisfies RuleSet;
