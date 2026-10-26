# Semantic Layer

Verified views that hold the business definitions as SQL. Query these instead of
rebuilding the logic from raw tables. The copilot reads this file with every
question; dashboards and analysts should use the same views.

**Rule:** if a view has the column you need, use it. Only go to raw tables for
columns no view has.

---

## v_shipments: one row per shipment

All shipments, including cancelled ones, with pickup date, week and both countries.

| Column | Meaning |
|---|---|
| shipment_id, shipper_id, run_id, node_id | Keys |
| shipper_name, account_manager | From `shippers` |
| shipper_country | `shippers.country`: use for shipper metrics |
| node_country | Destination node's country: use for truck/node metrics |
| run_type, carrier | From the shipment's truck run |
| service_level, status, hold_reason | As in `shipments` |
| created_date | Use for counts by status (e.g. how many were cancelled) |
| pickup_date | `truck_runs.run_date`: use for volume, on-time and periods |
| week_start | Sunday that starts the pickup week (Sun–Sat) |
| promised_date, delivered_to_node_date | As in `shipments` |
| is_cancelled | 1 if cancelled, else 0 |
| volume_packages | Packages, **0 if cancelled**. `SUM(volume_packages)` = volume |
| packages, pallets | Raw values, including cancelled |
| is_on_time | 1 if delivered on or before promised, 0 if not (incl. undelivered), **NULL if cancelled**. `AVG(is_on_time)` = on-time rate over non-cancelled shipments |
| is_customs_hold | 1 if held at customs, 0 if not, **NULL if cancelled**. `AVG(is_customs_hold)` = customs-hold rate |

## v_attainment_daily: one row per shipper per forecast day

Forecast-driven: only days with a forecast row. Actual volume is already
aggregated per shipper and day (no fan-out).

| Column | Meaning |
|---|---|
| shipper_id, shipper_name, account_manager, shipper_country | Shipper |
| day | Forecast date = pickup date |
| week_start | Sunday that starts the week |
| forecast_packages | Forecast for that day |
| actual_packages | Non-cancelled packages picked up that day, 0 if none |

Attainment for any period = `SUM(actual_packages) / SUM(forecast_packages)`.
Never average daily ratios.

## v_truck_runs: one row per truck run

| Column | Meaning |
|---|---|
| run_id, run_date, week_start | Run and its pickup date / week |
| run_type, carrier, node_id, node_country | Route and destination |
| run_outcome | `completed`, `wasted`, ... as in `truck_runs` |
| pallet_capacity, pallets_loaded | Utilisation = `SUM(pallets_loaded) / SUM(pallet_capacity)` |
| cost_eur | Full run cost |
| is_adhoc, is_wasted | 1/0 flags |
| is_late | 1 if arrived after planned, 0 if on time, **NULL if not completed**. `AVG(is_late)` = late rate over completed runs |
| adhoc_premium_eur | `cost_eur * 0.6 / 1.6` for ad-hoc runs, else 0 |
| avoidable_cost_eur | Wasted-run cost + ad-hoc premium |
| n_stops | Number of pickup stops on the run |

Node load per day = `SUM(pallets_loaded)` by `node_id`, `run_date`.

## v_shipper_avoidable_cost: one row per shipper per run stop

A run's cost split equally across its stops, so it can be attributed to
shippers and Account Managers without double-counting milkruns.

| Column | Meaning |
|---|---|
| run_id, run_date, week_start, shipper_id | Run, date, shipper |
| account_manager, shipper_country | From `shippers` |
| cost_share_eur | `cost_eur / n_stops` |
| avoidable_cost_share_eur | `avoidable_cost_eur / n_stops` |

Avoidable cost per AM = `SUM(avoidable_cost_share_eur)` grouped by `account_manager`.