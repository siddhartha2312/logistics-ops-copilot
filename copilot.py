"""Logistics Ops Copilot: turn a business question into SQL and a plain-English answer.

Usage (from the project root, with .venv active):
    python copilot.py "How many shipments were cancelled last quarter?"

Flow: question -> SQL (Claude) -> run on a read-only database
      -> one retry if the SQL fails -> plain-English answer (Claude).
Context sent with every question: schema, allowed values, docs/glossary.md,
docs/sql_examples.md.
"""

import re
import sqlite3
import sys
import time
from pathlib import Path

import anthropic
import pandas as pd
from dotenv import load_dotenv

MODEL = "claude-haiku-5-5"
DB_FILE = "logistics.db"
DOCS_DIR = Path(__file__).resolve().parent / "docs"
GLOSSARY_FILE = DOCS_DIR / "glossary.md"
EXAMPLES_FILE = DOCS_DIR / "sql_examples.md"

# Limits so a user never waits on a runaway query or a hanging API call.
SQL_TIMEOUT_S = 30   # stop any single SQL query after this many seconds
API_TIMEOUT_S = 60   # stop any single Claude call after this many seconds

# USD per million tokens for MODEL (check the pricing page if you change model).
PRICE_IN = 0.10
PRICE_OUT = 0.50

# Columns with a small, fixed set of values. Their exact values go in the prompt.
CATEGORY_COLUMNS = {
    "shipments": ["status", "hold_reason", "service_level"],
    "truck_runs": ["run_type", "run_outcome", "carrier"],
    "shippers": ["country", "status", "operating_days", "account_manager"],
    "nodes": ["node_type"],
    "exceptions": ["exception_type"],
}

ANSWER_PROMPT = """You explain database query results to a logistics operations
manager who does not read SQL.

Rules:
- Answer the question in 2-4 plain sentences. Lead with the direct answer.
- Use ONLY numbers that appear in the result. Never estimate or invent a number.
- State the time period and filters the query used, so the reader knows what is counted.
- If the result is empty, say that no data matched.
- Do not mention SQL, tables or column names.
"""


def get_schema(conn):
    """List every table with its columns and types."""
    lines = []
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for (table,) in tables:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_text = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        lines.append(f"{table}({col_text})")
    return "\n".join(lines)


def get_allowed_values(conn):
    """List the exact values each category column can take."""
    lines = []
    for table, cols in CATEGORY_COLUMNS.items():
        for col in cols:
            rows = conn.execute(
                f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL ORDER BY 1"
            ).fetchall()
            values = [r[0] for r in rows]
            lines.append(f"{table}.{col}: {values}")
    return "\n".join(lines)


def build_system_prompt(conn):
    """Instructions + database facts + business definitions + worked examples."""
    glossary = GLOSSARY_FILE.read_text()
    examples = EXAMPLES_FILE.read_text()
    return f"""You are a SQL expert for a logistics company's SQLite database.
Write ONE SQLite query that answers the user's question.

Rules:
- Use only the tables and columns listed below. Never invent a column.
- Use only the exact category values listed below. They are case-sensitive.
- Follow the business definitions below exactly. When the question uses a term
  defined there (on-time, attainment, utilisation, avoidable cost, peak, week...),
  use that definition, not your own.
- The worked examples show the correct patterns. Reuse their structure.
- This is SQLite: use date() and strftime(). There is no DATE_TRUNC or EXTRACT.
  Dates are stored as 'YYYY-MM-DD' text; timestamps as 'YYYY-MM-DD HH:MM:SS'.
- Read-only: write a SELECT (or WITH ... SELECT) query only.
- Reply with only the SQL inside a ```sql code block. No explanation.

Schema:
{get_schema(conn)}

Allowed values:
{get_allowed_values(conn)}

Business definitions:
{glossary}

Worked examples:
{examples}
"""


def extract_sql(text):
    """Pull the SQL out of the ```sql ... ``` block in the model's reply."""
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()  # fallback: the model replied with bare SQL


def ask_claude(client, system_prompt, messages):
    """Send a conversation to Claude. Return the reply text, usage and cost."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,  # room for thinking + a long query (2000 cut off H4)
        system=system_prompt,
        messages=messages,
    )
    # The reply can hold several blocks (e.g. thinking, then text). Keep the text.
    reply_text = "".join(block.text for block in response.content if block.type == "text")
    if response.stop_reason == "max_tokens":
        print("Warning: reply was cut off (max_tokens reached).")
    usage = response.usage
    cost = (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000
    return reply_text, usage, cost


def question_to_sql(client, system_prompt, question):
    """Business question in, SQL out."""
    messages = [{"role": "user", "content": question}]
    reply_text, usage, cost = ask_claude(client, system_prompt, messages)
    return extract_sql(reply_text), usage, cost


def run_sql(conn, sql, timeout_s=SQL_TIMEOUT_S):
    """Run the SQL on the read-only database and return the result as a table.

    SQLite has no timeout setting, so a progress handler checks the clock every
    10,000 steps and aborts the query once the deadline has passed.
    """
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        return pd.read_sql(sql, conn)
    except Exception as error:
        if "interrupted" in str(error):
            # Worded for the model: this message is sent back for the one retry.
            raise TimeoutError(
                f"The query was too slow and was stopped after {timeout_s}s. "
                "Rewrite it to be efficient: join on keys, filter dates early, "
                "aggregate before joining."
            ) from error
        raise
    finally:
        conn.set_progress_handler(None, 0)


def make_client():
    """Claude client with a per-call timeout (reads ANTHROPIC_API_KEY from .env)."""
    load_dotenv(Path(__file__).resolve().parent / ".env")
    return anthropic.Anthropic(timeout=API_TIMEOUT_S, max_retries=2)


def fix_sql(client, system_prompt, question, bad_sql, error):
    """Show Claude its failed SQL and the error, and ask for a corrected query."""
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": f"```sql\n{bad_sql}\n```"},
        {"role": "user", "content": (
            f"That query failed in SQLite with this error:\n{error}\n"
            "Fix it. Reply with only the corrected SQL inside a ```sql code block."
        )},
    ]
    reply_text, usage, cost = ask_claude(client, system_prompt, messages)
    return extract_sql(reply_text), usage, cost


def answer_in_english(client, question, sql, result, max_rows=50):
    """Second LLM call: turn the result table into a short plain-English answer."""
    shown = result.head(max_rows).to_string(index=False)
    note = "" if len(result) <= max_rows else f" (first {max_rows} of {len(result)} rows)"
    content = f"Question: {question}\n\nSQL used:\n{sql}\n\nResult{note}:\n{shown}"
    reply_text, usage, cost = ask_claude(client, ANSWER_PROMPT, [{"role": "user", "content": content}])
    return reply_text.strip(), usage, cost


def ask(client, conn, system_prompt, question):
    """Full pipeline for one question: SQL, run (one retry on error), answer.

    Returns a dict, so evals/run_evals.py can reuse it.
    """
    start = time.perf_counter()
    sql, _, cost = question_to_sql(client, system_prompt, question)
    retried = False
    try:
        result = run_sql(conn, sql)
    except Exception as error:
        retried = True
        sql, _, fix_cost = fix_sql(client, system_prompt, question, sql, error)
        cost += fix_cost
        try:
            result = run_sql(conn, sql)
        except Exception as error2:
            return {"ok": False, "sql": sql, "error": str(error2), "retried": True,
                    "cost": cost, "seconds": time.perf_counter() - start}

    answer, _, answer_cost = answer_in_english(client, question, sql, result)
    cost += answer_cost
    return {"ok": True, "answer": answer, "sql": sql, "result": result, "retried": retried,
            "cost": cost, "seconds": time.perf_counter() - start}


def main():
    if len(sys.argv) < 2:
        print('Usage: python copilot.py "your question"')
        sys.exit(1)
    question = sys.argv[1]

    client = make_client()
    conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)  # read-only: AI-written SQL can't change data
    system_prompt = build_system_prompt(conn)

    out = ask(client, conn, system_prompt, question)

    print(f"\nQ: {question}\n")
    if not out["ok"]:
        print("I couldn't answer this question. Try rephrasing it.")
        print(f"(SQL still failing after one retry: {out['error']})")
    else:
        print(f"A: {out['answer']}\n")
        print("-" * 60)
        print(f"Result ({len(out['result'])} rows):")
        print(out["result"].head(20).to_string(index=False))
        print(f"\nSQL{' (corrected after an error)' if out['retried'] else ''}:\n{out['sql']}")
    print("-" * 60)
    print(f"Cost: ${out['cost']:.5f}   Time: {out['seconds']:.1f}s")


if __name__ == "__main__":
    main()