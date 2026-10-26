-- =====================================================================
-- Semantic layer: verified views holding the business definitions.
-- Spec and column meanings: docs/semantic_layer.md
-- Built by generate_data.py after the tables (DROP + CREATE, so re-runnable).
-- =====================================================================

-- One row per shipment, with pickup date, week, both countries and flags.
DROP VIEW IF EXISTS v_shipments;
CREATE VIEW v_shipments AS
SELECT s.shipment_id,
       s.shipper_id,
       sh.name                                          AS shipper_name,
       sh.account_manager,
       sh.country                                       AS shipper_country,
       s.run_id,
       s.node_id,
       n.country                                        AS node_country,
       tr.run_type,
       tr.carrier,
       s.service_level,
       s.status,
       s.hold_reason,
       s.created_date,
       tr.run_date                                      AS pickup_date,
       date(tr.run_date, '-' || strftime('%w', tr.run_date) || ' days') AS week_start,
       s.promised_date,
       s.delivered_to_node_date,
       CASE WHEN s.status = 'Cancelled' THEN 1 ELSE 0 END AS is_cancelled,
       CASE WHEN s.status = 'Cancelled' THEN 0 ELSE s.packages END AS volume_packages,
       s.packages,
       s.pallets,
       -- NULL for cancelled, so AVG() uses non-cancelled shipments as the denominator
       CASE WHEN s.status = 'Cancelled' THEN NULL
            WHEN s.delivered_to_node_date IS NOT NULL
             AND s.delivered_to_node_date <= s.promised_date THEN 1
            ELSE 0 END                                  AS is_on_time,
       CASE WHEN s.status = 'Cancelled' THEN NULL
            WHEN s.hold_reason = 'At Customs' THEN 1
            ELSE 0 END                                  AS is_customs_hold
FROM shipments s
JOIN shippers sh     ON sh.shipper_id = s.shipper_id
LEFT JOIN truck_runs tr ON tr.run_id = s.run_id
LEFT JOIN nodes n    ON n.node_id = s.node_id;


-- One row per shipper per forecast day. Actuals aggregated before the join.
DROP VIEW IF EXISTS v_attainment_daily;
CREATE VIEW v_attainment_daily AS
WITH daily_actual AS (
    SELECT s.shipper_id, tr.run_date AS day, SUM(s.packages) AS actual_packages
    FROM shipments s
    JOIN truck_runs tr ON tr.run_id = s.run_id
    WHERE s.status <> 'Cancelled'
    GROUP BY s.shipper_id, tr.run_date
)
SELECT f.shipper_id,
       sh.name                                          AS shipper_name,
       sh.account_manager,
       sh.country                                       AS shipper_country,
       f.forecast_date                                  AS day,
       date(f.forecast_date, '-' || strftime('%w', f.forecast_date) || ' days') AS week_start,
       f.forecast_packages,
       COALESCE(a.actual_packages, 0)                   AS actual_packages
FROM forecasts f
JOIN shippers sh ON sh.shipper_id = f.shipper_id
LEFT JOIN daily_actual a
       ON a.shipper_id = f.shipper_id AND a.day = f.forecast_date;


-- One row per truck run, with late flag and avoidable cost.
DROP VIEW IF EXISTS v_truck_runs;
CREATE VIEW v_truck_runs AS
WITH stops AS (
    SELECT run_id, COUNT(*) AS n_stops FROM run_stops GROUP BY run_id
)
SELECT tr.run_id,
       tr.run_date,
       date(tr.run_date, '-' || strftime('%w', tr.run_date) || ' days') AS week_start,
       tr.run_type,
       tr.carrier,
       tr.node_id,
       n.country                                        AS node_country,
       tr.run_outcome,
       tr.pallet_capacity,
       tr.pallets_loaded,
       tr.cost_eur,
       tr.is_adhoc,
       CASE WHEN tr.run_outcome = 'wasted' THEN 1 ELSE 0 END AS is_wasted,
       -- NULL unless completed, so AVG() gives the late rate over completed runs
       CASE WHEN tr.run_outcome <> 'completed' OR tr.actual_arrival_time IS NULL THEN NULL
            WHEN tr.actual_arrival_time > tr.planned_arrival_time THEN 1
            ELSE 0 END                                  AS is_late,
       CASE WHEN tr.is_adhoc = 1 THEN tr.cost_eur * 0.6 / 1.6 ELSE 0 END AS adhoc_premium_eur,
       CASE WHEN tr.run_outcome = 'wasted' THEN tr.cost_eur ELSE 0 END
     + CASE WHEN tr.is_adhoc = 1 THEN tr.cost_eur * 0.6 / 1.6 ELSE 0 END AS avoidable_cost_eur,
       COALESCE(st.n_stops, 0)                          AS n_stops
FROM truck_runs tr
LEFT JOIN nodes n ON n.node_id = tr.node_id
LEFT JOIN stops st ON st.run_id = tr.run_id;


-- One row per shipper per run stop: run cost split equally across stops.
DROP VIEW IF EXISTS v_shipper_avoidable_cost;
CREATE VIEW v_shipper_avoidable_cost AS
SELECT rs.run_id,
       r.run_date,
       r.week_start,
       rs.shipper_id,
       sh.account_manager,
       sh.country                                       AS shipper_country,
       r.cost_eur / r.n_stops                           AS cost_share_eur,
       r.avoidable_cost_eur / r.n_stops                 AS avoidable_cost_share_eur
FROM run_stops rs
JOIN v_truck_runs r ON r.run_id = rs.run_id
JOIN shippers sh    ON sh.shipper_id = rs.shipper_id;