"""Logistics Ops Copilot: turn a business question into SQL and a plain-English answer.

Usage (from the project root, with .venv active):
    python copilot.py "How many shipments were cancelled last quarter?"

Flow: question -> SQL or "cannot answer" + assumptions (Claude, JSON)
      -> run on a read-only database -> one retry if the SQL fails
      -> plain-English answer (Claude).
Context sent with every question: schema, allowed values, docs/glossary.md,
docs/sql_examples.md.
"""

import json
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
MAX_ROWS = 10_000    # never load more rows than this into memory or the answer
PRINT_ROWS = 20      # rows printed in the terminal; the full result goes to a CSV
RESULT_FILE = "last_result.csv"
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
- If you only see part of the result, give the total number of rows and say the full
  list is in the table. Never write "only the first N are shown". Describe only what is
  certain from the rows you see (e.g. the top rows of a sorted list); don't generalise
  from them to all rows.
- The assumptions are shown to the reader separately: don't repeat them.
- Do not mention SQL, tables or column names.
"""


def get_schema(conn):
    """List every table with its columns and types."""
    lines = []
    tables = conn.execute(
        # sqlite_% = SQLite's own tables (e.g. sqlite_stat1 from ANALYZE), not business data
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
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

When the data cannot answer the question:
- If the question needs data that is not in the schema (e.g. a measure, attribute or
  status no table holds), do NOT answer with a different measure as a substitute.
  Set "sql" to null and say in "cannot_answer" which data is missing.
- Never refuse a question the schema can answer. Missing words in the glossary are
  not missing data: interpret them and list the interpretation in "assumptions".

Assumptions:
- List every interpretation you made that the business definitions do not settle
  (e.g. which dates a vague period covers, what threshold "high" or "large" means).
  Each one short and concrete, with the dates or thresholds you used.
- Empty list if the definitions settled everything.

Reply with only this JSON object, no other text. Format the SQL readably, with a
line break (\\n) before each clause (FROM, JOIN, WHERE, GROUP BY, ...):
{{"sql": "<SQLite query, or null>", "cannot_answer": "<what data is missing, or null>", "assumptions": ["<interpretation>", ...]}}

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


def parse_reply(text):
    """Read the model's JSON reply: {"sql", "cannot_answer", "assumptions"}.

    Falls back to treating the reply as SQL if it isn't valid JSON, so a format
    slip becomes a SQL error (and the one retry) rather than a crash.
    """
    start, end = text.find("{"), text.rfind("}")
    try:
        reply = json.loads(text[start:end + 1], strict=False)  # allow newlines in the SQL
    except (ValueError, TypeError):
        return {"sql": extract_sql(text), "cannot_answer": None, "assumptions": []}
    return {
        "sql": (reply.get("sql") or "").strip() or None,
        "cannot_answer": reply.get("cannot_answer") or None,
        "assumptions": [a for a in (reply.get("assumptions") or []) if a],
    }


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
    """Business question in; SQL or "cannot answer", plus assumptions, out."""
    messages = [{"role": "user", "content": question}]
    reply_text, usage, cost = ask_claude(client, system_prompt, messages)
    return parse_reply(reply_text), usage, cost


# Statements that change data or the database. Checked as whole words, outside strings.
BLOCKED_KEYWORDS = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX)\b"


def check_select_only(sql):
    """Raise ValueError unless the SQL is a single read-only SELECT (or WITH ... SELECT).

    A second layer behind the read-only connection: blocked SQL never reaches the database.
    """
    # One pass, left to right, so an apostrophe in a comment or "--" in a string
    # can't confuse it: quoted text becomes '' and comments become a space.
    token = r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/"
    body = re.sub(token, lambda m: "''" if m.group(0).startswith("'") else " ", sql, flags=re.DOTALL)
    body = body.strip().rstrip(";").strip()
    if ";" in body:
        raise ValueError("Blocked: only one SQL statement is allowed.")
    if not re.match(r"(?i)(SELECT|WITH)\b", body):
        raise ValueError("Blocked: only SELECT queries are allowed.")
    found = re.search(BLOCKED_KEYWORDS, body, flags=re.IGNORECASE)
    if found:
        raise ValueError(f"Blocked: {found.group(1).upper()} is not allowed in a read-only query.")


def run_sql(conn, sql, timeout_s=SQL_TIMEOUT_S, max_rows=MAX_ROWS):
    """Run the SQL on the read-only database and return the result as a table.

    SQLite has no timeout setting, so a progress handler checks the clock every
    10,000 steps and aborts the query once the deadline has passed.
    At most max_rows rows are loaded; result.attrs["truncated"] says if more existed.
    """
    check_select_only(sql)
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(max_rows + 1)  # one extra row tells us if there were more
        columns = [d[0] for d in cursor.description]
        result = pd.DataFrame.from_records(rows[:max_rows], columns=columns)
        result.attrs["truncated"] = len(rows) > max_rows
        return result
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


def answer_in_english(client, question, sql, result, assumptions=(), max_rows=50):
    """Second LLM call: turn the result table into a short plain-English answer."""
    shown = result.head(max_rows).to_string(index=False)
    total = f"{len(result)}+" if result.attrs.get("truncated") else str(len(result))
    note = "" if len(result) <= max_rows else f" (you see {max_rows} of {total} rows)"
    assumed = "\n".join(f"- {a}" for a in assumptions) or "(none)"
    content = (f"Question: {question}\n\nAssumptions made:\n{assumed}\n\n"
               f"SQL used:\n{sql}\n\nResult{note}:\n{shown}")
    reply_text, usage, cost = ask_claude(client, ANSWER_PROMPT, [{"role": "user", "content": content}])
    return reply_text.strip(), usage, cost


def ask(client, conn, system_prompt, question):
    """Full pipeline for one question: SQL, run (one retry on error), answer.

    Returns a dict, so evals/run_evals.py can reuse it.
    """
    start = time.perf_counter()
    reply, _, cost = question_to_sql(client, system_prompt, question)
    sql, assumptions = reply["sql"], reply["assumptions"]

    # The model says the data can't answer this: stop here, no SQL is run.
    if reply["cannot_answer"] or not sql:
        reason = reply["cannot_answer"] or "No query was produced."
        return {"ok": False, "cannot_answer": True, "error": reason, "sql": "",
                "assumptions": assumptions, "retried": False,
                "cost": cost, "seconds": time.perf_counter() - start}

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
            return {"ok": False, "cannot_answer": False, "sql": sql, "error": str(error2),
                    "assumptions": assumptions, "retried": True,
                    "cost": cost, "seconds": time.perf_counter() - start}

    answer, _, answer_cost = answer_in_english(client, question, sql, result, assumptions)
    cost += answer_cost
    return {"ok": True, "cannot_answer": False, "answer": answer, "sql": sql, "result": result,
            "assumptions": assumptions, "retried": retried,
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
    if out["cannot_answer"]:
        print(f"I can't answer this from the available data. {out['error']}")
    elif not out["ok"]:
        print("I couldn't answer this question. Try rephrasing it.")
        print(f"(SQL still failing after one retry: {out['error']})")
    else:
        print(f"A: {out['answer']}\n")
        if out["assumptions"]:
            print("Assumptions:")
            for a in out["assumptions"]:
                print(f"  - {a}")
            print()
        print("-" * 60)
        result = out["result"]
        cut = " (row limit reached, more rows exist)" if result.attrs.get("truncated") else ""
        print(f"Result ({len(result)} rows{cut}):")
        print(result.head(PRINT_ROWS).to_string(index=False))
        if len(result) > PRINT_ROWS:
            result.to_csv(RESULT_FILE, index=False)
            print(f"... {len(result) - PRINT_ROWS} more rows. Full result saved to {RESULT_FILE}")
        print(f"\nSQL{' (corrected after an error)' if out['retried'] else ''}:\n{out['sql']}")
    print("-" * 60)
    print(f"Cost: ${out['cost']:.5f}   Time: {out['seconds']:.1f}s")


if __name__ == "__main__":
    main()