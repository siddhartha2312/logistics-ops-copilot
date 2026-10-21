"""Run the golden questions through the copilot and score the results.

Usage (from the project root, with .venv active):
    python evals/run_evals.py            # all 15 questions
    python evals/run_evals.py E1 M1 H2   # only these (cheaper while testing)

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

import anthropic
import pandas as pd
from dotenv import load_dotenv

# copilot.py lives one folder up; make it importable from here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from copilot import DB_FILE, MODEL, ask, build_system_prompt  # noqa: E402
from compare import compare_results  # noqa: E402

GOLDEN_FILE = PROJECT_ROOT / "evals" / "golden_questions.csv"
RESULTS_DIR = PROJECT_ROOT / "evals" / "results"


def load_golden(only_ids):
    """Read the golden questions. keep_default_na=False keeps empty text as ''."""
    golden = pd.read_csv(GOLDEN_FILE, keep_default_na=False)
    if only_ids:
        golden = golden[golden["id"].isin(only_ids)]
    return golden


def evaluate_one(client, conn, system_prompt, row):
    """Ask the copilot one golden question and compare with the golden answer."""
    record = {"id": row["id"], "difficulty": row["difficulty"], "question": row["question"]}
    try:
        out = ask(client, conn, system_prompt, row["question"])
    except Exception as error:  # e.g. API down, no credit
        return {**record, "passed": False, "reason": f"copilot crashed: {error}",
                "retried": False, "cost_usd": 0.0, "seconds": 0.0, "ai_sql": "", "ai_answer": ""}

    record.update({"retried": out["retried"], "cost_usd": out["cost"],
                   "seconds": out["seconds"], "ai_sql": out["sql"]})
    if not out["ok"]:
        return {**record, "passed": False, "reason": f"SQL failed: {out['error']}", "ai_answer": ""}

    golden_result = pd.DataFrame(json.loads(row["answer_json"]))
    passed, reason = compare_results(golden_result, out["result"], row["check_columns"])
    return {**record, "passed": passed, "reason": reason, "ai_answer": out["answer"]}


def print_summary(report):
    """Score overall and by difficulty, plus cost and time."""
    total = len(report)
    passed = int(report["passed"].sum())
    print("\n" + "=" * 60)
    print(f"SCORE: {passed}/{total} = {100 * passed / total:.0f}%   (model: {MODEL})")
    for level in ["easy", "medium", "hard"]:
        part = report[report["difficulty"] == level]
        if len(part):
            print(f"  {level:6s} {int(part['passed'].sum())}/{len(part)}")
    print(f"Cost: ${report['cost_usd'].sum():.4f} total, "
          f"${report['cost_usd'].mean():.5f} per question")
    print(f"Time: {report['seconds'].mean():.1f}s average, {report['seconds'].max():.1f}s slowest")
    print(f"Retried after SQL error: {int(report['retried'].sum())}")
    print("=" * 60)


def main():
    only_ids = sys.argv[1:]  # e.g. ["E1", "M1"]; empty = all
    load_dotenv(PROJECT_ROOT / ".env")
    client = anthropic.Anthropic()
    conn = sqlite3.connect(f"file:{PROJECT_ROOT / DB_FILE}?mode=ro", uri=True)
    system_prompt = build_system_prompt(conn)

    golden = load_golden(only_ids)
    print(f"Running {len(golden)} golden questions with {MODEL}...\n")

    records = []
    for _, row in golden.iterrows():
        rec = evaluate_one(client, conn, system_prompt, row)
        records.append(rec)
        mark = "PASS" if rec["passed"] else "FAIL"
        print(f"{rec['id']:3s} {mark}  {rec['seconds']:5.1f}s  {rec['reason']}")

    report = pd.DataFrame(records)
    print_summary(report)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = RESULTS_DIR / f"eval_{stamp}.csv"
    report.to_csv(out_file, index=False)
    print(f"\nReport saved: {out_file.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()