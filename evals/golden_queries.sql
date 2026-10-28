-- =====================================================================
-- Golden queries: Logistics Ops Copilot
-- Ground-truth SQL for the dev questions (15 original + 5 added on 2026-10-26).
-- Written against docs/data_model.md (daily forecasts, account_manager,
-- is_adhoc, run_outcome, per-stop pickup times on run_stops).
--
-- Frozen reference date: "today" = 2026-10-19
--   Last quarter (LQ) = 2026-07-01 .. 2026-09-30
--   Last month        = 2026-09-01 .. 2026-09-30
-- Weeks run Sunday-Saturday (week_start = the Sunday).
--
-- "Check:" lists the columns that ARE the answer. The eval compares only those.
-- "a|b" means either column is accepted (e.g. shipper_id or name).
-- Actual volume = packages picked up on truck_runs.run_date, excluding
-- Cancelled shipments. Attainment only on days that have a forecast.
-- =====================================================================


-- ---------------------------------------------------------------------
-- E1. How many shipments were cancelled last quarter?
-- Assumption: "last quarter" applied to created_date.
-- Check: cancelled_shipments
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS cancelled_shipments
FROM shipments
WHERE status = 'Cancelled'
  AND date(created_date) BETWEEN '2026-07-01' AND '2026-09-30';


-- ---------------------------------------------------------------------
-- E2. How many active shippers do we have per country?
-- Check: active_shippers
-- ---------------------------------------------------------------------
SELECT country, COUNT(*) AS active_shippers
FROM shippers
WHERE status = 'active'
GROUP BY country
ORDER BY active_shippers DESC;


-- ---------------------------------------------------------------------
-- E3. What % of UK shipments were held at customs?
-- Assumption: all time; country = shipper's country; denominator =
-- non-cancelled shipments (changed 2026-10-22, see evals/golden_changes.md).
-- Expected (scenario 1): ~8.5%.
-- Check: customs_hold_pct
-- ---------------------------------------------------------------------
SELECT
    COUNT(*) AS uk_shipments,
    SUM(CASE WHEN s.hold_reason = 'At Customs' THEN 1 ELSE 0 END) AS customs_holds,
    ROUND(100.0 * SUM(CASE WHEN s.hold_reason = 'At Customs' THEN 1 ELSE 0 END)
          / COUNT(*), 2) AS customs_hold_pct
FROM shipments s
JOIN shippers sh ON sh.shipper_id = s.shipper_id
WHERE sh.country = 'UK'
  AND s.status <> 'Cancelled';


-- ---------------------------------------------------------------------
-- E4. How many truck runs were ad-hoc in September 2026?
-- Check: adhoc_runs
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS adhoc_runs
FROM truck_runs
WHERE is_adhoc = 1
  AND date(run_date) BETWEEN '2026-09-01' AND '2026-09-30';


-- ---------------------------------------------------------------------
-- E5. Which node has the highest daily pallet capacity?
-- Check: node_id|city, daily_capacity_pallets
-- ---------------------------------------------------------------------
SELECT node_id, node_type, city, country, daily_capacity_pallets
FROM nodes
ORDER BY daily_capacity_pallets DESC
LIMIT 1;


-- ---------------------------------------------------------------------
-- M1. Compare on-time rate and cost per package for milkrun vs direct,
--     last quarter.
-- Assumptions: LQ applied to run_date; on-time excludes Cancelled and
-- counts undelivered as not on-time; cost per package includes the cost
-- of wasted runs (true cost of the network).
-- Expected (scenario 2): milkrun lower on-time AND lower cost/package.
-- Check: on_time_pct, cost_per_package_eur
-- ---------------------------------------------------------------------
WITH lq_runs AS (
    SELECT run_id, run_type, cost_eur
    FROM truck_runs
    WHERE date(run_date) BETWEEN '2026-07-01' AND '2026-09-30'
),
ship AS (
    SELECT r.run_type,
           COUNT(*) AS shipments,
           SUM(s.packages) AS packages,
           AVG(CASE WHEN s.delivered_to_node_date IS NOT NULL
                     AND date(s.delivered_to_node_date) <= date(s.promised_date)
                    THEN 1.0 ELSE 0 END) AS on_time_rate
    FROM shipments s
    JOIN lq_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY r.run_type
),
cost AS (
    SELECT run_type, COUNT(*) AS runs, SUM(cost_eur) AS total_cost
    FROM lq_runs
    GROUP BY run_type
)
SELECT c.run_type, c.runs, sp.shipments, sp.packages,
       ROUND(100.0 * sp.on_time_rate, 1)        AS on_time_pct,
       ROUND(c.total_cost, 0)                   AS total_cost_eur,
       ROUND(c.total_cost / sp.packages, 3)     AS cost_per_package_eur
FROM cost c
JOIN ship sp ON sp.run_type = c.run_type;


-- ---------------------------------------------------------------------
-- M2. What was our weekly attainment for FR shippers last quarter?
-- Assumptions: weeks Sun-Sat; only weeks whose Sunday falls in LQ;
-- unplanned volume (days with no forecast) excluded.
-- Check: attainment_pct
-- ---------------------------------------------------------------------
WITH daily_actuals AS (
    SELECT s.shipper_id, date(tr.run_date) AS pickup_date,
           SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, date(tr.run_date)
),
daily AS (
    SELECT f.shipper_id, date(f.forecast_date) AS d,
           f.forecast_packages,
           COALESCE(a.actual_packages, 0) AS actual_packages
    FROM forecasts f
    LEFT JOIN daily_actuals a
      ON a.shipper_id = f.shipper_id AND a.pickup_date = date(f.forecast_date)
)
SELECT date(d.d, '-' || strftime('%w', d.d) || ' days') AS week_start,
       SUM(d.forecast_packages) AS forecast_packages,
       SUM(d.actual_packages)   AS actual_packages,
       ROUND(100.0 * SUM(d.actual_packages) / SUM(d.forecast_packages), 1) AS attainment_pct
FROM daily d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
WHERE sh.country = 'FR'
GROUP BY week_start
HAVING week_start BETWEEN '2026-07-01' AND '2026-09-30'
ORDER BY week_start;


-- ---------------------------------------------------------------------
-- M3. Which 10 shippers had the lowest attainment in Q3 2026?
-- Assumptions: quarter-level attainment = sum actual / sum forecast;
-- min 500 forecast packages in the quarter to remove noise.
-- Expected (scenario 4): planted over-forecasters near ~70%.
-- Check: shipper_id|name, attainment_pct
-- ---------------------------------------------------------------------
WITH daily_actuals AS (
    SELECT s.shipper_id, date(tr.run_date) AS pickup_date,
           SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, date(tr.run_date)
),
daily AS (
    SELECT f.shipper_id, f.forecast_packages,
           COALESCE(a.actual_packages, 0) AS actual_packages
    FROM forecasts f
    LEFT JOIN daily_actuals a
      ON a.shipper_id = f.shipper_id AND a.pickup_date = date(f.forecast_date)
    WHERE date(f.forecast_date) BETWEEN '2026-07-01' AND '2026-09-30'
)
SELECT sh.shipper_id, sh.name, sh.country, sh.account_manager,
       SUM(d.forecast_packages) AS forecast_packages,
       SUM(d.actual_packages)   AS actual_packages,
       ROUND(100.0 * SUM(d.actual_packages) / SUM(d.forecast_packages), 1) AS attainment_pct
FROM daily d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
GROUP BY sh.shipper_id
HAVING SUM(d.forecast_packages) >= 500
ORDER BY attainment_pct ASC
LIMIT 10;


-- ---------------------------------------------------------------------
-- M4. Did any de-listed shipper have volume after being de-listed?
-- Expected (scenario 8): zero rows.
-- Check: (expect no rows)
-- ---------------------------------------------------------------------
SELECT sh.shipper_id, sh.name, sh.delisted_date,
       COUNT(s.shipment_id) AS shipments_after,
       SUM(s.packages)      AS packages_after
FROM shippers sh
JOIN shipments s   ON s.shipper_id = sh.shipper_id
JOIN truck_runs tr ON tr.run_id = s.run_id
WHERE sh.status = 'de-listed'
  AND date(tr.run_date) > date(sh.delisted_date)
GROUP BY sh.shipper_id
ORDER BY shipments_after DESC;


-- ---------------------------------------------------------------------
-- M5. What was average truck utilisation by country last month?
-- Assumptions: country = destination node's country; weighted
-- utilisation (sum loaded / sum capacity); wasted runs included (0 loaded).
-- Check: utilisation_pct
-- ---------------------------------------------------------------------
SELECT n.country,
       COUNT(*) AS runs,
       ROUND(100.0 * SUM(tr.pallets_loaded) / SUM(tr.pallet_capacity), 1) AS utilisation_pct
FROM truck_runs tr
JOIN nodes n ON n.node_id = tr.node_id
WHERE date(tr.run_date) BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY n.country
ORDER BY utilisation_pct DESC;


-- ---------------------------------------------------------------------
-- H1. Which nodes went over capacity during peak 2025, and on how many days?
-- Assumptions: peak = 2025-11-28 (Black Friday) .. 2025-12-24;
-- pallets received per node per run_date (arrival assumed same day).
-- Expected (scenario 3): one node clearly over capacity.
-- Check: node_id|city, days_over_capacity
-- ---------------------------------------------------------------------
WITH daily_pallets AS (
    SELECT node_id, date(run_date) AS d, SUM(pallets_loaded) AS pallets
    FROM truck_runs
    WHERE date(run_date) BETWEEN '2025-11-28' AND '2025-12-24'
    GROUP BY node_id, date(run_date)
)
SELECT n.node_id, n.city, n.country, n.daily_capacity_pallets,
       COUNT(*)                                  AS days_over_capacity,
       MAX(dp.pallets - n.daily_capacity_pallets) AS max_pallets_over
FROM daily_pallets dp
JOIN nodes n ON n.node_id = dp.node_id
WHERE dp.pallets > n.daily_capacity_pallets
GROUP BY n.node_id
ORDER BY days_over_capacity DESC;


-- ---------------------------------------------------------------------
-- H2. Which Account Managers' shippers drove the most avoidable cost
--     last quarter?
-- Avoidable cost = ad-hoc premium + wasted truck cost.
--   Ad-hoc premium = cost_eur - cost_eur / 1.6  (= 0.375 x cost_eur)
--   Wasted cost    = full cost_eur
-- Multi-stop runs: cost split equally across stops.
-- Expected (scenario 11): ~3 AMs dominate wasted cost.
-- Check: account_manager, avoidable_cost_eur
-- ---------------------------------------------------------------------
WITH lq_runs AS (
    SELECT run_id, cost_eur, is_adhoc, run_outcome
    FROM truck_runs
    WHERE date(run_date) BETWEEN '2026-07-01' AND '2026-09-30'
      AND (is_adhoc = 1 OR run_outcome = 'wasted')
),
stops AS (
    SELECT run_id, shipper_id,
           1.0 / COUNT(*) OVER (PARTITION BY run_id) AS share
    FROM run_stops
),
by_shipper AS (
    SELECT st.shipper_id,
           SUM(st.share * CASE WHEN r.run_outcome = 'wasted'
                               THEN r.cost_eur ELSE 0 END) AS wasted_cost,
           SUM(st.share * CASE WHEN r.is_adhoc = 1 AND r.run_outcome <> 'wasted'
                               THEN r.cost_eur * 0.6 / 1.6 ELSE 0 END) AS adhoc_premium
    FROM lq_runs r
    JOIN stops st ON st.run_id = r.run_id
    GROUP BY st.shipper_id
)
SELECT sh.account_manager,
       COUNT(DISTINCT sh.shipper_id)                        AS shippers_involved,
       ROUND(SUM(b.wasted_cost), 0)                         AS wasted_cost_eur,
       ROUND(SUM(b.adhoc_premium), 0)                       AS adhoc_premium_eur,
       ROUND(SUM(b.wasted_cost + b.adhoc_premium), 0)       AS avoidable_cost_eur
FROM by_shipper b
JOIN shippers sh ON sh.shipper_id = b.shipper_id
GROUP BY sh.account_manager
ORDER BY avoidable_cost_eur DESC
LIMIT 10;


-- ---------------------------------------------------------------------
-- H3. How much unplanned volume did we get on bank holidays in 2026,
--     by country?
-- Unplanned = picked-up packages on a day with no forecast row.
-- Expected (scenario 9): non-zero in each country.
-- Check: country, unplanned_packages
-- ---------------------------------------------------------------------
WITH daily_actuals AS (
    SELECT s.shipper_id, date(tr.run_date) AS pickup_date,
           SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, date(tr.run_date)
)
SELECT sh.country,
       COUNT(DISTINCT h.holiday_date)    AS holidays_with_volume,
       COUNT(DISTINCT da.shipper_id)     AS shippers,
       SUM(da.actual_packages)           AS unplanned_packages
FROM daily_actuals da
JOIN shippers sh ON sh.shipper_id = da.shipper_id
JOIN holidays h  ON h.country = sh.country
                AND date(h.holiday_date) = da.pickup_date
LEFT JOIN forecasts f ON f.shipper_id = da.shipper_id
                     AND date(f.forecast_date) = da.pickup_date
WHERE f.shipper_id IS NULL
  AND da.pickup_date BETWEEN '2026-01-01' AND '2026-12-31'
GROUP BY sh.country
ORDER BY unplanned_packages DESC;


-- ---------------------------------------------------------------------
-- H4. Which shippers missed the +/-10% attainment band for 3+
--     consecutive weeks?
-- Assumptions: all time; weeks Sun-Sat; "consecutive" = consecutive
-- forecast weeks for that shipper; min 50 forecast packages per week.
-- Technique: gaps-and-islands with two ROW_NUMBERs.
-- Check: shipper_id|name
-- ---------------------------------------------------------------------
WITH daily_actuals AS (
    SELECT s.shipper_id, date(tr.run_date) AS pickup_date,
           SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, date(tr.run_date)
),
weekly AS (
    SELECT f.shipper_id,
           date(f.forecast_date, '-' || strftime('%w', f.forecast_date) || ' days') AS week_start,
           SUM(f.forecast_packages) AS fc,
           SUM(COALESCE(a.actual_packages, 0)) AS act
    FROM forecasts f
    LEFT JOIN daily_actuals a
      ON a.shipper_id = f.shipper_id AND a.pickup_date = date(f.forecast_date)
    GROUP BY f.shipper_id, week_start
    HAVING SUM(f.forecast_packages) >= 50
),
flagged AS (
    SELECT shipper_id, week_start,
           CASE WHEN 1.0 * act / fc < 0.9 OR 1.0 * act / fc > 1.1
                THEN 1 ELSE 0 END AS miss
    FROM weekly
),
islands AS (
    SELECT shipper_id, week_start, miss,
           ROW_NUMBER() OVER (PARTITION BY shipper_id ORDER BY week_start)
         - ROW_NUMBER() OVER (PARTITION BY shipper_id, miss ORDER BY week_start) AS grp
    FROM flagged
),
streaks AS (
    SELECT shipper_id, grp,
           COUNT(*)        AS weeks_in_streak,
           MIN(week_start) AS streak_start,
           MAX(week_start) AS streak_end
    FROM islands
    WHERE miss = 1
    GROUP BY shipper_id, grp
    HAVING COUNT(*) >= 3
)
SELECT sh.shipper_id, sh.name, sh.account_manager,
       COUNT(*)                 AS streaks,
       MAX(st.weeks_in_streak)  AS longest_streak_weeks,
       MAX(st.streak_end)       AS latest_streak_end
FROM streaks st
JOIN shippers sh ON sh.shipper_id = st.shipper_id
GROUP BY sh.shipper_id
ORDER BY longest_streak_weeks DESC;


-- ---------------------------------------------------------------------
-- H5. For milkruns, which shippers are most often the cause of late
--     node arrivals?
-- Rule: a late milkrun is blamed on the stop that ADDED the most delay.
--   Delay added at a stop = its lateness (actual - planned pickup)
--   minus the lateness it inherited from the previous stop (LAG).
--   Using raw lateness would wrongly blame later stops for delay that
--   an earlier stop caused.
-- Late = actual_arrival_time > planned_arrival_time.
-- Expected: a small group of 'slow loader' shippers dominates.
-- Check: shipper_id|name
-- ---------------------------------------------------------------------
WITH milkruns AS (
    SELECT run_id,
           CASE WHEN actual_arrival_time > planned_arrival_time THEN 1 ELSE 0 END AS is_late
    FROM truck_runs
    WHERE run_type = 'milkrun'
      AND run_outcome = 'completed'
      AND actual_arrival_time IS NOT NULL
),
stop_lateness AS (
    SELECT rs.run_id, rs.shipper_id, rs.stop_sequence,
           (julianday(rs.actual_pickup_time) - julianday(rs.planned_pickup_time)) * 1440 AS late_min
    FROM run_stops rs
    JOIN milkruns m ON m.run_id = rs.run_id
),
stop_added AS (
    SELECT run_id, shipper_id,
           late_min - COALESCE(LAG(late_min) OVER (PARTITION BY run_id ORDER BY stop_sequence), 0)
               AS added_delay_min
    FROM stop_lateness
),
blamed AS (
    SELECT sa.run_id, sa.shipper_id, sa.added_delay_min,
           ROW_NUMBER() OVER (PARTITION BY sa.run_id ORDER BY sa.added_delay_min DESC) AS rn
    FROM stop_added sa
    JOIN milkruns m ON m.run_id = sa.run_id
    WHERE m.is_late = 1
),
exposure AS (
    SELECT rs.shipper_id, COUNT(*) AS milkruns
    FROM run_stops rs
    JOIN milkruns m ON m.run_id = rs.run_id
    GROUP BY rs.shipper_id
)
SELECT sh.shipper_id, sh.name, sh.country,
       e.milkruns,
       COUNT(*)                                    AS late_runs_blamed,
       ROUND(100.0 * COUNT(*) / e.milkruns, 1)     AS blame_rate_pct,
       ROUND(AVG(b.added_delay_min), 0)            AS avg_added_delay_min
FROM blamed b
JOIN exposure e  ON e.shipper_id = b.shipper_id
JOIN shippers sh ON sh.shipper_id = b.shipper_id
WHERE b.rn = 1
GROUP BY sh.shipper_id
HAVING e.milkruns >= 20
ORDER BY late_runs_blamed DESC
LIMIT 10;


-- ---------------------------------------------------------------------
-- M6. List of shippers whose weekly volume stayed constant (within ±5%) in week 20 compared to last year.
-- Moved from held-out T1 on 2026-10-26: week numbering now in the glossary.
-- Definition: week 20 2026 = 17-23 May 2026 vs week 20 2025 = 18-24 May 2025.
--   Only shippers with volume in both weeks. Constant = |2026/2025 - 1| <= 5%.
-- Check: shipper_id|name
-- ---------------------------------------------------------------------
WITH weekly AS (
    SELECT s.shipper_id,
           SUM(CASE WHEN r.run_date BETWEEN '2026-05-17' AND '2026-05-23' THEN s.packages END) AS vol_2026,
           SUM(CASE WHEN r.run_date BETWEEN '2025-05-18' AND '2025-05-24' THEN s.packages END) AS vol_2025
    FROM shipments s
    JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id
)
SELECT w.shipper_id, sh.name, w.vol_2025, w.vol_2026,
       ROUND(100.0 * (1.0 * w.vol_2026 / w.vol_2025 - 1), 2) AS change_pct
FROM weekly w
JOIN shippers sh ON sh.shipper_id = w.shipper_id
WHERE w.vol_2025 > 0 AND w.vol_2026 > 0
  AND ABS(1.0 * w.vol_2026 / w.vol_2025 - 1) <= 0.05
ORDER BY w.shipper_id;


-- ---------------------------------------------------------------------
-- M7. List of nodes which were closed in Italy but open in Spain in July 2025.
-- Moved from held-out T4 on 2026-10-26: node closures now in the glossary.
-- Closed = bank holiday with no truck arriving, or Sunday at a Mon-Sat node.
-- Italy has no bank holiday in July 2025, so only its Mon-Sat nodes on Sundays
-- (Spanish 7-day nodes are open those Sundays).
-- Check: node_id
-- ---------------------------------------------------------------------
WITH july AS (
    SELECT DISTINCT run_date AS day FROM truck_runs
    WHERE run_date BETWEEN '2025-07-01' AND '2025-07-31'
),
it_closed AS (
    SELECT n.node_id, n.city, d.day
    FROM nodes n CROSS JOIN july d
    WHERE n.country = 'IT'
      AND (   (n.operating_days = 'Mon-Sat' AND strftime('%w', d.day) = '0')
           OR (EXISTS (SELECT 1 FROM holidays h WHERE h.country = 'IT' AND h.holiday_date = d.day)
               AND NOT EXISTS (SELECT 1 FROM truck_runs r WHERE r.node_id = n.node_id AND r.run_date = d.day)))
),
es_open_days AS (
    SELECT d.day
    FROM july d
    WHERE EXISTS (SELECT 1 FROM nodes e
                  WHERE e.country = 'ES'
                    AND NOT (e.operating_days = 'Mon-Sat' AND strftime('%w', d.day) = '0')
                    AND NOT (EXISTS (SELECT 1 FROM holidays h WHERE h.country = 'ES' AND h.holiday_date = d.day)
                             AND NOT EXISTS (SELECT 1 FROM truck_runs r WHERE r.node_id = e.node_id AND r.run_date = d.day)))
)
SELECT c.node_id, c.city, COUNT(*) AS days_closed
FROM it_closed c
JOIN es_open_days o ON o.day = c.day
GROUP BY c.node_id, c.city
ORDER BY c.node_id;


-- ---------------------------------------------------------------------
-- M8. Truck wastage: which country had the most wasted trucks in week 30 of 2026?
-- Moved from held-out T5 on 2026-10-26: week numbering now in the glossary.
-- Definition: wasted = truck sent, shipper loaded nothing (run_outcome = 'wasted').
--   Week 30 2026 = 26 Jul - 1 Aug 2026. Country of the destination node.
--   Counting trucks or their pallet capacity gives the same winner.
-- Check: country, wasted_trucks
-- ---------------------------------------------------------------------
SELECT n.country,
       COUNT(*) AS wasted_trucks,
       SUM(r.pallet_capacity) AS wasted_pallet_capacity
FROM truck_runs r
JOIN nodes n ON n.node_id = r.node_id
WHERE r.run_outcome = 'wasted'
  AND r.run_date BETWEEN '2026-07-26' AND '2026-08-01'
GROUP BY n.country
ORDER BY wasted_trucks DESC
LIMIT 1;


-- ---------------------------------------------------------------------
-- M9. For any day in 2026, list date, shipper name, country, actual, forecast and gap, where the gap between actual and forecast is more than 200 packages.
-- Moved from held-out T8 on 2026-10-26: forecast-vs-actual gap now in the glossary.
-- Definition: gap = actual - forecast (negative = under forecast); filter |gap| > 200. Any day with a forecast
--   or actual volume counts (missing side = 0). Data ends 2026-09-30.
-- Check: gap
-- ---------------------------------------------------------------------
WITH actual AS (
    SELECT s.shipper_id, r.run_date AS day, SUM(s.packages) AS actual
    FROM shipments s
    JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled' AND r.run_date >= '2026-01-01'
    GROUP BY s.shipper_id, r.run_date
),
forecast AS (
    SELECT shipper_id, forecast_date AS day, forecast_packages AS forecast
    FROM forecasts
    WHERE forecast_date >= '2026-01-01'
),
days AS (
    SELECT shipper_id, day FROM actual
    UNION
    SELECT shipper_id, day FROM forecast
)
SELECT d.day, sh.name, sh.country,
       COALESCE(a.actual, 0) AS actual,
       COALESCE(f.forecast, 0) AS forecast,
       COALESCE(a.actual, 0) - COALESCE(f.forecast, 0) AS gap
FROM days d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
LEFT JOIN actual a ON a.shipper_id = d.shipper_id AND a.day = d.day
LEFT JOIN forecast f ON f.shipper_id = d.shipper_id AND f.day = d.day
WHERE ABS(COALESCE(a.actual, 0) - COALESCE(f.forecast, 0)) > 200
ORDER BY d.day, sh.name;


-- ---------------------------------------------------------------------
-- M10. Which nodes were closed in Italy but open in Spain on 2 June 2026?
-- Closed = bank holiday in the node's country with no truck arriving, or Sunday at a
-- Mon-Sat node. 2 June 2026 is an IT holiday (Festa della Repubblica), not in ES.
-- Check: node_id
-- ---------------------------------------------------------------------
SELECT n.node_id, n.city
FROM nodes n
JOIN holidays h ON h.country = n.country AND h.holiday_date = '2026-06-02'
WHERE n.country = 'IT'
  AND NOT EXISTS (SELECT 1 FROM truck_runs r
                  WHERE r.node_id = n.node_id AND r.run_date = '2026-06-02')
  AND EXISTS (SELECT 1 FROM nodes e
              WHERE e.country = 'ES'
                AND NOT EXISTS (SELECT 1 FROM holidays x
                                WHERE x.country = 'ES' AND x.holiday_date = '2026-06-02'))
ORDER BY n.node_id;