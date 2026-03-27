#!/usr/bin/env python3
"""
Reproducible methodology for analyzing PR review friction in getsentry/sentry.

Requirements:
- Python 3.11+
- GitHub CLI (gh) authenticated
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import statistics
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class PrRow:
    number: int
    title: str
    url: str
    ttm_h: float
    reviews_total: int
    changes_requested: int
    commented: int
    approvals: int
    files: int
    churn: int


def run_gh_json(args: list[str]) -> Any:
    output = subprocess.check_output(
        ["gh", *args],
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return json.loads(output)


def iso_days_ago(days: int) -> str:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    return since.date().isoformat()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((len(ordered) - 1) * p)
    return round(ordered[idx], 2)


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.median(values)), 2)


def collect_prs(repo: str, days: int, limit: int) -> list[dict[str, Any]]:
    since = iso_days_ago(days)
    query = f"merged:>={since}"
    fields = "number,title,createdAt,mergedAt,author,reviews,files,url"
    return run_gh_json(
        [
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "merged",
            "--search",
            query,
            "--limit",
            str(limit),
            "--json",
            fields,
        ]
    )


def to_rows(prs: list[dict[str, Any]]) -> list[PrRow]:
    rows: list[PrRow] = []
    for pr in prs:
        created = dt.datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        merged = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        ttm_h = (merged - created).total_seconds() / 3600

        reviews = pr.get("reviews", [])
        files = pr.get("files", [])
        churn = sum((f.get("additions") or 0) + (f.get("deletions") or 0) for f in files)

        rows.append(
            PrRow(
                number=pr["number"],
                title=pr["title"],
                url=pr["url"],
                ttm_h=ttm_h,
                reviews_total=len(reviews),
                changes_requested=sum(1 for r in reviews if r.get("state") == "CHANGES_REQUESTED"),
                commented=sum(1 for r in reviews if r.get("state") == "COMMENTED"),
                approvals=sum(1 for r in reviews if r.get("state") == "APPROVED"),
                files=len(files),
                churn=churn,
            )
        )
    return rows


def summarize(rows: list[PrRow], repo: str, days: int, limit: int) -> dict[str, Any]:
    small = [r for r in rows if r.files <= 3 and r.churn <= 80]
    large = [r for r in rows if r.files >= 10 or r.churn >= 400]

    ttm = [r.ttm_h for r in rows]
    reviews = [float(r.reviews_total) for r in rows]

    baseline = {
        "ttm_median_h": median(ttm),
        "ttm_p75_h": percentile(ttm, 0.75),
        "ttm_p90_h": percentile(ttm, 0.90),
        "reviews_median": median(reviews),
        "reviews_avg": round(statistics.mean(reviews), 2) if reviews else 0.0,
        "changes_requested_share": round(
            sum(1 for r in rows if r.changes_requested > 0) / len(rows), 3
        )
        if rows
        else 0.0,
        "small_pr_share": round(len(small) / len(rows), 3) if rows else 0.0,
        "large_pr_share": round(len(large) / len(rows), 3) if rows else 0.0,
    }

    segmented = {
        "small_pr_ttm_median_h": median([r.ttm_h for r in small]),
        "large_pr_ttm_median_h": median([r.ttm_h for r in large]),
        "small_pr_reviews_median": median([float(r.reviews_total) for r in small]),
        "large_pr_reviews_median": median([float(r.reviews_total) for r in large]),
    }

    top_review_volume = sorted(rows, key=lambda r: r.reviews_total, reverse=True)[:15]
    top_ttm = sorted(rows, key=lambda r: r.ttm_h, reverse=True)[:15]

    return {
        "methodology": {
            "repo": repo,
            "window_days": days,
            "query_limit": limit,
            "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        },
        "sample_size": len(rows),
        "baseline": baseline,
        "segmented": segmented,
        "top_review_volume": [r.__dict__ for r in top_review_volume],
        "top_ttm": [r.__dict__ for r in top_ttm],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze PR friction for a GitHub repository.")
    parser.add_argument("--repo", default="getsentry/sentry", help="GitHub repo in owner/name format")
    parser.add_argument("--days", type=int, default=90, help="Number of trailing days to query")
    parser.add_argument("--limit", type=int, default=500, help="Maximum merged PRs to analyze")
    parser.add_argument(
        "--out",
        default="studies/sentry-pr-review-friction/output/sentry_pr_friction_report.json",
        help="Path to write JSON report",
    )
    args = parser.parse_args()

    prs = collect_prs(repo=args.repo, days=args.days, limit=args.limit)
    rows = to_rows(prs)
    report = summarize(rows, repo=args.repo, days=args.days, limit=args.limit)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
