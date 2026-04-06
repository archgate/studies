/**
 * eslint-frontend-conventions.js
 *
 * Custom ESLint plugin implementing FE-001 (Frontend Component and
 * Styling Conventions) for the Sentry codebase.
 *
 * Implements the patterns that recur across PRs in the Sentry PR Friction
 * Study (https://studies.archgate.dev/studies/sentry-pr-review-friction/):
 *
 *   - no-inline-style: forbids `style={...}` JSX attributes without an
 *     `// inline-style:` escape hatch comment
 *   - no-stack-zero-gap: forbids `<Stack gap={0}>`
 *   - async-state-try-finally: requires `setLoading(false)` (and similar
 *     boolean state setters) to live in a `finally` block
 *
 * Install in `.archgate/lint/eslint.js` and reference from your eslint
 * config:
 *
 *   import frontendPlugin from "./.archgate/lint/eslint.js";
 *   export default [
 *     { plugins: { archgate: frontendPlugin } },
 *     {
 *       rules: {
 *         "archgate/no-inline-style": "error",
 *         "archgate/no-stack-zero-gap": "error",
 *         "archgate/async-state-try-finally": "warn",
 *       },
 *     },
 *   ];
 */

const noInlineStyle = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Forbid inline `style=` JSX attributes without an explicit escape hatch comment",
    },
    messages: {
      noInlineStyle:
        "Inline `style=` is forbidden. Use a styled component, className, or design system tokens. If a runtime-dynamic value is genuinely required, add `// inline-style: <reason>` on the line above.",
    },
    schema: [],
  },
  create(context) {
    return {
      JSXAttribute(node) {
        if (node.name.name !== "style") return;

        // Look for an `// inline-style:` comment on the same or previous line
        const sourceCode = context.getSourceCode();
        const comments = sourceCode.getAllComments();
        const nodeLine = node.loc.start.line;
        const hasEscapeHatch = comments.some((c) => {
          const commentLine = c.loc.end.line;
          return (
            (commentLine === nodeLine || commentLine === nodeLine - 1) &&
            /inline-style:/i.test(c.value)
          );
        });

        if (!hasEscapeHatch) {
          context.report({ node, messageId: "noInlineStyle" });
        }
      },
    };
  },
};

const noStackZeroGap = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Forbid `<Stack gap={0}>` — use `<Container>` or `<Flex>` for zero-gap layouts",
    },
    messages: {
      noStackZeroGap:
        "`<Stack gap={0}>` is meaningless. Use `<Container>` or `<Flex direction='column'>` instead.",
    },
    schema: [],
  },
  create(context) {
    return {
      JSXOpeningElement(node) {
        if (node.name.type !== "JSXIdentifier" || node.name.name !== "Stack") {
          return;
        }
        for (const attr of node.attributes) {
          if (
            attr.type !== "JSXAttribute" ||
            attr.name.name !== "gap"
          ) {
            continue;
          }
          const value = attr.value;
          if (!value) continue;

          const isZero =
            (value.type === "Literal" &&
              (value.value === 0 || value.value === "0")) ||
            (value.type === "JSXExpressionContainer" &&
              value.expression.type === "Literal" &&
              (value.expression.value === 0 || value.expression.value === "0"));

          if (isZero) {
            context.report({ node: attr, messageId: "noStackZeroGap" });
          }
        }
      },
    };
  },
};

const asyncStateTryFinally = {
  meta: {
    type: "suggestion",
    docs: {
      description:
        "Require async state setters (setLoading, setSaving, etc.) to be reset in a `finally` block",
    },
    messages: {
      missingFinally:
        "`{{name}}(false)` should live in a `finally` block so the state is reset on both success and error paths.",
    },
    schema: [],
  },
  create(context) {
    const TRACKED_SETTERS =
      /^set(Saving|Loading|Submitting|Busy|Pending)$/;

    return {
      // Detect: setSaving(true) inside a try block of an async function,
      // and check that there is a `finally` clause containing setSaving(false).
      "FunctionDeclaration[async=true], FunctionExpression[async=true], ArrowFunctionExpression[async=true]"(
        fn
      ) {
        const sourceCode = context.getSourceCode();
        const fnText = sourceCode.getText(fn);

        // Quick filter: only proceed if the function references a tracked setter with `true`
        const setterTrueMatch = fnText.match(
          /\b(set(Saving|Loading|Submitting|Busy|Pending))\s*\(\s*true\s*\)/
        );
        if (!setterTrueMatch) return;

        const setterName = setterTrueMatch[1];

        // Walk the function body for try statements
        function visit(node) {
          if (!node || typeof node !== "object") return;
          if (node.type === "TryStatement") {
            const finallyBlock = node.finalizer
              ? sourceCode.getText(node.finalizer)
              : "";
            const tryBlock = sourceCode.getText(node.block);

            const finallyHasReset = new RegExp(
              `\\b${setterName}\\s*\\(\\s*false\\s*\\)`
            ).test(finallyBlock);

            const tryHasReset = new RegExp(
              `\\b${setterName}\\s*\\(\\s*false\\s*\\)`
            ).test(tryBlock);

            if (tryHasReset && !finallyHasReset) {
              context.report({
                node,
                messageId: "missingFinally",
                data: { name: setterName },
              });
            }
          }
          for (const key of Object.keys(node)) {
            if (key === "parent" || key === "loc" || key === "range") continue;
            const child = node[key];
            if (Array.isArray(child)) {
              for (const c of child) visit(c);
            } else if (child && typeof child === "object") {
              visit(child);
            }
          }
        }

        visit(fn.body);
      },
    };
  },
};

export default {
  rules: {
    "no-inline-style": noInlineStyle,
    "no-stack-zero-gap": noStackZeroGap,
    "async-state-try-finally": asyncStateTryFinally,
  },
};
