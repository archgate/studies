#!/usr/bin/env python3
"""
Reproducible methodology for analyzing PR review friction in getsentry/sentry.

Three-phase pipeline:
  collect  — fetch PR data and deep comments from GitHub API
  analyze  — compute metrics, domain maps, theme coding, friction predictors
  report   — structure analysis into narrative-ready JSON

Requirements:
- Python 3.11+
- GitHub CLI (gh) authenticated
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
THEME_DICT_PATH = Path(__file__).resolve().parent / "theme_dictionary.json"


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
    labels: list[str] = field(default_factory=list)
    title_scope: str = "unscoped"
    title_type: str = "unknown"
    file_domains: list[str] = field(default_factory=list)
    review_rounds: int = 0
    friction_score: float = 0.0
    author: str = ""
    state: str = "merged"


@dataclass
class CommentEntry:
    author: str
    body: str
    created_at: str
    is_bot: bool
    source: str  # "issue_comment", "review_body", "review_comment"
    path: str = ""  # file path for inline review comments


@dataclass
class PrCommentData:
    pr_number: int
    pr_url: str
    pr_title: str
    comments: list[dict[str, Any]] = field(default_factory=list)
    theme_tags: list[str] = field(default_factory=list)
    evidence_quotes: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_gh_json(args: list[str]) -> Any:
    """Run a gh CLI command and parse JSON output."""
    output = subprocess.check_output(
        ["gh", *args],
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    return json.loads(output)


def run_gh_api_json(endpoint: str, paginate: bool = False) -> Any:
    """Run a gh api call and parse JSON output."""
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    output = subprocess.check_output(
        cmd,
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


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.mean(values)), 2)


TITLE_PATTERN = re.compile(r"^(\w+?)(?:\(([^)]+)\))?:\s*")


def parse_title(title: str) -> tuple[str, str]:
    """Extract (type, scope) from conventional commit title. Returns ('unknown', 'unscoped') on mismatch."""
    m = TITLE_PATTERN.match(title)
    if m:
        return (m.group(1).lower(), m.group(2) or "unscoped")
    return ("unknown", "unscoped")


def extract_file_domains(file_paths: list[str]) -> list[str]:
    """Extract unique domain prefixes from file paths (first two segments)."""
    domains: set[str] = set()
    for fp in file_paths:
        parts = fp.strip("/").split("/")
        if len(parts) >= 2:
            domains.add(f"{parts[0]}/{parts[1]}")
        elif len(parts) == 1:
            domains.add(parts[0])
    return sorted(domains)


AUTOMATED_MARKERS = [
    "linear-linkback",
    "BACKEND_TEST_FAILURES",
    "FRONTEND_BACKEND_WARNING",
    "BUGBOT_REVIEW",
    "BUGBOT_",
    "codecov",
    "<!-- sentry-",
    "<!-- coverage-",
    "This pull request contains Frontend and Backend changes",
]


def is_bot(login: str) -> bool:
    return login.endswith("[bot]") or login.endswith("-bot")


def is_automated_comment(body: str) -> bool:
    """Check if a comment is automated (CI bots, linear links, etc.)."""
    return any(marker in body for marker in AUTOMATED_MARKERS)


def normalize_values(values: list[float]) -> list[float]:
    """Min-max normalize a list of values to 0-1 range."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def count_review_rounds(reviews: list[dict[str, Any]]) -> int:
    """Count review rounds: each CHANGES_REQUESTED increments the round counter."""
    rounds = 0
    for r in reviews:
        if r.get("state") == "CHANGES_REQUESTED":
            rounds += 1
    return rounds


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  -> Wrote {path}")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Collect subcommand
# ---------------------------------------------------------------------------


def collect_prs(
    repo: str, days: int, limit: int, state: str = "merged"
) -> list[dict[str, Any]]:
    """Fetch PRs from GitHub using gh CLI."""
    since = iso_days_ago(days)
    fields = "number,title,createdAt,mergedAt,closedAt,author,reviews,files,url,labels"

    args = [
        "pr",
        "list",
        "-R",
        repo,
        "--limit",
        str(limit),
        "--json",
        fields,
    ]

    if state == "merged":
        args.extend(["--state", "merged", "--search", f"merged:>={since}"])
    elif state == "closed":
        args.extend(["--state", "closed", "--search", f"closed:>={since} is:unmerged"])
    elif state == "open":
        args.extend(["--state", "open"])

    return run_gh_json(args)


def to_rows(
    prs: list[dict[str, Any]], state: str = "merged"
) -> list[PrRow]:
    """Transform raw GitHub API data into PrRow objects."""
    rows: list[PrRow] = []
    for pr in prs:
        created = dt.datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))

        if state == "merged" and pr.get("mergedAt"):
            end = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        elif pr.get("closedAt"):
            end = dt.datetime.fromisoformat(pr["closedAt"].replace("Z", "+00:00"))
        else:
            end = dt.datetime.now(dt.UTC)

        ttm_h = round((end - created).total_seconds() / 3600, 2)

        reviews = pr.get("reviews", [])
        files = pr.get("files", [])
        churn = sum(
            (f.get("additions") or 0) + (f.get("deletions") or 0) for f in files
        )
        file_paths = [f.get("path", "") for f in files if f.get("path")]
        labels = [l.get("name", "") for l in pr.get("labels", []) if l.get("name")]

        title_type, title_scope = parse_title(pr.get("title", ""))
        author_login = ""
        if isinstance(pr.get("author"), dict):
            author_login = pr["author"].get("login", "")
        elif isinstance(pr.get("author"), str):
            author_login = pr["author"]

        rows.append(
            PrRow(
                number=pr["number"],
                title=pr.get("title", ""),
                url=pr.get("url", ""),
                ttm_h=ttm_h,
                reviews_total=len(reviews),
                changes_requested=sum(
                    1 for r in reviews if r.get("state") == "CHANGES_REQUESTED"
                ),
                commented=sum(
                    1 for r in reviews if r.get("state") == "COMMENTED"
                ),
                approvals=sum(
                    1 for r in reviews if r.get("state") == "APPROVED"
                ),
                files=len(files),
                churn=churn,
                labels=labels,
                title_scope=title_scope,
                title_type=title_type,
                file_domains=extract_file_domains(file_paths),
                review_rounds=count_review_rounds(reviews),
                author=author_login,
                state=state,
            )
        )
    return rows


def compute_friction_scores(rows: list[PrRow]) -> None:
    """Compute composite friction scores (mutates rows in place)."""
    if not rows:
        return
    review_vals = [float(r.reviews_total) for r in rows]
    ttm_vals = [r.ttm_h for r in rows]
    norm_reviews = normalize_values(review_vals)
    norm_ttm = normalize_values(ttm_vals)
    for i, row in enumerate(rows):
        row.friction_score = round(norm_reviews[i] + norm_ttm[i], 4)


def fetch_deep_comments(
    repo: str, pr_numbers: list[int], delay: float = 0.5
) -> list[PrCommentData]:
    """Fetch full comment data for selected high-friction PRs."""
    results: list[PrCommentData] = []
    owner, name = repo.split("/")

    for i, pr_num in enumerate(pr_numbers):
        print(f"  Fetching comments for PR #{pr_num} ({i + 1}/{len(pr_numbers)})...")

        pr_data = PrCommentData(pr_number=pr_num, pr_url="", pr_title="")

        # 1. Get PR details with comments and reviews
        try:
            detail = run_gh_json([
                "pr",
                "view",
                str(pr_num),
                "-R",
                repo,
                "--json",
                "title,url,comments,reviews",
            ])
            pr_data.pr_url = detail.get("url", "")
            pr_data.pr_title = detail.get("title", "")

            # Issue-level comments
            for c in detail.get("comments", []):
                author = c.get("author", {}).get("login", "") if isinstance(c.get("author"), dict) else str(c.get("author", ""))
                pr_data.comments.append(asdict(CommentEntry(
                    author=author,
                    body=c.get("body", ""),
                    created_at=c.get("createdAt", ""),
                    is_bot=is_bot(author),
                    source="issue_comment",
                )))

            # Review bodies (the top-level review summary text)
            for r in detail.get("reviews", []):
                author = r.get("author", {}).get("login", "") if isinstance(r.get("author"), dict) else str(r.get("author", ""))
                body = r.get("body", "")
                if body and body.strip():
                    pr_data.comments.append(asdict(CommentEntry(
                        author=author,
                        body=body,
                        created_at=r.get("submittedAt", ""),
                        is_bot=is_bot(author),
                        source="review_body",
                    )))

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"    Warning: failed to fetch PR detail for #{pr_num}: {e}")

        time.sleep(delay)

        # 2. Get inline review comments via REST API
        try:
            inline_comments = run_gh_api_json(
                f"repos/{owner}/{name}/pulls/{pr_num}/comments",
                paginate=True,
            )
            if isinstance(inline_comments, list):
                for c in inline_comments:
                    author = c.get("user", {}).get("login", "") if isinstance(c.get("user"), dict) else ""
                    pr_data.comments.append(asdict(CommentEntry(
                        author=author,
                        body=c.get("body", ""),
                        created_at=c.get("created_at", ""),
                        is_bot=is_bot(author),
                        source="review_comment",
                        path=c.get("path", ""),
                    )))
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"    Warning: failed to fetch inline comments for #{pr_num}: {e}")

        time.sleep(delay)
        results.append(pr_data)

    return results


def cmd_collect(args: argparse.Namespace) -> None:
    """Collect PR data from GitHub."""
    repo = args.repo
    days = args.days
    limit = args.limit
    top_n = args.top_n

    print(f"Collecting data for {repo} (last {days} days, limit {limit})...\n")

    # 1. Merged PRs
    print("Fetching merged PRs...")
    merged_raw = collect_prs(repo, days, limit, state="merged")
    merged_rows = to_rows(merged_raw, state="merged")
    compute_friction_scores(merged_rows)
    print(f"  Collected {len(merged_rows)} merged PRs")

    save_json(
        {
            "methodology": {
                "repo": repo,
                "window_days": days,
                "query_limit": limit,
                "state": "merged",
                "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            },
            "count": len(merged_rows),
            "prs": [asdict(r) for r in merged_rows],
        },
        OUTPUT_DIR / "collected_prs.json",
    )

    # 2. Closed-unmerged PRs
    print("\nFetching closed-unmerged PRs...")
    closed_raw = collect_prs(repo, days, limit, state="closed")
    closed_rows = to_rows(closed_raw, state="closed")
    compute_friction_scores(closed_rows)
    print(f"  Collected {len(closed_rows)} closed-unmerged PRs")

    save_json(
        {
            "methodology": {
                "repo": repo,
                "window_days": days,
                "query_limit": limit,
                "state": "closed-unmerged",
                "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            },
            "count": len(closed_rows),
            "prs": [asdict(r) for r in closed_rows],
        },
        OUTPUT_DIR / "collected_closed.json",
    )

    # 3. Open stale PRs
    print("\nFetching open PRs...")
    open_raw = collect_prs(repo, days, limit=500, state="open")
    open_rows = to_rows(open_raw, state="open")
    now = dt.datetime.now(dt.UTC)
    stale_14 = [r for r in open_rows if r.ttm_h >= 14 * 24]
    stale_30 = [r for r in open_rows if r.ttm_h >= 30 * 24]
    print(f"  Collected {len(open_rows)} open PRs ({len(stale_14)} stale 14d+, {len(stale_30)} stale 30d+)")

    save_json(
        {
            "methodology": {
                "repo": repo,
                "state": "open",
                "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            },
            "count": len(open_rows),
            "stale_14d": len(stale_14),
            "stale_30d": len(stale_30),
            "prs": [asdict(r) for r in open_rows],
        },
        OUTPUT_DIR / "collected_open.json",
    )

    # 4. Deep comments for top-N friction PRs
    print(f"\nSelecting top {top_n} friction PRs for deep comment analysis...")
    all_friction = sorted(merged_rows, key=lambda r: r.friction_score, reverse=True)
    top_merged = all_friction[:top_n]

    # Also include top-10 closed-unmerged by discussion volume
    top_closed = sorted(closed_rows, key=lambda r: r.reviews_total, reverse=True)[:10]

    deep_pr_numbers = [r.number for r in top_merged] + [r.number for r in top_closed]
    # Deduplicate while preserving order
    seen: set[int] = set()
    unique_numbers: list[int] = []
    for n in deep_pr_numbers:
        if n not in seen:
            seen.add(n)
            unique_numbers.append(n)

    print(f"  Will fetch comments for {len(unique_numbers)} PRs ({len(top_merged)} merged + {len(top_closed)} closed-unmerged, deduplicated)")

    deep_comments = fetch_deep_comments(repo, unique_numbers, delay=args.delay)
    print(f"  Fetched comments for {len(deep_comments)} PRs")

    total_comments = sum(len(d.comments) for d in deep_comments)
    non_bot_comments = sum(
        sum(1 for c in d.comments if not c.get("is_bot", False))
        for d in deep_comments
    )
    print(f"  Total comments: {total_comments} ({non_bot_comments} non-bot)")

    save_json(
        {
            "methodology": {
                "repo": repo,
                "top_n_merged": top_n,
                "top_n_closed": 10,
                "total_prs_fetched": len(deep_comments),
                "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            },
            "total_comments": total_comments,
            "non_bot_comments": non_bot_comments,
            "prs": [asdict(d) for d in deep_comments],
        },
        OUTPUT_DIR / "deep_comments.json",
    )

    print("\nCollection complete!")


# ---------------------------------------------------------------------------
# Analyze subcommand
# ---------------------------------------------------------------------------


def compute_baseline(rows: list[PrRow]) -> dict[str, Any]:
    """Compute aggregate baseline metrics."""
    small = [r for r in rows if r.files <= 3 and r.churn <= 80]
    large = [r for r in rows if r.files >= 10 or r.churn >= 400]

    ttm = [r.ttm_h for r in rows]
    reviews = [float(r.reviews_total) for r in rows]

    return {
        "sample_size": len(rows),
        "ttm_median_h": median(ttm),
        "ttm_p75_h": percentile(ttm, 0.75),
        "ttm_p90_h": percentile(ttm, 0.90),
        "ttm_mean_h": mean(ttm),
        "reviews_median": median(reviews),
        "reviews_mean": mean(reviews),
        "changes_requested_share": round(
            sum(1 for r in rows if r.changes_requested > 0) / len(rows), 3
        )
        if rows
        else 0.0,
        "review_rounds_median": median([float(r.review_rounds) for r in rows]),
        "review_rounds_mean": mean([float(r.review_rounds) for r in rows]),
        "small_pr_count": len(small),
        "small_pr_share": round(len(small) / len(rows), 3) if rows else 0.0,
        "small_pr_ttm_median_h": median([r.ttm_h for r in small]),
        "small_pr_reviews_median": median([float(r.reviews_total) for r in small]),
        "large_pr_count": len(large),
        "large_pr_share": round(len(large) / len(rows), 3) if rows else 0.0,
        "large_pr_ttm_median_h": median([r.ttm_h for r in large]),
        "large_pr_reviews_median": median([float(r.reviews_total) for r in large]),
        "churn_median": median([float(r.churn) for r in rows]),
        "churn_p90": percentile([float(r.churn) for r in rows], 0.90),
        "files_median": median([float(r.files) for r in rows]),
        "files_p90": percentile([float(r.files) for r in rows], 0.90),
    }


def compute_domain_friction(rows: list[PrRow], min_count: int = 5) -> dict[str, Any]:
    """Group PRs by title scope and file domain, compute per-group friction metrics."""
    # By title scope
    scope_groups: dict[str, list[PrRow]] = {}
    for r in rows:
        scope_groups.setdefault(r.title_scope, []).append(r)

    scope_table = []
    for scope, group in sorted(scope_groups.items()):
        if len(group) >= min_count:
            scope_table.append({
                "scope": scope,
                "count": len(group),
                "ttm_median_h": median([r.ttm_h for r in group]),
                "reviews_median": median([float(r.reviews_total) for r in group]),
                "changes_requested_rate": round(
                    sum(1 for r in group if r.changes_requested > 0) / len(group), 3
                ),
                "churn_median": median([float(r.churn) for r in group]),
                "review_rounds_median": median([float(r.review_rounds) for r in group]),
            })
    scope_table.sort(key=lambda x: x["reviews_median"], reverse=True)

    # By file domain (top-level path prefix)
    domain_groups: dict[str, list[PrRow]] = {}
    for r in rows:
        for d in r.file_domains:
            domain_groups.setdefault(d, []).append(r)

    domain_table = []
    for domain, group in sorted(domain_groups.items()):
        if len(group) >= min_count:
            domain_table.append({
                "domain": domain,
                "count": len(group),
                "ttm_median_h": median([r.ttm_h for r in group]),
                "reviews_median": median([float(r.reviews_total) for r in group]),
                "changes_requested_rate": round(
                    sum(1 for r in group if r.changes_requested > 0) / len(group), 3
                ),
                "churn_median": median([float(r.churn) for r in group]),
            })
    domain_table.sort(key=lambda x: x["reviews_median"], reverse=True)

    # By label
    label_groups: dict[str, list[PrRow]] = {}
    for r in rows:
        for l in r.labels:
            label_groups.setdefault(l, []).append(r)

    label_table = []
    for label, group in sorted(label_groups.items()):
        if len(group) >= min_count:
            label_table.append({
                "label": label,
                "count": len(group),
                "ttm_median_h": median([r.ttm_h for r in group]),
                "reviews_median": median([float(r.reviews_total) for r in group]),
            })
    label_table.sort(key=lambda x: x["reviews_median"], reverse=True)

    return {
        "by_scope": scope_table,
        "by_file_domain": domain_table,
        "by_label": label_table,
    }


def compute_theme_coding(
    deep_data: list[dict[str, Any]],
    theme_dict: dict[str, Any],
    include_bots: bool = False,
) -> dict[str, Any]:
    """Apply keyword-based theme classification to deep comments.

    If include_bots is False, only human comments are coded (default).
    If True, bot review comments (cursor[bot], sentry[bot], etc.) are
    included alongside humans — used for the combined analysis.
    """
    theme_frequency: dict[str, int] = {t: 0 for t in theme_dict}
    pr_themes: list[dict[str, Any]] = []

    for pr in deep_data:
        non_bot_comments = [
            c
            for c in pr.get("comments", [])
            if (include_bots or not c.get("is_bot", False))
            and not is_automated_comment(c.get("body", ""))
            and len(c.get("body", "")) >= 20
        ]
        all_text = "\n".join(c.get("body", "") for c in non_bot_comments).lower()

        matched_themes: dict[str, list[str]] = {}
        for theme_name, theme_info in theme_dict.items():
            keywords = theme_info.get("keywords", [])
            matching_quotes: list[str] = []

            for comment in non_bot_comments:
                body = comment.get("body", "")
                body_lower = body.lower()
                if any(kw.lower() in body_lower for kw in keywords):
                    # Extract first 300 chars as evidence quote
                    quote = body[:300].strip()
                    if len(body) > 300:
                        quote += "..."
                    matching_quotes.append(quote)

            if matching_quotes:
                matched_themes[theme_name] = matching_quotes[:5]  # Keep top 5 quotes
                theme_frequency[theme_name] += 1

        pr_themes.append({
            "pr_number": pr.get("pr_number"),
            "pr_url": pr.get("pr_url", ""),
            "pr_title": pr.get("pr_title", ""),
            "total_comments": len(pr.get("comments", [])),
            "non_bot_comments": len(non_bot_comments),
            "themes": list(matched_themes.keys()),
            "evidence": matched_themes,
        })

    # Sort themes by frequency
    theme_freq_sorted = sorted(
        theme_frequency.items(), key=lambda x: x[1], reverse=True
    )

    return {
        "theme_frequency": [
            {
                "theme": t,
                "count": c,
                "description": theme_dict.get(t, {}).get("description", ""),
                "share": round(c / len(deep_data), 3) if deep_data else 0.0,
            }
            for t, c in theme_freq_sorted
        ],
        "pr_themes": pr_themes,
    }


def compute_friction_predictors(rows: list[PrRow]) -> dict[str, Any]:
    """Analyze what factors predict high friction."""
    if not rows:
        return {}

    # High friction = top quartile by friction score
    sorted_rows = sorted(rows, key=lambda r: r.friction_score, reverse=True)
    q1_cutoff = len(sorted_rows) // 4
    high_friction_scores = {r.number for r in sorted_rows[:q1_cutoff]}

    def friction_rate(subset: list[PrRow]) -> float:
        if not subset:
            return 0.0
        return round(
            sum(1 for r in subset if r.number in high_friction_scores) / len(subset),
            3,
        )

    # By PR size bucket
    size_buckets = {
        "tiny (1-2 files, ≤30 churn)": [r for r in rows if r.files <= 2 and r.churn <= 30],
        "small (≤3 files, ≤80 churn)": [r for r in rows if r.files <= 3 and r.churn <= 80],
        "medium (4-9 files, 81-399 churn)": [
            r for r in rows if 4 <= r.files <= 9 and 81 <= r.churn <= 399
        ],
        "large (≥10 files OR ≥400 churn)": [r for r in rows if r.files >= 10 or r.churn >= 400],
    }

    # By reviewer count bucket
    reviewer_buckets = {
        "0-1 reviewers": [r for r in rows if r.reviews_total <= 1],
        "2-3 reviewers": [r for r in rows if 2 <= r.reviews_total <= 3],
        "4-6 reviewers": [r for r in rows if 4 <= r.reviews_total <= 6],
        "7+ reviewers": [r for r in rows if r.reviews_total >= 7],
    }

    # By title type
    type_groups: dict[str, list[PrRow]] = {}
    for r in rows:
        type_groups.setdefault(r.title_type, []).append(r)

    # By scope (top 15 scopes by count)
    scope_groups: dict[str, list[PrRow]] = {}
    for r in rows:
        scope_groups.setdefault(r.title_scope, []).append(r)
    top_scopes = sorted(scope_groups.items(), key=lambda x: len(x[1]), reverse=True)[:15]

    return {
        "high_friction_threshold": "top 25% by composite friction score",
        "high_friction_count": q1_cutoff,
        "by_size": [
            {"bucket": k, "count": len(v), "high_friction_rate": friction_rate(v)}
            for k, v in size_buckets.items()
        ],
        "by_reviewer_count": [
            {"bucket": k, "count": len(v), "high_friction_rate": friction_rate(v)}
            for k, v in reviewer_buckets.items()
        ],
        "by_title_type": sorted(
            [
                {"type": k, "count": len(v), "high_friction_rate": friction_rate(v)}
                for k, v in type_groups.items()
                if len(v) >= 5
            ],
            key=lambda x: x["high_friction_rate"],
            reverse=True,
        ),
        "by_scope": [
            {"scope": k, "count": len(v), "high_friction_rate": friction_rate(v)}
            for k, v in top_scopes
        ],
    }


def compute_abandoned_analysis(
    merged_rows: list[PrRow], closed_rows: list[PrRow]
) -> dict[str, Any]:
    """Compare abandoned PRs against merged high-friction PRs."""
    # High-discussion closed-unmerged
    high_discussion_closed = [r for r in closed_rows if r.reviews_total >= 10]
    high_discussion_closed.sort(key=lambda r: r.reviews_total, reverse=True)

    # Merged high-friction for comparison (top quartile)
    merged_sorted = sorted(merged_rows, key=lambda r: r.friction_score, reverse=True)
    merged_high_friction = merged_sorted[: len(merged_sorted) // 4]

    def group_stats(group: list[PrRow]) -> dict[str, Any]:
        if not group:
            return {"count": 0}
        return {
            "count": len(group),
            "ttm_median_h": median([r.ttm_h for r in group]),
            "reviews_median": median([float(r.reviews_total) for r in group]),
            "churn_median": median([float(r.churn) for r in group]),
            "files_median": median([float(r.files) for r in group]),
            "review_rounds_median": median([float(r.review_rounds) for r in group]),
        }

    return {
        "closed_unmerged_total": len(closed_rows),
        "closed_high_discussion": {
            "count": len(high_discussion_closed),
            "threshold": "≥10 review events",
            "share": round(len(high_discussion_closed) / len(closed_rows), 3)
            if closed_rows
            else 0.0,
            "top_examples": [
                {
                    "number": r.number,
                    "title": r.title,
                    "url": r.url,
                    "reviews_total": r.reviews_total,
                    "ttm_h": r.ttm_h,
                    "files": r.files,
                    "churn": r.churn,
                }
                for r in high_discussion_closed[:15]
            ],
        },
        "comparison": {
            "merged_high_friction": group_stats(merged_high_friction),
            "closed_high_discussion": group_stats(high_discussion_closed),
        },
    }


def compute_bot_review_analysis(
    deep_data: list[dict[str, Any]], theme_dict: dict[str, Any]
) -> dict[str, Any]:
    """Analyze automated review activity as a distinct friction source.

    Bot reviews from tools like cursor[bot], sentry[bot], sentry-warden[bot]
    represent real review work the developer must address — they're not noise.
    """
    from collections import Counter

    bot_authors: Counter = Counter()
    bot_sources: Counter = Counter()
    total_bot = 0
    total_human = 0
    prs_with_bots = 0
    bot_comment_lengths: list[int] = []

    # Per-PR bot vs human ratio
    pr_bot_ratios: list[dict[str, Any]] = []

    for pr in deep_data:
        bot_count = 0
        human_count = 0
        pr_bot_authors: Counter = Counter()
        for c in pr.get("comments", []):
            if is_automated_comment(c.get("body", "")):
                continue
            if len(c.get("body", "")) < 20:
                continue
            if c.get("is_bot", False):
                bot_count += 1
                total_bot += 1
                bot_authors[c["author"]] += 1
                bot_sources[c["source"]] += 1
                bot_comment_lengths.append(len(c.get("body", "")))
                pr_bot_authors[c["author"]] += 1
            else:
                human_count += 1
                total_human += 1

        if bot_count > 0:
            prs_with_bots += 1
        pr_bot_ratios.append(
            {
                "pr_number": pr.get("pr_number"),
                "pr_url": pr.get("pr_url", ""),
                "pr_title": pr.get("pr_title", ""),
                "bot_comments": bot_count,
                "human_comments": human_count,
                "bot_share": round(bot_count / (bot_count + human_count), 3)
                if (bot_count + human_count) > 0
                else 0.0,
                "top_bot": pr_bot_authors.most_common(1)[0][0]
                if pr_bot_authors
                else None,
            }
        )

    # PRs sorted by bot activity volume
    top_bot_activity = sorted(
        pr_bot_ratios, key=lambda x: x["bot_comments"], reverse=True
    )[:15]

    # PRs where bots dominate the discussion (bot_share >= 0.5)
    bot_dominated = [p for p in pr_bot_ratios if p["bot_share"] >= 0.5 and p["bot_comments"] >= 3]

    # Theme coding on bot comments only
    bot_theme_frequency: dict[str, int] = {t: 0 for t in theme_dict}
    for pr in deep_data:
        bot_comments = [
            c
            for c in pr.get("comments", [])
            if c.get("is_bot", False)
            and not is_automated_comment(c.get("body", ""))
            and len(c.get("body", "")) >= 20
        ]
        if not bot_comments:
            continue

        for theme_name, theme_info in theme_dict.items():
            keywords = theme_info.get("keywords", [])
            for comment in bot_comments:
                body_lower = comment.get("body", "").lower()
                if any(kw.lower() in body_lower for kw in keywords):
                    bot_theme_frequency[theme_name] += 1
                    break  # Count each PR once per theme

    bot_theme_sorted = sorted(
        bot_theme_frequency.items(), key=lambda x: x[1], reverse=True
    )

    return {
        "total_bot_comments": total_bot,
        "total_human_comments": total_human,
        "bot_share_of_review": round(total_bot / (total_bot + total_human), 3)
        if (total_bot + total_human) > 0
        else 0.0,
        "prs_with_bot_activity": prs_with_bots,
        "prs_total": len(deep_data),
        "prs_with_bot_share": round(prs_with_bots / len(deep_data), 3)
        if deep_data
        else 0.0,
        "bot_authors": [
            {"author": a, "count": c} for a, c in bot_authors.most_common()
        ],
        "bot_sources": dict(bot_sources),
        "avg_bot_comment_length": round(
            sum(bot_comment_lengths) / len(bot_comment_lengths)
        )
        if bot_comment_lengths
        else 0,
        "bot_dominated_prs": {
            "count": len(bot_dominated),
            "threshold": "bot_share >= 0.5 AND bot_comments >= 3",
            "examples": sorted(bot_dominated, key=lambda x: x["bot_share"], reverse=True)[:10],
        },
        "top_bot_activity_prs": top_bot_activity,
        "bot_theme_frequency": [
            {
                "theme": t,
                "count": c,
                "share": round(c / len(deep_data), 3) if deep_data else 0.0,
                "description": theme_dict.get(t, {}).get("description", ""),
            }
            for t, c in bot_theme_sorted
        ],
    }


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze collected PR data."""
    print("Loading collected data...")

    merged_data = load_json(OUTPUT_DIR / "collected_prs.json")
    closed_data = load_json(OUTPUT_DIR / "collected_closed.json")
    open_data = load_json(OUTPUT_DIR / "collected_open.json")
    deep_data = load_json(OUTPUT_DIR / "deep_comments.json")

    merged_rows = [PrRow(**pr) for pr in merged_data["prs"]]
    closed_rows = [PrRow(**pr) for pr in closed_data["prs"]]
    open_rows = [PrRow(**pr) for pr in open_data["prs"]]

    # Recompute friction scores (they're stored but recompute ensures consistency)
    compute_friction_scores(merged_rows)

    print(f"  Merged: {len(merged_rows)}, Closed: {len(closed_rows)}, Open: {len(open_rows)}")
    print(f"  Deep comments: {len(deep_data['prs'])} PRs, {deep_data['total_comments']} comments")

    # 1. Baseline
    print("\nComputing baseline metrics...")
    baseline = compute_baseline(merged_rows)

    # 2. Domain friction map
    print("Computing domain friction map...")
    domain_friction = compute_domain_friction(merged_rows)

    # 3. Theme coding
    print("Computing theme coding...")
    if THEME_DICT_PATH.exists():
        theme_dict = load_json(THEME_DICT_PATH)
        themes = compute_theme_coding(deep_data["prs"], theme_dict)
        bot_review = compute_bot_review_analysis(deep_data["prs"], theme_dict)
    else:
        print(f"  Warning: {THEME_DICT_PATH} not found. Skipping theme analysis.")
        themes = {"theme_frequency": [], "pr_themes": []}
        bot_review = {}

    # 4. Friction predictors
    print("Computing friction predictors...")
    predictors = compute_friction_predictors(merged_rows)

    # 5. Abandoned PR analysis
    print("Computing abandoned PR analysis...")
    abandoned = compute_abandoned_analysis(merged_rows, closed_rows)

    # 6. Top lists
    top_review_volume = sorted(merged_rows, key=lambda r: r.reviews_total, reverse=True)[:15]
    top_ttm = sorted(merged_rows, key=lambda r: r.ttm_h, reverse=True)[:15]
    top_friction = sorted(merged_rows, key=lambda r: r.friction_score, reverse=True)[:15]

    # 7. Open/stale analysis
    stale_14 = [r for r in open_rows if r.ttm_h >= 14 * 24]
    stale_30 = [r for r in open_rows if r.ttm_h >= 30 * 24]
    stale_high_discussion = sorted(
        [r for r in stale_14 if r.reviews_total >= 5],
        key=lambda r: r.reviews_total,
        reverse=True,
    )

    report = {
        "methodology": {
            "repo": merged_data["methodology"]["repo"],
            "window_days": merged_data["methodology"]["window_days"],
            "query_limit": merged_data["methodology"]["query_limit"],
            "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
            "merged_sample": len(merged_rows),
            "closed_sample": len(closed_rows),
            "open_sample": len(open_rows),
            "deep_comment_prs": len(deep_data["prs"]),
        },
        "baseline": baseline,
        "domain_friction": domain_friction,
        "themes": themes,
        "bot_review": bot_review,
        "friction_predictors": predictors,
        "abandoned": abandoned,
        "stale": {
            "open_total": len(open_rows),
            "stale_14d": len(stale_14),
            "stale_30d": len(stale_30),
            "stale_high_discussion": [
                {
                    "number": r.number,
                    "title": r.title,
                    "url": r.url,
                    "reviews_total": r.reviews_total,
                    "ttm_h": r.ttm_h,
                }
                for r in stale_high_discussion[:10]
            ],
        },
        "top_lists": {
            "by_review_volume": [asdict(r) for r in top_review_volume],
            "by_ttm": [asdict(r) for r in top_ttm],
            "by_friction_score": [asdict(r) for r in top_friction],
        },
    }

    save_json(report, OUTPUT_DIR / "analysis_report.json")
    print("\nAnalysis complete!")


# ---------------------------------------------------------------------------
# Report subcommand
# ---------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> None:
    """Generate narrative-ready JSON from analysis report."""
    print("Loading analysis report...")
    report = load_json(OUTPUT_DIR / "analysis_report.json")

    # Structure data by page for easy MDX authoring
    narrative = {
        "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "pages": {
            "index": {
                "repo": report["methodology"]["repo"],
                "window_days": report["methodology"]["window_days"],
                "merged_sample": report["methodology"]["merged_sample"],
                "closed_sample": report["methodology"]["closed_sample"],
                "key_findings": {
                    "ttm_median_h": report["baseline"]["ttm_median_h"],
                    "ttm_p90_h": report["baseline"]["ttm_p90_h"],
                    "reviews_median": report["baseline"]["reviews_median"],
                    "large_pr_ttm_median_h": report["baseline"]["large_pr_ttm_median_h"],
                    "top_theme": report["themes"]["theme_frequency"][0]
                    if report["themes"]["theme_frequency"]
                    else None,
                    "abandoned_high_discussion": report["abandoned"]["closed_high_discussion"]["count"],
                },
            },
            "methodology": report["methodology"],
            "baseline": report["baseline"],
            "friction_map": report["domain_friction"],
            "themes": report["themes"],
            "abandoned": {
                **report["abandoned"],
                "stale": report["stale"],
            },
            "top_lists": report["top_lists"],
            "friction_predictors": report["friction_predictors"],
        },
    }

    save_json(narrative, OUTPUT_DIR / "narrative_data.json")
    print("Narrative data generated!")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze PR review friction in a GitHub repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s collect --repo getsentry/sentry --days 90 --limit 500
  %(prog)s analyze
  %(prog)s report
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect
    p_collect = subparsers.add_parser("collect", help="Fetch PR data from GitHub")
    p_collect.add_argument(
        "--repo",
        default="getsentry/sentry",
        help="GitHub repo in owner/name format (default: getsentry/sentry)",
    )
    p_collect.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of trailing days to query (default: 90)",
    )
    p_collect.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum PRs to fetch per state (default: 500)",
    )
    p_collect.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top friction PRs for deep comment analysis (default: 50)",
    )
    p_collect.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between API calls in seconds (default: 0.5)",
    )

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze collected data")

    # report
    p_report = subparsers.add_parser("report", help="Generate narrative-ready JSON")

    args = parser.parse_args()

    if args.command == "collect":
        cmd_collect(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
