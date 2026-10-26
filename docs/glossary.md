# Business Glossary

Agreed definitions for the first-mile network. The copilot reads this file with
every question; analysts and dashboards should use the same definitions.

Most of these definitions are already built into the semantic layer views
(`docs/semantic_layer.md`). Use the views; this file explains what they mean and
covers what views can't hold (periods, thresholds, ranking rules).

## Dates and periods

- **Today** is 2026-10-19. Last quarter = 2026-07-01 to 2026-09-30.
  Last month = September 2026. Quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec.
- **Peak** = Black Friday to Christmas Eve. Peak 2025 = 2025-11-28 to 2025-12-24.
- **Week** = Sunday to Saturday, labelled by its Sunday date (`week_start`).
  SQLite: `date(d, '-' || strftime('%w', d) || ' days')`. Never use `%W` (Monday weeks).
  A week belongs to a period if its `week_start` falls inside the period.
- **Pickup date** = `truck_runs.run_date`. Use it for volume, attainment, cost,
  utilisation, on-time and node load, and to decide which period a run belongs to.
- **Shipment counts by status** (e.g. cancelled, on hold) use `shipments.created_date`.

## Volume and forecast

- **Volume** = packages (not pallets), from shipments with `status <> 'Cancelled'`.
- **Actual volume** for a shipper on a day = packages of their non-cancelled shipments
  on truck runs with that `run_date` (join `shipments.run_id` to `truck_runs`).
- **Attainment** = actual volume ÷ forecast packages.
  - Start from `forecasts`, LEFT JOIN actual volume on shipper and
    `forecast_date = run_date`; missing actual = 0.
  - Aggregate actual volume to shipper × day **before** joining (avoid fan-out).
  - Only days that have a forecast row count. Weekly / quarterly attainment =
    sum of actual ÷ sum of forecast over those days.
  - Healthy band: 90%–110%. "Missed the band" = below 90% or above 110%.
  - When ranking shippers by attainment, ignore low volume: weekly forecast
    below 50 packages, or quarterly forecast below 500 packages.
- **Unplanned volume** = actual volume on a shipper-day with **no** forecast row
  (e.g. shipping on a bank holiday without opting in). Holidays match the
  shipper's country.

## Delivery and trucks

- **Rates over shipments** (on-time, customs hold, compliance hold, ...) use
  **non-cancelled** shipments as the denominator. Cancelled shipments never
  reach the node or customs.
- **On-time rate** = shipments delivered to the node on or before `promised_date`
  ÷ **all non-cancelled** shipments. Undelivered (on hold, in transit) count as not on time.
- **Cost per package** = total `cost_eur` of all truck runs in the period,
  **including wasted runs** ÷ packages of non-cancelled shipments on those runs.
- **Truck utilisation** = SUM(`pallets_loaded`) ÷ SUM(`pallet_capacity`).
  Never average per-truck ratios.
- **Node load** = SUM(`truck_runs.pallets_loaded`) arriving at a node per `run_date`,
  compared with `nodes.daily_capacity_pallets`. Not based on delivered dates.
- **Country**: for truck metrics use the destination node's country
  (`truck_runs.node_id` → `nodes.country`); for shipper metrics use `shippers.country`.

## Cost of planning misses

- **Wasted truck** = `run_outcome = 'wasted'` (shipper closed on arrival). Full cost counts.
- **Ad-hoc truck** = `is_adhoc = 1` (same-day, unplanned). Costs 1.6× a planned truck,
  so the **ad-hoc premium** = `cost_eur * 0.6 / 1.6`.
- **Avoidable cost** = wasted-truck cost + ad-hoc premium. Both parts, always.
  For a multi-stop run, split the cost equally across its stops (`run_stops`).
  Attribute to Account Managers through `shippers.account_manager`.

## Milkruns and exceptions

- **Late arrival** = `actual_arrival_time > planned_arrival_time` (completed runs only).
- **Milkrun delay blame**: for each stop, delay added = its pickup lateness
  (`actual_pickup_time − planned_pickup_time` in `run_stops`) minus the previous
  stop's lateness. A late milkrun is blamed on the stop that added the most delay.
  When ranking shippers, require at least 20 milkruns.
- **Exceptions table**: run-level types (Late arrival at node, Truck no-show,
  Weather site closure, Partial pickup, Ad-hoc truck request, Shipper closed on arrival)
  have **no** `shipment_id`. Link them to shippers through `run_stops.run_id`, not shipments.