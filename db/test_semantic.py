"""Test the semantic layer: each view must reproduce known-correct golden answers.

Run from the project root:  python db/test_semantic.py
Like dbt tests: if a definition in db/semantic.sql breaks, a test fails before the
copilot (or a dashboard) uses the wrong number.
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
from compare import compare_results  # noqa: E402

DB = ROOT / "logistics.db"
GOLDEN = ROOT / "evals" / "golden_questions.csv"

# 1. Structure: views must not add or drop rows versus their source table.
ROW_TESTS = {
    "v_shipments has one row per shipment":
        "SELECT (SELECT COUNT(*) FROM v_shipments) = (SELECT COUNT(*) FROM shipments)",
    "v_truck_runs has one row per run":
        "SELECT (SELECT COUNT(*) FROM v_truck_runs) = (SELECT COUNT(*) FROM truck_runs)",
    "v_attainment_daily has one row per forecast":
        "SELECT (SELECT COUNT(*) FROM v_attainment_daily) = (SELECT COUNT(*) FROM forecasts)",
    "v_shipper_avoidable_cost has one row per stop":
        "SELECT (SELECT COUNT(*) FROM v_shipper_avoidable_cost) = (SELECT COUNT(*) FROM run_stops)",
    "cost split adds back to total run cost":
        "SELECT ABS((SELECT SUM(cost_share_eur) FROM v_shipper_avoidable_cost)"
        " - (SELECT SUM(cost_eur) FROM truck_runs WHERE run_id IN (SELECT run_id FROM run_stops))) < 0.01",
    "is_on_time is NULL exactly for cancelled shipments":
        "SELECT COUNT(*) = 0 FROM v_shipments WHERE (is_on_time IS NULL) <> (is_cancelled = 1)",
}

# 2. Definitions: the golden question answered through the views must match
#    the golden answer computed from raw tables.
GOLDEN_TESTS = {
    "E3": """SELECT 100.0 * AVG(is_customs_hold) AS customs_hold_pct
             FROM v_shipments WHERE shipper_country = 'UK'""",
    "M1": """SELECT s.run_type, 100.0 * AVG(s.is_on_time) AS on_time_pct,
                    c.cost / SUM(s.volume_packages) AS cost_per_package
             FROM v_shipments s
             JOIN (SELECT run_type, SUM(cost_eur) AS cost FROM v_truck_runs
                   WHERE run_date BETWEEN '2026-07-01' AND '2026-09-30' GROUP BY run_type) c
               ON c.run_type = s.run_type
             WHERE s.pickup_date BETWEEN '2026-07-01' AND '2026-09-30'
             GROUP BY s.run_type""",
    "M2": """SELECT week_start, 100.0 * SUM(actual_packages) / SUM(forecast_packages) AS attainment_pct
             FROM v_attainment_daily
             WHERE shipper_country = 'FR' AND week_start BETWEEN '2026-07-01' AND '2026-09-30'
             GROUP BY week_start""",
    "M3": """SELECT shipper_id, 100.0 * SUM(actual_packages) / SUM(forecast_packages) AS attainment_pct
             FROM v_attainment_daily WHERE day BETWEEN '2026-07-01' AND '2026-09-30'
             GROUP BY shipper_id HAVING SUM(forecast_packages) >= 500
             ORDER BY attainment_pct LIMIT 10""",
    "M5": """SELECT node_country AS country, 100.0 * SUM(pallets_loaded) / SUM(pallet_capacity) AS utilisation_pct
             FROM v_truck_runs WHERE run_date BETWEEN '2026-09-01' AND '2026-09-30'
             GROUP BY node_country""",
    "H1": """SELECT node_id, COUNT(*) AS days_over_capacity FROM (
               SELECT r.node_id, r.run_date, SUM(r.pallets_loaded) AS load
               FROM v_truck_runs r WHERE r.run_date BETWEEN '2025-11-28' AND '2025-12-24'
               GROUP BY r.node_id, r.run_date) d
             JOIN nodes n USING (node_id)
             WHERE d.load > n.daily_capacity_pallets GROUP BY node_id""",
    "H2": """SELECT account_manager, SUM(avoidable_cost_share_eur) AS avoidable_cost_eur
             FROM v_shipper_avoidable_cost WHERE run_date BETWEEN '2026-07-01' AND '2026-09-30'
             GROUP BY account_manager ORDER BY avoidable_cost_eur DESC""",
}


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    golden = pd.read_csv(GOLDEN, keep_default_na=False).set_index("id")
    failures = 0

    print("Structure")
    for name, sql in ROW_TESTS.items():
        ok = bool(conn.execute(sql).fetchone()[0])
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    print("\nDefinitions (view answer vs golden answer)")
    for qid, sql in GOLDEN_TESTS.items():
        start = time.perf_counter()
        view_result = pd.read_sql(sql, conn)
        seconds = time.perf_counter() - start
        gold = pd.DataFrame(json.loads(golden.loc[qid, "answer_json"]))
        ok, reason = compare_results(gold, view_result, golden.loc[qid, "check_columns"])
        failures += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {qid}  {seconds:4.1f}s  {reason}")

    print(f"\n{'All tests passed' if not failures else f'{failures} test(s) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()