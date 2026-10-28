-- =====================================================================
-- Held-out queries: Logistics Ops Copilot
-- Ground-truth SQL for questions that were NOT used to write the
-- glossary or the worked examples. Questions were written by the domain
-- owner without the glossary in front of them. T1, T4, T5 and T8 moved to the dev
-- set on 2026-10-26 after the glossary was fixed on their failures. Do not tune the copilot
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


-- =====================================================================
-- Batch 2 (2026-10-28): 26 questions drafted by the builder from real
-- logistics pain points (not from the glossary), reviewed and accepted by
-- the domain owner before any run. Answer keys committed before the run.
-- "Expect: no_data" = passes if the copilot refuses OR returns nothing.
-- "Expect: clarify" = not scored yet (baseline for clarifying questions).
-- =====================================================================


-- ---------------------------------------------------------------------
-- T11. which carriers had the most truck no-shows last month?
-- Level: easy
-- Definition: 'Truck no-show' exceptions on runs picked up in Sep 2026, by carrier.
-- Check: carrier, no_shows
-- ---------------------------------------------------------------------
SELECT r.carrier, COUNT(*) AS no_shows
FROM exceptions e
JOIN truck_runs r ON r.run_id = e.run_id
WHERE e.exception_type = 'Truck no-show'
  AND r.run_date BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY r.carrier
ORDER BY no_shows DESC;


-- ---------------------------------------------------------------------
-- T12. how many adhoc trucks did we book each week in Sept and how much extra did it cost us
-- Level: medium
-- Definition: Sun-Sat weeks whose week_start is in Sep 2026; extra cost = ad-hoc premium cost*0.6/1.6.
-- Check: adhoc_trucks, extra_cost_eur
-- ---------------------------------------------------------------------
SELECT date(run_date, '-' || strftime('%w', run_date) || ' days') AS week_start,
       COUNT(*) AS adhoc_trucks,
       ROUND(SUM(cost_eur * 0.6 / 1.6), 2) AS extra_cost_eur
FROM truck_runs
WHERE is_adhoc = 1
  AND date(run_date, '-' || strftime('%w', run_date) || ' days') BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY week_start
ORDER BY week_start;


-- ---------------------------------------------------------------------
-- T13. avg pickup delay by carrier for UK in Q3, in minutes
-- Level: medium
-- Definition: completed runs to UK nodes, run_date in Q3 2026; delay = actual - planned
--   pickup time on the run (early pickups count as negative).
-- Check: avg_delay_min
-- ---------------------------------------------------------------------
SELECT r.carrier,
       ROUND(AVG((julianday(r.actual_pickup_time) - julianday(r.planned_pickup_time)) * 1440), 1) AS avg_delay_min
FROM truck_runs r
JOIN nodes n ON n.node_id = r.node_id
WHERE n.country = 'UK'
  AND r.run_outcome = 'completed'
  AND r.actual_pickup_time IS NOT NULL
  AND r.run_date BETWEEN '2026-07-01' AND '2026-09-30'
GROUP BY r.carrier
ORDER BY avg_delay_min DESC;


-- ---------------------------------------------------------------------
-- T14. which milkrun routes have the worst truck fill?
-- Level: medium
-- Expect: clarify
-- Why: "route" is not defined (no route id); the copilot should ask what a route is.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T15. which of my shippers were closed when the truck arrived more than twice last quarter?
-- Level: medium
-- Expect: clarify
-- Why: "my" needs to know which Account Manager is asking.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T16. shippers onboarded in 2026 that havent shipped anything since August
-- Level: medium
-- Definition: onboarded_date in 2026, no non-cancelled pickup on/after 2026-08-01.
--   Every 2026 shipper is still shipping, so the correct answer is none.
-- Check: (expect no rows)
-- ---------------------------------------------------------------------
SELECT s.shipper_id, s.name
FROM shippers s
WHERE s.onboarded_date >= '2026-01-01'
  AND NOT EXISTS (SELECT 1 FROM shipments x JOIN truck_runs r ON r.run_id = x.run_id
                  WHERE x.shipper_id = s.shipper_id AND x.status <> 'Cancelled'
                    AND r.run_date >= '2026-08-01');


-- ---------------------------------------------------------------------
-- T17. top 10 shippers by volume growth, Q3 vs Q2
-- Level: medium
-- Definition: % growth in non-cancelled packages (pickup date), Q3 vs Q2 2026; only
--   shippers with at least 500 packages in Q2.
-- Check: shipper_id|name
-- ---------------------------------------------------------------------
WITH q AS (
    SELECT s.shipper_id,
           SUM(CASE WHEN r.run_date BETWEEN '2026-04-01' AND '2026-06-30' THEN s.packages ELSE 0 END) AS q2,
           SUM(CASE WHEN r.run_date BETWEEN '2026-07-01' AND '2026-09-30' THEN s.packages ELSE 0 END) AS q3
    FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id
)
SELECT q.shipper_id, sh.name, q.q2, q.q3, ROUND(100.0 * (q.q3 - q.q2) / q.q2, 1) AS growth_pct
FROM q JOIN shippers sh ON sh.shipper_id = q.shipper_id
WHERE q.q2 >= 500
ORDER BY growth_pct DESC
LIMIT 10;


-- ---------------------------------------------------------------------
-- T18. which shippers ship on bank holidays without telling us?
-- Level: medium
-- Definition: non-cancelled volume on a bank holiday in the shipper's country with no
--   forecast row for that day (all dates).
-- Check: shipper_id
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT s.shipper_id, r.run_date AS day, SUM(s.packages) AS packages
    FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, r.run_date
)
SELECT DISTINCT d.shipper_id
FROM daily d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
JOIN holidays h ON h.country = sh.country AND h.holiday_date = d.day
WHERE NOT EXISTS (SELECT 1 FROM forecasts f WHERE f.shipper_id = d.shipper_id AND f.forecast_date = d.day)
ORDER BY d.shipper_id;


-- ---------------------------------------------------------------------
-- T19. which day of the week is busiest for the Manchester node, in pallets?
-- Level: easy
-- Definition: N-UK-02, average pallets arriving per day, over days with trucks, all dates.
-- Check: avg_pallets
-- ---------------------------------------------------------------------
WITH daily AS (
    SELECT run_date, SUM(pallets_loaded) AS pallets
    FROM truck_runs WHERE node_id = 'N-UK-02'
    GROUP BY run_date
)
SELECT CASE strftime('%w', run_date) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday'
         WHEN '2' THEN 'Tuesday' WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday'
         WHEN '5' THEN 'Friday' ELSE 'Saturday' END AS weekday,
       ROUND(AVG(pallets), 1) AS avg_pallets
FROM daily
GROUP BY strftime('%w', run_date)
ORDER BY avg_pallets DESC
LIMIT 1;


-- ---------------------------------------------------------------------
-- T20. on how many days in the last 3 months did any UK node go above 90% of capacity?
-- Level: medium
-- Definition: Jul-Sep 2026; node load = pallets loaded on runs arriving that day.
-- Check: days_over_90pct
-- ---------------------------------------------------------------------
WITH load AS (
    SELECT r.node_id, r.run_date, SUM(r.pallets_loaded) AS pallets
    FROM truck_runs r
    WHERE r.run_date BETWEEN '2026-07-01' AND '2026-09-30'
    GROUP BY r.node_id, r.run_date
)
SELECT n.node_id, n.city, COUNT(*) AS days_over_90pct
FROM load l JOIN nodes n ON n.node_id = l.node_id
WHERE n.country = 'UK' AND l.pallets > 0.9 * n.daily_capacity_pallets
GROUP BY n.node_id, n.city;


-- ---------------------------------------------------------------------
-- T21. which nodes get the most late-arriving trucks?
-- Level: easy
-- Definition: completed runs arriving after planned time, all dates, top 10 nodes.
-- Check: node_id|city, late_trucks
-- ---------------------------------------------------------------------
SELECT n.node_id, n.city, COUNT(*) AS late_trucks
FROM truck_runs r JOIN nodes n ON n.node_id = r.node_id
WHERE r.run_outcome = 'completed' AND r.actual_arrival_time > r.planned_arrival_time
GROUP BY n.node_id, n.city
ORDER BY late_trucks DESC
LIMIT 10;


-- ---------------------------------------------------------------------
-- T22. which shippers have been forecasting way too high for the last 8 weeks?
-- Level: hard
-- Definition: weekly attainment below 90% in every one of the last 8 full weeks of data
--   (week_start 2026-08-02 .. 2026-09-20), forecast days only.
-- Check: shipper_id
-- ---------------------------------------------------------------------
WITH actual AS (
    SELECT s.shipper_id, r.run_date AS day, SUM(s.packages) AS packages
    FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, r.run_date
),
weekly AS (
    SELECT f.shipper_id,
           date(f.forecast_date, '-' || strftime('%w', f.forecast_date) || ' days') AS week_start,
           1.0 * SUM(COALESCE(a.packages, 0)) / SUM(f.forecast_packages) AS attainment
    FROM forecasts f
    LEFT JOIN actual a ON a.shipper_id = f.shipper_id AND a.day = f.forecast_date
    GROUP BY f.shipper_id, week_start
)
SELECT shipper_id
FROM weekly
WHERE week_start BETWEEN '2026-08-02' AND '2026-09-20'
GROUP BY shipper_id
HAVING COUNT(*) = 8 AND MAX(attainment) < 0.9
ORDER BY shipper_id;


-- ---------------------------------------------------------------------
-- T23. forecast accuracy by country for September
-- Level: hard
-- Definition: 1 - SUM|actual - forecast| / SUM forecast over every shipper-day in Sep 2026
--   with a forecast or volume (WAPE accuracy), by shipper country.
-- Check: accuracy_pct
-- ---------------------------------------------------------------------
WITH actual AS (
    SELECT s.shipper_id, r.run_date AS day, SUM(s.packages) AS packages
    FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
    WHERE s.status <> 'Cancelled' AND r.run_date BETWEEN '2026-09-01' AND '2026-09-30'
    GROUP BY s.shipper_id, r.run_date
),
fc AS (
    SELECT shipper_id, forecast_date AS day, forecast_packages AS forecast
    FROM forecasts WHERE forecast_date BETWEEN '2026-09-01' AND '2026-09-30'
),
days AS (SELECT shipper_id, day FROM actual UNION SELECT shipper_id, day FROM fc)
SELECT sh.country,
       ROUND(100.0 * (1 - 1.0 * SUM(ABS(COALESCE(a.packages, 0) - COALESCE(f.forecast, 0)))
                          / SUM(COALESCE(f.forecast, 0))), 1) AS accuracy_pct
FROM days d
JOIN shippers sh ON sh.shipper_id = d.shipper_id
LEFT JOIN actual a ON a.shipper_id = d.shipper_id AND a.day = d.day
LEFT JOIN fc f ON f.shipper_id = d.shipper_id AND f.day = d.day
GROUP BY sh.country
ORDER BY sh.country;


-- ---------------------------------------------------------------------
-- T24. which shippers dont send a forecast but still ship?
-- Level: medium
-- Definition: shippers with non-cancelled volume on at least one day without a forecast row.
-- Check: shipper_id
-- ---------------------------------------------------------------------
SELECT DISTINCT s.shipper_id
FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
WHERE s.status <> 'Cancelled'
  AND NOT EXISTS (SELECT 1 FROM forecasts f WHERE f.shipper_id = s.shipper_id AND f.forecast_date = r.run_date)
ORDER BY s.shipper_id;


-- ---------------------------------------------------------------------
-- T25. for UK customs holds, how many days on average to resolve them in Q3?
-- Level: medium
-- Expect: no_data
-- Why: customs-hold exceptions have no resolution date recorded (all blank).
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T26. how many shipments are stuck in transit for more than 7 days?
-- Level: easy
-- Definition: status 'In Transit', created more than 7 days before today (2026-10-19).
-- Check: stuck_shipments
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS stuck_shipments
FROM shipments
WHERE status = 'In Transit' AND created_date < '2026-10-12';


-- ---------------------------------------------------------------------
-- T27. split of service levels by country last month
-- Level: easy
-- Definition: share of non-cancelled shipments by service level, by shipper country,
--   pickup date in Sep 2026.
-- Check: share_pct
-- ---------------------------------------------------------------------
SELECT sh.country, s.service_level, COUNT(*) AS shipments,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY sh.country), 1) AS share_pct
FROM shipments s
JOIN truck_runs r ON r.run_id = s.run_id
JOIN shippers sh ON sh.shipper_id = s.shipper_id
WHERE s.status <> 'Cancelled' AND r.run_date BETWEEN '2026-09-01' AND '2026-09-30'
GROUP BY sh.country, s.service_level
ORDER BY sh.country, s.service_level;


-- ---------------------------------------------------------------------
-- T28. how are we doing on on-time lately?
-- Level: easy
-- Definition: "lately" = last month (Sep 2026); on-time rate over non-cancelled shipments.
-- Check: on_time_pct
-- ---------------------------------------------------------------------
SELECT ROUND(100.0 * AVG(CASE WHEN s.delivered_to_node_date IS NOT NULL
                               AND s.delivered_to_node_date <= s.promised_date THEN 1 ELSE 0 END), 1) AS on_time_pct
FROM shipments s JOIN truck_runs r ON r.run_id = s.run_id
WHERE s.status <> 'Cancelled' AND r.run_date BETWEEN '2026-09-01' AND '2026-09-30';


-- ---------------------------------------------------------------------
-- T29. who are our problem shippers?
-- Level: medium
-- Expect: clarify
-- Why: "problem" could mean wasted trucks, low attainment, late pickups, holds...
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T30. is any node in trouble this week?
-- Level: medium
-- Expect: no_data
-- Why: this week (from 2026-10-18) is after the data ends (2026-09-30).
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T31. which drivers did the most overtime in September?
-- Level: easy
-- Expect: refusal
-- Why: no driver or working-hours data.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T32. what's the fuel cost per km by carrier?
-- Level: easy
-- Expect: refusal
-- Why: no fuel cost or distance data.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T33. how much revenue did our top 20 shippers bring in Q3?
-- Level: easy
-- Expect: refusal
-- Why: no revenue or pricing data.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T34. how many packages got damaged at the Lyon node?
-- Level: easy
-- Definition: 'Damaged freight' exceptions on shipments delivered to the Lyon node
--   (N-FR-02), all dates. Damage is recorded per shipment, not per package.
-- Check: damaged_shipments
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS damaged_shipments
FROM exceptions e
JOIN shipments s ON s.shipment_id = e.shipment_id
JOIN nodes n ON n.node_id = s.node_id
WHERE e.exception_type = 'Damaged freight' AND n.city = 'Lyon';


-- ---------------------------------------------------------------------
-- T35. what's the CO2 per package for milkrun vs direct?
-- Level: easy
-- Expect: refusal
-- Why: no emissions, fuel or distance data.
-- ---------------------------------------------------------------------


-- ---------------------------------------------------------------------
-- T36. which AMs have repeat-offender shippers (2+ wasted trucks in the same month), and what did those wasted trucks cost?
-- Level: hard
-- Definition: wasted run = shipper closed on arrival (one stop); offender = shipper with
--   2+ wasted runs in one calendar month (pickup date); cost = full cost of those runs.
-- Check: account_manager, wasted_cost_eur
-- ---------------------------------------------------------------------
WITH wasted AS (
    SELECT rs.shipper_id, strftime('%Y-%m', r.run_date) AS month, r.cost_eur
    FROM truck_runs r JOIN run_stops rs ON rs.run_id = r.run_id
    WHERE r.run_outcome = 'wasted'
),
offences AS (
    SELECT shipper_id, month, COUNT(*) AS wasted_trucks, SUM(cost_eur) AS cost
    FROM wasted GROUP BY shipper_id, month HAVING COUNT(*) >= 2
)
SELECT sh.account_manager,
       COUNT(DISTINCT o.shipper_id) AS offender_shippers,
       SUM(o.wasted_trucks) AS wasted_trucks,
       ROUND(SUM(o.cost), 2) AS wasted_cost_eur
FROM offences o JOIN shippers sh ON sh.shipper_id = o.shipper_id
GROUP BY sh.account_manager
ORDER BY wasted_cost_eur DESC;