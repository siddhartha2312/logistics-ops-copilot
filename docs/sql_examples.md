# Worked SQL Examples

Correct queries for common patterns. The copilot reads these with every question.
They show HOW to apply the business definitions; they are not the answer to any
evaluation question.

## Example 1: daily attainment for one shipper (forecast-driven join)

Question: Show daily attainment for shipper S0100 in the week starting 6 September 2026.

```sql
WITH daily_actual AS (
    -- aggregate actual volume to shipper x pickup day BEFORE joining (no fan-out)
    SELECT s.shipper_id, tr.run_date AS pickup_date, SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, tr.run_date
)
SELECT f.forecast_date,
       f.forecast_packages,
       COALESCE(a.actual_packages, 0) AS actual_packages,
       ROUND(100.0 * COALESCE(a.actual_packages, 0) / f.forecast_packages, 1) AS attainment_pct
FROM forecasts f                      -- start from the forecast side
LEFT JOIN daily_actual a
  ON a.shipper_id = f.shipper_id AND a.pickup_date = f.forecast_date
WHERE f.shipper_id = 'S0100'
  AND f.forecast_date BETWEEN '2026-09-06' AND '2026-09-12'
ORDER BY f.forecast_date;
```

## Example 2: late arrivals by carrier (run-level metric, no exceptions join)

Question: Which carrier had the most late arrivals in September 2026?

```sql
SELECT carrier,
       COUNT(*) AS completed_runs,
       SUM(CASE WHEN actual_arrival_time > planned_arrival_time THEN 1 ELSE 0 END) AS late_runs,
       ROUND(100.0 * SUM(CASE WHEN actual_arrival_time > planned_arrival_time THEN 1 ELSE 0 END)
             / COUNT(*), 1) AS late_pct
FROM truck_runs
WHERE run_outcome = 'completed'
  AND actual_arrival_time IS NOT NULL
  AND run_date BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY carrier
ORDER BY late_runs DESC;
```

## Example 3: on-time rate (denominator = all non-cancelled shipments)

Question: What was the on-time rate by service level in August 2026?

```sql
SELECT s.service_level,
       COUNT(*) AS shipments,
       ROUND(100.0 * SUM(CASE WHEN s.delivered_to_node_date IS NOT NULL
                               AND s.delivered_to_node_date <= s.promised_date
                              THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct
FROM shipments s
JOIN truck_runs tr ON tr.run_id = s.run_id      -- period is decided by pickup date
WHERE s.status <> 'Cancelled'
  AND tr.run_date BETWEEN '2026-08-01' AND '2026-08-31'
GROUP BY s.service_level;
```