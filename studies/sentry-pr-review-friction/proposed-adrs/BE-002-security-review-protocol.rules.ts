/// <reference path="./rules.d.ts" />

/**
 * BE-002 — Security Review Protocol for Auth and Integration Changes
 *
 * Enforces front-loaded security analysis for PRs touching auth,
 * integration, identity, and API endpoint paths. The rules check the
 * PR description (when available via .git/PR_DESCRIPTION) and flag
 * code-level security anti-patterns the bot reviewers already catch.
 */

const SECURITY_SENSITIVE_PATTERNS = [
  /^src\/sentry\/integrations\//,
  /^src\/sentry\/identity\//,
  /^src\/sentry\/auth\//,
  /^src\/sentry\/api\//,
  /^src\/sentry\/web\/frontend\/auth_/,
];

function isSecuritySensitive(path: string): boolean {
  return SECURITY_SENSITIVE_PATTERNS.some((re) => re.test(path));
}

export default {
  rules: {
    "security-considerations-section-required": {
      description:
        "PRs touching auth/integration/API paths must include a Security Considerations section",
      severity: "error",
      async check(ctx) {
        const sensitiveChanges = ctx.changedFiles.filter(isSecuritySensitive);
        if (sensitiveChanges.length === 0) return;

        let body: string;
        try {
          body = await ctx.readFile(".git/PR_DESCRIPTION");
        } catch {
          return;
        }

        if (!/##\s*Security Considerations/i.test(body)) {
          ctx.report.violation({
            message: `PR touches ${sensitiveChanges.length} security-sensitive file(s) but the description has no '## Security Considerations' section.`,
            fix: "Add a '## Security Considerations' section addressing user-controlled inputs, authorization checks, defense-in-depth changes, state-management windows, and validated identifiers.",
          });
        }
      },
    },

    "no-pipeline-bind-before-validation": {
      description:
        "pipeline.bind_state() must happen after authorization validation, not before",
      severity: "warning",
      async check(ctx) {
        const integrationFiles = ctx.scopedFiles.filter(
          (f) =>
            (f.includes("/integrations/") || f.includes("/identity/")) &&
            f.endsWith(".py")
        );

        for (const file of integrationFiles) {
          const content = await ctx.readFile(file);
          const lines = content.split(/\r?\n/);

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!/\bpipeline\.bind_state\s*\(/.test(line)) continue;

            // Look BACKWARD up to 30 lines (within the same function) for
            // a validate_* call or an explicit authorization check.
            const start = Math.max(0, i - 30);
            const window = lines.slice(start, i).join("\n");
            const hasValidation =
              /\bvalidate_\w+\s*\(/.test(window) ||
              /\bcheck_\w+_access\s*\(/.test(window) ||
              /\brequest\.access\b/.test(window) ||
              /\bhas_(access|permission)\b/.test(window);

            // Check that the window doesn't START a new function (def keyword)
            // — if it does, our backward window crossed a function boundary.
            const crossedFunction = /^\s*def\s+\w+/m.test(window) === false;

            if (!hasValidation && crossedFunction) {
              ctx.report.warning({
                message:
                  "pipeline.bind_state() called without an apparent prior authorization check. User-supplied identifiers must be validated before binding.",
                file,
                line: i + 1,
                fix: "Move the bind_state call after the authorization validation, or add a validate_*/has_access check before this line.",
              });
            }
          }
        }
      },
    },

    "no-unscoped-model-get-in-api": {
      description:
        "API endpoints should fetch models with organization/project scoping for defense-in-depth",
      severity: "warning",
      async check(ctx) {
        const apiFiles = ctx.scopedFiles.filter(
          (f) => f.startsWith("src/sentry/api/") && f.endsWith(".py")
        );

        // Models that should always be organization-scoped when accessed via API
        const scopedModels = [
          "Group",
          "Project",
          "Team",
          "Release",
          "Environment",
          "Monitor",
          "AlertRule",
          "Dashboard",
        ];

        for (const file of apiFiles) {
          const content = await ctx.readFile(file);
          const lines = content.split(/\r?\n/);

          for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            for (const model of scopedModels) {
              const pattern = new RegExp(
                `\\b${model}\\.objects\\.get\\s*\\(([^)]*)\\)`
              );
              const match = pattern.exec(line);
              if (!match) continue;

              const args = match[1];
              // Acceptable scopings
              if (
                /organization\s*=/.test(args) ||
                /project__organization\s*=/.test(args) ||
                /project_id\s*=/.test(args) ||
                /project\s*=/.test(args)
              ) {
                continue;
              }

              ctx.report.warning({
                message: `${model}.objects.get() in an API endpoint without organization/project scoping. Defense-in-depth weakened — add an organization filter.`,
                file,
                line: i + 1,
                fix: `Add an organization filter: ${model}.objects.get(id=..., project__organization=self.organization)`,
              });
            }
          }
        }
      },
    },
  },
} satisfies RuleSet;
