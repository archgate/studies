/// <reference path="./rules.d.ts" />

/**
 * FE-001 — Frontend Component and Styling Conventions
 *
 * Codifies the recurring frontend review comments from the Sentry PR
 * Friction Study, particularly the "can we avoid this inline style" comment
 * that appeared 6 times in PR #111529.
 *
 * The archgate rules enforce the patterns at PR-check time. A companion
 * ESLint plugin in .archgate/lint/eslint.js provides edit-time feedback
 * in the IDE.
 */

export default {
  rules: {
    "no-inline-style": {
      description:
        "JSX `style=` props are forbidden unless accompanied by an `// inline-style:` escape hatch comment",
      severity: "error",
      async check(ctx) {
        const tsxFiles = ctx.scopedFiles.filter((f) => f.endsWith(".tsx"));

        for (const file of tsxFiles) {
          const content = await ctx.readFile(file);
          const lines = content.split(/\r?\n/);

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            // Match `style={` or `style="` JSX attribute (not React's style prop in spread)
            if (!/\bstyle\s*=\s*[\{"]/.test(line)) continue;

            // Skip if the line itself or the previous line contains the escape hatch
            const prev = i > 0 ? lines[i - 1] : "";
            const hasEscapeHatch =
              /\/\/\s*inline-style:/.test(line) ||
              /\/\/\s*inline-style:/.test(prev);

            if (!hasEscapeHatch) {
              ctx.report.violation({
                message:
                  "Inline `style=` prop is forbidden. Use a styled component, className, or design system tokens.",
                file,
                line: i + 1,
                fix: "Replace with a styled component, or add `// inline-style: <reason>` if a runtime-dynamic value is genuinely required.",
              });
            }
          }
        }
      },
    },

    "no-stack-with-zero-gap": {
      description:
        "`Stack` components must not use `gap={0}` — use `Container` for zero-gap wrappers",
      severity: "error",
      async check(ctx) {
        const tsxFiles = ctx.scopedFiles.filter((f) => f.endsWith(".tsx"));
        const matches = await Promise.all(
          tsxFiles.map((file) =>
            ctx.grep(file, /<Stack[^>]*\sgap\s*=\s*[\{"]?0[\}"]?/)
          )
        );

        for (const fileMatches of matches) {
          for (const m of fileMatches) {
            ctx.report.violation({
              message:
                "`Stack` with `gap={0}` is meaningless. Use `<Container>` or `<Flex>` instead.",
              file: m.file,
              line: m.line,
              fix: "Replace `<Stack gap={0}>` with `<Container>` or `<Flex direction='column'>`.",
            });
          }
        }
      },
    },

    "async-state-try-finally": {
      description:
        "Async event handlers that set a loading state must reset it in a `finally` block, not only in `try`",
      severity: "warning",
      async check(ctx) {
        const tsxFiles = ctx.scopedFiles.filter(
          (f) => f.endsWith(".tsx") || f.endsWith(".ts")
        );

        for (const file of tsxFiles) {
          const content = await ctx.readFile(file);

          // Conservative check: find functions where `setSaving(true)` or
          // `setLoading(true)` appear, then verify a corresponding `finally`
          // block exists in the same function. The implementation uses a
          // simple regex over the file with limited scope-awareness.
          const setterMatches = [
            ...content.matchAll(
              /(?:set(?:Saving|Loading|Submitting|Busy|Pending))\s*\(\s*true\s*\)/g
            ),
          ];

          for (const m of setterMatches) {
            // Look at the next ~40 lines (typical function body) for a `finally` block.
            const idx = m.index ?? 0;
            const window = content.slice(idx, idx + 2000);

            const hasFinally = /\}\s*finally\s*\{/.test(window);
            const hasFalseInTry = /set(?:Saving|Loading|Submitting|Busy|Pending)\s*\(\s*false\s*\)/.test(
              window.slice(0, window.indexOf("catch") >= 0 ? window.indexOf("catch") : window.length)
            );

            if (!hasFinally && hasFalseInTry) {
              const lineNum = content.slice(0, idx).split(/\r?\n/).length;
              ctx.report.warning({
                message:
                  "Loading state setter appears to reset in try but not finally. The catch path will leave the state stuck.",
                file,
                line: lineNum,
                fix: "Move the `setLoading(false)` (or equivalent) into a `finally` block so it runs on both success and error.",
              });
            }
          }
        }
      },
    },
  },
} satisfies RuleSet;
