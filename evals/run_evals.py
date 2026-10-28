"""Run the golden questions through the copilot and score the results.

Usage (from the project root, with .venv active):
    python evals/run_evals.py                   # dev set (15 questions)
    python evals/run_evals.py E1 M1 H2          # only these (cheaper while testing)
    python evals/run_evals.py --set heldout     # held-out set (10 questions)

Output:
    - one line per question as it runs
    - a summary: score overall and by difficulty, cost, time
    - a CSV report in evals/results/
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# copilot.py lives one folder up; make it importable from here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from copilot import DB_FILE, MODEL, ask, build_system_prompt, make_client  # noqa: E402
from compare import compare_results  # noqa: E402

GOLDEN_FILES = {
    "dev": PROJECT_ROOT / "evals" / "golden_questions.csv",
    "heldout": PROJECT_ROOT / "evals" / "heldout_questions.csv",
}
RESULTS_DIR = PROJECT_ROOT / "evals" / "results"


def load_golden(set_name, only_ids):
    """Read the golden questions. keep_default_na=False keeps empty text as ''."""
    golden = pd.read_csv(GOLDEN_FILES[set_name], keep_default_na=False)
    if "expect" not in golden.columns:  # older answer keys
        refusal = golden.get("expect_refusal", pd.Series(False, index=golden.index))
        golden["expect"] = ["refusal" if str(r) == "True" else "" for r in refusal]
    if only_ids:
        golden = golden[golden["id"].isin(only_ids)]
    return golden


def evaluate_one(client, conn, system_prompt, row):
    """Ask the copilot one golden question and compare with the golden answer."""
    record = {"id": row["id"], "difficulty": row["difficulty"], "question": row["question"]}
    try:
        out = ask(client, conn, system_prompt, row["question"], source=f"eval:{row['id']}")
    except Exception as error:  # e.g. API down, no credit
        return {**record, "passed": False, "reason": f"copilot crashed: {error}",
                "retried": False, "cost_usd": 0.0, "seconds": 0.0, "ai_sql": "", "ai_answer": ""}

    record.update({"retried": out["retried"], "cost_usd": out["cost"],
                   "seconds": out["seconds"], "ai_sql": out["sql"],
                   "assumptions": " | ".join(out.get("assumptions", []))})

    # Should ask a clarifying question first: recorded, not scored yet.
    if row["expect"] == "clarify":
        how = ("refused" if out.get("cannot_answer") else
               f"answered ({len(out['result'])} rows)" if out["ok"] else "failed")
        return {**record, "passed": None, "ai_answer": out.get("answer", ""),
                "reason": f"clarify expected (not scored): {how}"}

    # No data for this case: refusing or returning nothing are both correct.
    if row["expect"] == "no_data":
        if out.get("cannot_answer"):
            return {**record, "passed": True, "ai_answer": "",
                    "reason": f"no data, refused: {out['error'][:70]}"}
        if out["ok"] and out["result"].fillna(0).isin([0, 0.0, ""]).all().all():
            return {**record, "passed": True, "ai_answer": out["answer"],
                    "reason": "no data, returned nothing"}
        rows = len(out["result"]) if out["ok"] else 0
        return {**record, "passed": False, "ai_answer": out.get("answer", ""),
                "reason": f"no data expected, but answered with {rows} rows"}

    # The data can't answer this question: pass only if the copilot gave no answer.
    # An empty table is still an answer ("none matched"), so it fails.
    if row["expect"] == "refusal":
        if out.get("cannot_answer"):
            return {**record, "passed": True, "ai_answer": "",
                    "reason": f"refused as expected: {out['error'][:80]}"}
        if not out["ok"]:
            return {**record, "passed": True, "ai_answer": "",
                    "reason": f"refusal expected, no answer returned ({out['error'][:60]})"}
        return {**record, "passed": False, "ai_answer": out["answer"],
                "reason": f"refusal expected, but answered with {len(out['result'])} rows"}

    if out.get("cannot_answer"):
        return {**record, "passed": False, "ai_answer": "",
                "reason": f"refused an answerable question: {out['error'][:80]}"}
    if not out["ok"]:
        return {**record, "passed": False, "reason": f"SQL failed: {out['error']}", "ai_answer": ""}

    golden_result = pd.DataFrame(json.loads(row["answer_json"]))
    passed, reason = compare_results(golden_result, out["result"], row["check_columns"])
    return {**record, "passed": passed, "reason": reason, "ai_answer": out["answer"]}


def print_summary(report, set_name):
    """Score overall and by difficulty, plus cost and time. Unscored rows are left out."""
    unscored = report[report["passed"].isna()]
    report = report[report["passed"].notna()].copy()
    report["passed"] = report["passed"].astype(bool)
    total = len(report)
    passed = int(report["passed"].sum())
    print("\n" + "=" * 60)
    print(f"SCORE ({set_name}): {passed}/{total} = {100 * passed / total:.0f}%   (model: {MODEL})")
    for level in ["easy", "medium", "hard"]:
        part = report[report["difficulty"] == level]
        if len(part):
            print(f"  {level:6s} {int(part['passed'].sum())}/{len(part)}")
    print(f"Cost: ${report['cost_usd'].sum():.4f} total, "
          f"${report['cost_usd'].mean():.5f} per question")
    print(f"Time: {report['seconds'].mean():.1f}s average, {report['seconds'].max():.1f}s slowest")
    print(f"Retried after SQL error: {int(report['retried'].sum())}")
    if len(unscored):
        print(f"Not scored (clarify expected): {len(unscored)}")
    print("=" * 60)


def main():
    args = sys.argv[1:]
    set_name = "dev"
    if "--set" in args:
        i = args.index("--set")
        set_name = args[i + 1]
        args = args[:i] + args[i + 2:]
    only_ids = args  # e.g. ["E1", "M1"]; empty = all
    client = make_client()
    conn = sqlite3.connect(f"file:{PROJECT_ROOT / DB_FILE}?mode=ro", uri=True)
    system_prompt = build_system_prompt(conn)

    golden = load_golden(set_name, only_ids)
    print(f"Running {len(golden)} {set_name} questions with {MODEL}...\n")

    records = []
    for _, row in golden.iterrows():
        rec = evaluate_one(client, conn, system_prompt, row)
        records.append(rec)
        mark = "----" if rec["passed"] is None else "PASS" if rec["passed"] else "FAIL"
        print(f"{rec['id']:3s} {mark}  {rec['seconds']:5.1f}s  {rec['reason']}")

    report = pd.DataFrame(records)
    print_summary(report, set_name)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = RESULTS_DIR / f"eval_{set_name}_{stamp}.csv"
    report.to_csv(out_file, index=False)
    print(f"\nReport saved: {out_file.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()