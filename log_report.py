"""Summarise logs/calls.jsonl: usage, outcomes, cost, speed and what gets asked.

Usage (from the project root):
    python log_report.py              # real use only (eval runs excluded)
    python log_report.py --eval       # eval runs only
    python log_report.py --all        # everything

On AWS the same questions would be answered with CloudWatch Logs Insights or
Athena over the logs in S3.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

LOG_FILE = Path(__file__).resolve().parent / "logs" / "calls.jsonl"


def load(which):
    if not LOG_FILE.exists():
        sys.exit(f"No log yet: {LOG_FILE}")
    rows = [json.loads(line) for line in LOG_FILE.read_text(encoding="utf-8").splitlines() if line]
    df = pd.DataFrame(rows)
    is_eval = df["source"].str.startswith("eval")
    if which == "eval":
        df = df[is_eval]
    elif which == "real":
        df = df[~is_eval]
    return df


def pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "-"


def main():
    which = "eval" if "--eval" in sys.argv else "all" if "--all" in sys.argv else "real"
    df = load(which)
    n = len(df)
    if n == 0:
        sys.exit(f"No {which} calls in the log.")

    print(f"\nCALLS ({which}): {n}   from {df['timestamp'].min()[:10]} to {df['timestamp'].max()[:10]}")
    print(f"Users: {df['user'].nunique()}   Prompt versions: {', '.join(sorted(df['prompt_version'].unique()))}")

    print("\nOUTCOMES")
    for outcome, count in df["outcome"].value_counts().items():
        print(f"  {outcome:14s} {count:5d}  {pct(count, n)}")
    print(f"  retried        {int(df['retried'].sum()):5d}  {pct(df['retried'].sum(), n)}")

    print("\nCOST")
    print(f"  total ${df['cost_usd'].sum():.4f}   per question ${df['cost_usd'].mean():.5f}"
          f"   per 1,000 questions ${1000 * df['cost_usd'].mean():.2f}")
    print(f"  tokens per question: {df['tokens_in'].mean():,.0f} in, {df['tokens_out'].mean():,.0f} out")

    print("\nSPEED (seconds)")
    s = df["seconds"]
    print(f"  average {s.mean():.1f}   median {s.median():.1f}   95th pct {s.quantile(0.95):.1f}   max {s.max():.1f}")
    stages = pd.DataFrame(list(df["stage_seconds"])).fillna(0)
    total = stages.sum().sum()
    for stage, secs in stages.sum().sort_values(ascending=False).items():
        print(f"  {stage:13s} {pct(secs, total):>4s} of time")

    print("\nVIEWS USED (share of answered questions)")
    answered = df[df["outcome"] == "answered"]
    views = Counter(v for sql in answered["sql"] for v in set(re.findall(r"\bv_\w+", sql)))
    raw_only = sum(1 for sql in answered["sql"] if not re.search(r"\bv_\w+", sql))
    for view, count in views.most_common():
        print(f"  {view:26s} {count:4d}  {pct(count, len(answered))}")
    print(f"  {'(raw tables only)':26s} {raw_only:4d}  {pct(raw_only, len(answered))}")

    refused = df[df["outcome"] == "cannot_answer"]
    if len(refused):
        print("\nREFUSED (data not available)")
        for q in refused["question"].head(10):
            print(f"  - {q}")

    failed = df[df["outcome"] == "failed"]
    if len(failed):
        print("\nFAILED (SQL error after retry)")
        for _, r in failed.head(10).iterrows():
            print(f"  - {r['question']}  ->  {str(r['error'])[:70]}")

    print("\nMOST ASKED")
    for q, count in df["question"].str.strip().str.lower().value_counts().head(5).items():
        print(f"  {count:3d}x  {q[:80]}")
    print()


if __name__ == "__main__":
    main()