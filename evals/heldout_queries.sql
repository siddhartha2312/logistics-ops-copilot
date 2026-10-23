-- =====================================================================
-- Held-out queries: Logistics Ops Copilot
-- Ground-truth SQL for 10 questions that were NOT used to write the
-- glossary or the worked examples. Questions were written by the domain
-- owner without the glossary in front of them. Do not tune the copilot
-- on these: they measure accuracy on unseen questions.
--
-- Same conventions as golden_queries.sql:
--   "today" = 2026-10-19, data runs 2025-01-01 .. 2026-09-30
--   Weeks run Sunday-Saturday. "Week N" = SQLite %U numbering
--   (Sunday-start, week 1 begins on the year's first Sunday).
--   Volume = packages of non-cancelled shipments, by truck_runs.run_date.
--
-- "Level:" easy / medium / hard.
-- "Check:" the columns that ARE the answer ("a|b" = either is accepted).
-- "Expect: refusal" = the data cannot answer this. The copilot passes
--   only if it returns no result table (it says it can't answer).
-- =====================================================================


-- ---------------------------------------------------------------------
-- T1. List of shippers whose weekly volume stayed constant (within ±5%) in week 20 compared to last year.
-- Level: medium
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
-- T2. Which shippers had daily pallet counts greater than 5% of their node capacity in Feb 2026?
-- Level: medium
-- Definition: pallets of non-cancelled shipments per shipper, node and pickup day,
--   compared with nodes.daily_capacity_pallets.
-- Check: shipper_id
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT s.shipper_id, s.node_id, r.run_date, SUM(s.pallets) AS pallets
    FROM shipments s
    JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
      AND r.run_date BETWEEN '2026-02-01' AND '2026-02-28'
    GROUP BY s.shipper_id, s.node_id, r.run_date
)
SELECT d.shipper_id,
       COUNT(*) AS days_over_5pct,
       ROUND(MAX(100.0 * d.pallets / n.daily_capacity_pallets), 2) AS max_share_pct
FROM daily d
JOIN nodes n ON n.node_id = d.node_id
WHERE 1.0 * d.pallets / n.daily_capacity_pallets > 0.05
GROUP BY d.shipper_id
ORDER BY d.shipper_id;


-- ---------------------------------------------------------------------
-- T3. Node volume = total packages coming into a node that day. Show weekly forecast vs actual packages per node: how much the node was expecting vs how much it got.
-- Level: hard
-- Expect: refusal
-- Why: forecasts are stored per shipper, not per node, and each shipper's volume
--   is spread across several nodes. There is no node-level forecast to compare.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T4. List of nodes which were closed in Italy but open in Spain in July 2025.
-- Level: medium
-- Definition: a node is closed on its country's bank holiday (no other closure data).
--   Italy has no bank holiday in July 2025, so the correct answer is no nodes.
-- Check: (expect no rows)
-- ---------------------------------------------------------------------
SELECT n.node_id, h.holiday_date
FROM holidays h
JOIN nodes n ON n.country = 'IT'
WHERE h.country = 'IT'
  AND h.holiday_date BETWEEN '2025-07-01' AND '2025-07-31'
  AND NOT EXISTS (SELECT 1 FROM holidays e
                  WHERE e.country = 'ES' AND e.holiday_date = h.holiday_date);


-- ---------------------------------------------------------------------
-- T5. Truck wastage: which country had the most wasted trucks in week 30 of 2026?
-- Level: medium
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
-- T6. Which trucks ran over their weight limit in Aug 2026?
-- Level: easy
-- Expect: refusal
-- Why: the data has no truck weight or weight limit.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T7. How many bank holidays are there in each country in the current calendar year?
-- Level: easy
-- Definition: calendar year 2026 = 1 Jan - 31 Dec 2026.
-- Check: country, holidays
-- ---------------------------------------------------------------------
SELECT country, COUNT(*) AS holidays
FROM holidays
WHERE holiday_date BETWEEN '2026-01-01' AND '2026-12-31'
GROUP BY country
ORDER BY country;


-- ---------------------------------------------------------------------
-- T8. For any day in 2026, list date, shipper name, country, actual, forecast and gap, where the gap between actual and forecast is more than 200 packages.
-- Level: medium
-- Definition: gap = |actual - forecast| in either direction. Any day with a forecast
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
       ABS(COALESCE(a.actual, 0) - COALESCE(f.forecast, 0)) AS gap
FROM days d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
LEFT JOIN actual a ON a.shipper_id = d.shipper_id AND a.day = d.day
LEFT JOIN forecast f ON f.shipper_id = d.shipper_id AND f.day = d.day
WHERE ABS(COALESCE(a.actual, 0) - COALESCE(f.forecast, 0)) > 200
ORDER BY d.day, sh.name;


-- ---------------------------------------------------------------------
-- T9. Create the ADV of each shipper for Jul 2026. Avg Daily Volume = total period volume / active days in the period. Active day = the shipper sent some volume and the forecast was non-zero.
-- Level: hard
-- Definition: numerator = all non-cancelled packages picked up in Jul 2026;
--   denominator = July days with packages > 0 and forecast > 0.
-- Check: shipper_id, adv
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT s.shipper_id, r.run_date AS day, SUM(s.packages) AS packages
    FROM shipments s
    JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
      AND r.run_date BETWEEN '2026-07-01' AND '2026-07-31'
    GROUP BY s.shipper_id, r.run_date
)
SELECT d.shipper_id,
       SUM(d.packages) AS july_volume,
       SUM(CASE WHEN d.packages > 0 AND f.forecast_packages > 0 THEN 1 ELSE 0 END) AS active_days,
       ROUND(1.0 * SUM(d.packages)
             / SUM(CASE WHEN d.packages > 0 AND f.forecast_packages > 0 THEN 1 ELSE 0 END), 2) AS adv
FROM daily d
LEFT JOIN forecasts f ON f.shipper_id = d.shipper_id AND f.forecast_date = d.day
GROUP BY d.shipper_id
HAVING active_days > 0
ORDER BY d.shipper_id;


-- ---------------------------------------------------------------------
-- T10. List of shipper id, name and AM of shippers dropping packages in Liverpool in the current year.
-- Level: easy
-- Definition: Liverpool = the delivery node (N-UK-06), not shippers based in Liverpool.
--   Non-cancelled shipments, pickup date in 2026.
-- Check: shipper_id
-- ---------------------------------------------------------------------
SELECT DISTINCT sh.shipper_id, sh.name, sh.account_manager
FROM shipments s
JOIN truck_runs r ON r.run_id = s.run_id
JOIN nodes n ON n.node_id = s.node_id
JOIN shippers sh ON sh.shipper_id = s.shipper_id
WHERE n.city = 'Liverpool'
  AND s.status <> 'Cancelled'
  AND r.run_date >= '2026-01-01'
ORDER BY sh.shipper_id;