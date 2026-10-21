"""Run every golden query and save question + SQL + answer to a CSV.

Run from the project root:  python evals/build_golden.py
Output: evals/golden_questions.csv (the answer key used by evals/run_evals.py)
"""

import json
import re
import sqlite3

import pandas as pd

SQL_FILE = "evals/golden_queries.sql"
OUT_FILE = "evals/golden_questions.csv"
DB_FILE = "logistics.db"


def split_queries(text):
    """Split the .sql file into blocks, one per question (E1, M2, H3, ...)."""
    blocks = re.split(r"\n(?=-- -{20,}\n-- [EMH]\d\.)", text)
    queries = []
    for block in blocks:
        header = re.search(r"-- ([EMH]\d)\. (.*)", block)
        if not header:
            continue  # the file's intro comment, not a query
        qid, question = header.group(1), header.group(2).strip()
        # Questions that wrap onto a second comment line ("--     last quarter.")
        follow = re.search(rf"-- {qid}\. .*\n--\s{{4,}}(.*)", block)
        if follow:
            question += " " + follow.group(1).strip()
        level = {"E": "easy", "M": "medium", "H": "hard"}[qid[0]]
        # "-- Check: col_a, col_b|col_c" names the columns that ARE the answer.
        check = re.search(r"-- Check: (.*)", block)
        check_columns = check.group(1).strip() if check else ""
        if check_columns.startswith("("):  # e.g. "(expect no rows)"
            check_columns = ""
        sql = block.strip().rstrip(";")
        queries.append({"id": qid, "difficulty": level, "question": question,
                        "check_columns": check_columns, "sql": sql})
    return queries


def main():
    conn = sqlite3.connect(DB_FILE)
    queries = split_queries(open(SQL_FILE).read())

    rows = []
    for q in queries:
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

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(rows)} golden questions to {OUT_FILE}")


if __name__ == "__main__":
    main()