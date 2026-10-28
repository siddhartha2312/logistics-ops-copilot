"""Run every golden query and save question + SQL + answer to a CSV.

Run from the project root:
    python evals/build_golden.py                 # dev set
    python evals/build_golden.py --set heldout   # held-out set
Output: evals/golden_questions.csv or evals/heldout_questions.csv
(the answer key used by evals/run_evals.py)
"""

import json
import re
import sqlite3
import sys

import pandas as pd

SETS = {
    "dev": ("evals/golden_queries.sql", "evals/golden_questions.csv"),
    "heldout": ("evals/heldout_queries.sql", "evals/heldout_questions.csv"),
}
DB_FILE = "logistics.db"
LEVELS = {"E": "easy", "M": "medium", "H": "hard"}


def split_queries(text):
    """Split the .sql file into blocks, one per question (E1, M2, T3, ...)."""
    blocks = re.split(r"\n(?=-- -{20,}\n-- [A-Z]\d+\.)", text)
    queries = []
    for block in blocks:
        header = re.search(r"-- ([A-Z]\d+)\. (.*)", block)
        if not header:
            continue  # the file's intro comment, not a query
        qid, question = header.group(1), header.group(2).strip()
        # Questions that wrap onto a second comment line ("--     last quarter.")
        follow = re.search(rf"-- {qid}\. .*\n--\s{{4,}}(.*)", block)
        if follow:
            question += " " + follow.group(1).strip()
        # Level comes from the ID letter (E/M/H) or a "-- Level:" line.
        level_line = re.search(r"-- Level: (\w+)", block)
        level = level_line.group(1) if level_line else LEVELS[qid[0]]
        # "-- Expect: refusal | no_data | clarify" = no SQL answer key:
        #   refusal = the data can't answer it; no_data = refusing or "nothing found"
        #   are both correct; clarify = should ask first (recorded, not scored yet).
        expect_line = re.search(r"-- Expect: (\w+)", block)
        expect = expect_line.group(1) if expect_line else ""
        expect_refusal = expect == "refusal"
        # "-- Check: col_a, col_b|col_c" names the columns that ARE the answer.
        check = re.search(r"-- Check: (.*)", block)
        check_columns = check.group(1).strip() if check else ""
        if check_columns.startswith("("):  # e.g. "(expect no rows)"
            check_columns = ""
        sql = "" if expect else block.strip().rstrip(";")
        queries.append({"id": qid, "difficulty": level, "question": question,
                        "check_columns": check_columns, "expect": expect,
                        "expect_refusal": expect_refusal, "sql": sql})
    return queries


def main():
    set_name = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "dev"
    sql_file, out_file = SETS[set_name]
    conn = sqlite3.connect(DB_FILE)
    queries = split_queries(open(sql_file).read())

    rows = []
    for q in queries:
        if q["expect"]:
            rows.append({**q, "answer_rows": 0, "answer_json": "[]"})
            print(f"{q['id']:3s} {q['difficulty']:6s} {q['expect']:10s} {q['question'][:60]}")
            continue
        result = pd.read_sql(q["sql"], conn)
        rows.append(
            {
                **q,
                "answer_rows": len(result),
                # The full result, stored as JSON so it fits in one CSV cell.
                "answer_json": json.dumps(result.to_dict("records"), default=str),
            }
        )
        print(f"{q['id']:3s} {q['difficulty']:6s} {len(result):4d} rows  {q['question'][:60]}")

    pd.DataFrame(rows).to_csv(out_file, index=False)
    print(f"\nSaved {len(rows)} {set_name} questions to {out_file}")


if __name__ == "__main__":
    main()