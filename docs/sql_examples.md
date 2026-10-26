# Worked SQL Examples

Correct queries for common patterns, using the semantic layer views
(`docs/semantic_layer.md`). The copilot reads these with every question.
They show HOW to use the views; they are not the answer to any evaluation question.

## Example 1: daily attainment for one shipper

Question: Show daily attainment for shipper S0100 in the week starting 6 September 2026.

```sql
SELECT day,
       forecast_packages,
       actual_packages,
       ROUND(100.0 * actual_packages / forecast_packages, 1) AS attainment_pct
FROM v_attainment_daily               -- forecast days only, actuals already joined
WHERE shipper_id = 'S0100'
  AND week_start = '2026-09-06'
ORDER BY day;
```

## Example 2: late arrivals by carrier (run-level metric)

Question: Which carrier had the most late arrivals in September 2026?

```sql
SELECT carrier,
       COUNT(is_late) AS completed_runs,          -- is_late is NULL unless completed
       SUM(is_late) AS late_runs,
       ROUND(100.0 * AVG(is_late), 1) AS late_pct
FROM v_truck_runs
WHERE run_date BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY carrier
ORDER BY late_runs DESC;
```

## Example 3: on-time rate (denominator handled by the view)

Question: What was the on-time rate by service level in August 2026?

```sql
SELECT service_level,
       COUNT(is_on_time) AS shipments,             -- non-cancelled only (NULL skipped)
       ROUND(100.0 * AVG(is_on_time), 1) AS on_time_pct
FROM v_shipments
WHERE pickup_date BETWEEN '2026-08-01' AND '2026-08-31'
GROUP BY service_level;
```