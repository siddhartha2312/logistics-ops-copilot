"""Decide whether the copilot's result matches the golden answer.

Rule (v1): for each column that IS the answer (the golden "Check:" columns),
the same values must appear in some column of the AI result.

Deliberately ignored, because they don't change the business answer:
- column names (on_time_pct vs on_time_rate)
- column order, and extra columns the AI added
- row order
- percent vs fraction (87.8 vs 0.878)
- extra rows (AI listed all 25 AMs; golden kept the top 10)

Known limits of v1 (improve in week 3):
- a wrong query could match by coincidence
- "top 10" questions accept a longer list, so ranking cut-offs aren't checked
"""

import pandas as pd


def numbers_match(a, b):
    """True if two numbers are equal, allowing for rounding differences."""
    tolerance = max(0.06, 0.002 * abs(b))  # 0.06 absolute, or 0.2% for big numbers
    return abs(a - b) <= tolerance


def numeric_column_found(golden_values, ai_values):
    """True if every golden number appears in the AI column (each used once).

    Also tries the AI column x100 and /100, to accept 0.878 vs 87.8.
    """
    for scale in (1, 100, 0.01):
        remaining = [v * scale for v in ai_values]
        all_found = True
        for g in golden_values:
            match = next((v for v in remaining if numbers_match(v, g)), None)
            if match is None:
                all_found = False
                break
            remaining.remove(match)  # each AI value can match only one golden value
        if all_found:
            return True
    return False


def text_column_found(golden_values, ai_values):
    """True if every golden text value appears in the AI column (case-insensitive)."""
    ai_set = {str(v).strip().lower() for v in ai_values}
    return all(str(g).strip().lower() in ai_set for g in golden_values)


def value_found(golden, col, ai):
    """True if golden[col]'s values appear in any AI column of the same kind."""
    golden_values = golden[col].dropna().tolist()
    is_number = pd.api.types.is_numeric_dtype(golden[col])
    for ai_col in ai.columns:
        ai_is_number = pd.api.types.is_numeric_dtype(ai[ai_col])
        ai_values = ai[ai_col].dropna().tolist()
        if is_number and ai_is_number and numeric_column_found(golden_values, ai_values):
            return True
        if not is_number and not ai_is_number and text_column_found(golden_values, ai_values):
            return True
    return False


def compare_results(golden, ai, check_columns=""):
    """Compare two result tables. Return (passed, reason).

    check_columns: e.g. "shipper_id|name, attainment_pct".
    Commas separate required answers; "|" means either column is accepted.
    Empty = check every numeric golden column.
    """
    # Case 1: golden answer is "no rows" (e.g. M4: no de-listed shipper had volume).
    if golden.empty:
        if ai.empty:
            return True, "both empty"
        numeric = [c for c in ai.columns if pd.api.types.is_numeric_dtype(ai[c])]
        values = ai[numeric].fillna(0).to_numpy().ravel()
        if len(values) > 0 and all(v == 0 for v in values):
            return True, "golden empty, AI returned zeros"
        return False, f"golden has no rows, AI returned {len(ai)} rows"

    if ai.empty:
        return False, f"AI returned no rows, golden has {len(golden)}"

    # Case 2: each required answer column must be found in the AI result.
    if check_columns:
        required = [part.strip().split("|") for part in check_columns.split(",")]
    else:
        required = [[c] for c in golden.columns if pd.api.types.is_numeric_dtype(golden[c])]

    missing = []
    for options in required:
        if not any(value_found(golden, col, ai) for col in options if col in golden.columns):
            missing.append("|".join(options))

    if missing:
        return False, "not found: " + ", ".join(missing)
    return True, "all answer columns found"