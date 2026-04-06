/// <reference path="./rules.d.ts" />

/**
 * GEN-001 — PR Scope Boundaries and Size Budget
 *
 * Computes the size of the changed file set and the total churn relative
 * to the merge base. Warns when soft limits are exceeded and requires a
 * "Scope Rationale" section in the PR description for over-limit PRs.
 *
 * The thresholds are derived from the empirical distribution in the
 * Sentry PR Friction Study (median 2 files / 51 churn; large-PR cutoff
 * at 10 files / 400 churn).
 */

const SOFT_FILES = 5;
const SOFT_CHURN = 200;
const HARD_FILES = 10;
const HARD_CHURN = 400;

// Files that don't count toward the size budget — mechanical or generated
const EXCLUDE_PATTERNS = [
  /\/snapshots\//,
  /\.snap$/,
  /\.lock$/,
  /^pnpm-lock\.yaml$/,
  /^yarn\.lock$/,
  /\/migrations\/\d+_/,
  /__snapshots__/,
  /\.generated\./,
];

function isExcluded(path: string): boolean {
  return EXCLUDE_PATTERNS.some((re) => re.test(path));
}

export default {
  rules: {
    "pr-size-warning": {
      description:
        "Warn when a PR exceeds the soft size limits (5 files / 200 churn)",
      severity: "warning",
      async check(ctx) {
        // changedFiles already excludes deleted files in archgate's diff context
        const counted = ctx.changedFiles.filter((f) => !isExcluded(f));

        if (counted.length === 0) return;

        // Compute total churn by reading the diff lines from each changed file.
        // archgate's grep returns line counts via repeated matches; we use a
        // proxy by counting non-empty lines in the changed regions.
        let totalChurn = 0;
        for (const file of counted) {
          try {
            const content = await ctx.readFile(file);
            // Approximation: count non-empty lines in the modified file as
            // a churn proxy. The CI integration replaces this with real
            // git diff numstat output when available.
            const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
            totalChurn += Math.min(lines.length, 1000); // cap to avoid pathological files
          } catch {
            // unreadable — skip
          }
        }

        if (counted.length >= HARD_FILES || totalChurn >= HARD_CHURN) {
          ctx.report.warning({
            message: `PR exceeds the LARGE threshold (${counted.length} files, ~${totalChurn} churn). The Sentry friction study shows large PRs hit the high-friction quartile 57.4% of the time.`,
            fix: "Split the PR into smaller logical units. If the change cannot be split, add a '## Scope Rationale' section to the PR description.",
          });
          return;
        }

        if (counted.length > SOFT_FILES || totalChurn > SOFT_CHURN) {
          ctx.report.warning({
            message: `PR exceeds the soft size limit (${counted.length} files, ~${totalChurn} churn; soft limit is ${SOFT_FILES} files / ${SOFT_CHURN} churn).`,
            fix: "Add a '## Scope Rationale' section to the PR description, or split the PR.",
          });
        }
      },
    },

    "scope-rationale-required": {
      description:
        "PRs over the soft size limit must include a Scope Rationale section",
      severity: "error",
      async check(ctx) {
        const counted = ctx.changedFiles.filter((f) => !isExcluded(f));
        if (counted.length <= SOFT_FILES) return;

        // The CI integration writes the PR body to .git/PR_DESCRIPTION before
        // running archgate check. If the file is missing (local run), skip.
        let body: string;
        try {
          body = await ctx.readFile(".git/PR_DESCRIPTION");
        } catch {
          return;
        }

        if (!/##\s*Scope Rationale/i.test(body)) {
          ctx.report.violation({
            message:
              "PR exceeds the soft size limit but the description has no '## Scope Rationale' section explaining why the change cannot be split.",
            fix: "Add a '## Scope Rationale' section to the PR description that identifies the specific coupling preventing a split.",
          });
        }
      },
    },
  },
} satisfies RuleSet;
