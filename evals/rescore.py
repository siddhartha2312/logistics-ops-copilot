"""Re-score a saved eval run against the CURRENT golden answers.

Use this after a golden answer changes (see evals/golden_changes.md), so old and
new copilot versions are compared against the same answer key.

It re-runs the SQL the copilot wrote in that run. No API calls, no cost.

Usage (from the project root):
    python evals/rescore.py evals/results/eval_20261021_1217.csv
    python evals/rescore.py evals/results/eval_heldout_20261022_1613.csv --set heldout
"""

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from compare import compare_results

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_FILES = {
    "dev": PROJECT_ROOT / "evals" / "golden_questions.csv",
    "heldout": PROJECT_ROOT / "evals" / "heldout_questions.csv",
}
DB_FILE = PROJECT_ROOT / "logistics.db"


def main():
    if len(sys.argv) < 2:
        print("Usage: python evals/rescore.py <saved report csv> [--set heldout]")
        sys.exit(1)
    set_name = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "dev"
    report = pd.read_csv(sys.argv[1], keep_default_na=False)
    report["passed"] = report["passed"].astype(object)  # holds True/False/None
    golden = pd.read_csv(GOLDEN_FILES[set_name], keep_default_na=False).set_index("id")
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)

    changed = 0
    for i, row in report.iterrows():
        gold_row = golden.loc[row["id"]]
        gold_result = pd.DataFrame(json.loads(gold_row["answer_json"]))
        expect = str(gold_row.get("expect", "")) or (
            "refusal" if str(gold_row.get("expect_refusal", "")) == "True" else "")
        refusal = expect == "refusal"
        if expect == "clarify":  # not scored yet
            print(f"{row['id']:3s} ----  clarify expected (not scored)")
            report.at[i, "passed"] = None
            continue
        if not str(row["ai_sql"]).strip():  # the copilot refused: no SQL was written
            passed = expect in ("refusal", "no_data")
            reason = "refused as expected" if passed else "refused an answerable question"
            was = str(row["passed"]) == "True"
            flag = "  <- changed" if passed != was else ""
            changed += passed != was
            print(f"{row['id']:3s} {'PASS' if passed else 'FAIL'}  {reason}{flag}")
            report.at[i, "passed"] = passed
            report.at[i, "reason"] = reason
            continue
        try:
            ai_result = pd.read_sql(row["ai_sql"], conn)
            if refusal:  # an answer of any size, even empty, is not a refusal
                passed, reason = False, f"refusal expected, but answered with {len(ai_result)} rows"
            elif expect == "no_data":
                passed = (ai_result.empty or bool(ai_result.fillna(0).isin([0, 0.0, ""]).all().all())
                          or bool(ai_result.isna().all().any()))
                reason = "no data, returned nothing" if passed else f"no data expected, but {len(ai_result)} rows"
            else:
                passed, reason = compare_results(gold_result, ai_result, gold_row["check_columns"])
        except Exception as error:
            if refusal:
                passed, reason = True, "refusal expected, no answer returned"
            else:
                passed, reason = False, f"SQL failed: {error}"
        was = str(row["passed"]) == "True"
        flag = "  <- changed" if passed != was else ""
        changed += passed != was
        print(f"{row['id']:3s} {'PASS' if passed else 'FAIL'}  {reason}{flag}")
        report.at[i, "passed"] = passed
        report.at[i, "reason"] = reason

    report = report[report["passed"].notna() & (report["passed"].astype(str) != "")].copy()
    report["passed"] = report["passed"].astype(str).isin(["True", "1", "1.0"])  # mixed types → bool
    total, ok = len(report), int(report["passed"].sum())
    print(f"\nRe-scored: {ok}/{total} = {100 * ok / total:.0f}%  ({changed} changed)")
    for level in ["easy", "medium", "hard"]:
        part = report[report["difficulty"] == level]
        print(f"  {level:6s} {int(part['passed'].astype(bool).sum())}/{len(part)}")


if __name__ == "__main__":
    main()