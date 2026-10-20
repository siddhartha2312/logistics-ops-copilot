"""Logistics Ops Copilot v0: turn a business question into SQL.

Usage (from the project root, with .venv active):
    python copilot.py "How many shipments were cancelled last quarter?"

Day 3: prints the SQL the model writes. It does not run it yet.
Day 4: runs the SQL and answers in plain English.
"""

import re
import sqlite3
import sys

import anthropic
from dotenv import load_dotenv

MODEL = "claude-haiku-5-5"
DB_FILE = "logistics.db"
TODAY = "2026-10-19"  # frozen reference date, see docs/data_model.md

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
    """Instructions + database facts the model needs before any question."""
    return f"""You are a SQL expert for a logistics company's SQLite database.
Write ONE SQLite query that answers the user's question.

Rules:
- Use only the tables and columns listed below. Never invent a column.
- Use only the exact category values listed below. They are case-sensitive.
- This is SQLite: use date() and strftime(). There is no DATE_TRUNC or EXTRACT.
  Dates are stored as 'YYYY-MM-DD' text; timestamps as 'YYYY-MM-DD HH:MM:SS'.
- Today's date is {TODAY}.
- Read-only: write a SELECT (or WITH ... SELECT) query only.
- Reply with only the SQL inside a ```sql code block. No explanation.

Schema:
{get_schema(conn)}

Allowed values:
{get_allowed_values(conn)}
"""


def extract_sql(text):
    """Pull the SQL out of the ```sql ... ``` block in the model's reply."""
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()  # fallback: the model replied with bare SQL


def question_to_sql(client, system_prompt, question):
    """One LLM call: business question in, SQL (plus tokens and cost) out."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,  # room for thinking + a long query
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
    )
    # The reply can hold several blocks (e.g. thinking, then text). Keep the text.
    reply_text = "".join(block.text for block in response.content if block.type == "text")
    if response.stop_reason == "max_tokens":
        print("Warning: reply was cut off (max_tokens reached). SQL may be incomplete.")

    sql = extract_sql(reply_text)
    usage = response.usage
    cost = (usage.input_tokens * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000
    return sql, usage, cost


def main():
    if len(sys.argv) < 2:
        print('Usage: python copilot.py "your question"')
        sys.exit(1)
    question = sys.argv[1]

    load_dotenv()
    client = anthropic.Anthropic()
    conn = sqlite3.connect(DB_FILE)

    system_prompt = build_system_prompt(conn)
    sql, usage, cost = question_to_sql(client, system_prompt, question)

    print(f"\nQuestion: {question}\n")
    print(f"SQL:\n{sql}\n")
    print(f"Tokens: {usage.input_tokens} in / {usage.output_tokens} out   Cost: ${cost:.5f}")


if __name__ == "__main__":
    main()