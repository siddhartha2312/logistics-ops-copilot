# Data Model: Simulated European First-Mile Parcel Network

Synthetic dataset modelling inbound pickup from shipper warehouses to delivery
nodes across UK, FR, IT and ES. Date range: 2025-01-01 to 2026-09-30.
Rebuild it any time with `python generate_data.py` (seed 42, same data every run).

## Data volume
- Shippers: 1,000 (250 per country), 25 Account Managers
- Nodes: 40 (10 per country)
- Truck runs: ~293,000
- Shipments: ~411,000
- Forecasts: daily, per shipper, operating days only (~369,000 rows)

## Flow
Daily forecast → Truck planned → Shipper Warehouse → Truck Run (Direct or Milkrun) → Node

## Tables

### shippers
| Column | Description |
|---|---|
| shipper_id | Unique shipper ID |
| name | Shipper name |
| country | UK, FR, IT, ES |
| city | Shipper warehouse city |
| onboarded_date | Date shipper joined the network |
| status | active / de-listed |
| delisted_date | Date de-listed (null if active) |
| operating_days | Days the shipper ships: Mon-Fri / Mon-Sun / Mon-Sat / Tue-Sun |
| ships_on_holidays | 1 if shipper has opted in to ship on bank holidays, else 0 |
| account_manager | Account Manager (AM) who owns the shipper relationship |

### nodes
| Column | Description |
|---|---|
| node_id | Unique node ID |
| node_type | delivery_station / warehouse |
| country | UK, FR, IT, ES |
| city | Node city |
| daily_capacity_pallets | Max pallets the node can receive per day |

### truck_runs
| Column | Description |
|---|---|
| run_id | Unique truck run ID |
| run_date | Pickup date of the run |
| run_type | direct / milkrun |
| carrier | Trucking carrier name |
| node_id | Destination node |
| planned_pickup_time | Scheduled pickup at first shipper |
| actual_pickup_time | Actual pickup at first shipper (null if cancelled) |
| planned_arrival_time | Scheduled arrival at node (includes planning buffer) |
| actual_arrival_time | Actual arrival at node (null if cancelled or wasted) |
| pallet_capacity | Max pallets the truck can carry (booked against forecast) |
| pallets_loaded | Pallets actually loaded |
| cost_eur | Total cost of the run |
| is_adhoc | 1 if truck was requested same-day (not in plan), else 0 |
| run_outcome | completed / wasted (truck arrived, shipper closed, no pickup) |

### run_stops
| Column | Description |
|---|---|
| run_id | Truck run ID |
| shipper_id | Shipper visited |
| stop_sequence | Order of the stop (1 for direct; 1..n for milkrun) |
| planned_pickup_time | Scheduled pickup at this stop (milkrun stops 40 min apart) |
| actual_pickup_time | Actual pickup at this stop (null if run cancelled) |
| pallets_picked | Pallets picked at this stop |

### shipments
| Column | Description |
|---|---|
| shipment_id | Unique shipment ID |
| shipper_id | Shipper sending the shipment |
| run_id | Truck run that carried it |
| node_id | Destination node |
| service_level | 1DD / NDD |
| created_date | Date shipment was created |
| promised_date | Date it must reach the node |
| delivered_to_node_date | Actual date it reached the node (null if not delivered) |
| status | Created / Picked Up / In Transit / Delivered to Node / On Hold / Cancelled |
| hold_reason | At Customs / Shipper Compliance (null if not on hold) |
| packages | Number of packages |
| pallets | Number of pallets |

### forecasts
| Column | Description |
|---|---|
| shipper_id | Shipper |
| forecast_date | Pickup date being forecast |
| forecast_packages | Forecasted packages to be picked up that day |

Forecast rows exist only for days the shipper operates. No forecast on a
country bank holiday unless ships_on_holidays = 1. No row = forecast of 0.

### holidays
| Column | Description |
|---|---|
| country | UK, FR, IT, ES |
| holiday_date | Date of the bank holiday |
| holiday_name | Name of the holiday |

### exceptions
| Column | Description |
|---|---|
| exception_id | Unique exception ID |
| run_id | Related truck run (nullable) |
| shipment_id | Related shipment (nullable) |
| exception_type | See exception types below |
| exception_date | Date raised |
| resolved_date | Date resolved (null if open) |

## Business definitions
- **Reference date ("today")**: 2026-10-19. All relative dates resolve against it.
  - Last quarter (LQ) = Q3 2026 (2026-07-01 to 2026-09-30).
  - Last month = September 2026.
  - Quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec.
- **Week**: Sunday to Saturday. week_start = the Sunday.
- **Shipper Warehouse**: shipper site where trucks pick up packages.
- **Node**: delivery station or warehouse where shipments are dropped.
- **Service levels**: 1DD = one-day delivery (promised = created + 1 day);
  NDD = next-day-plus delivery (promised = created + 2 to 3 days).
- **On-time delivery**: shipment delivered to node **on or before** promised_date.
  Cancelled shipments are excluded; undelivered shipments count as not on-time.
- **Pickup on-time**: actual_pickup_time within 30 minutes of planned_pickup_time.
- **Late arrival at node**: actual_arrival_time > planned_arrival_time.
- **Planning buffer**: planned_arrival_time includes 30 minutes, plus 10 minutes
  per extra milkrun stop.
- **Truck Run Type**:
  - Direct: one truck picks up from one shipper and drops at one node.
  - Milkrun: one truck picks up from 2–4 nearby (same-city) shippers and drops at one node.
- **Actual volume** = packages picked up on a date: shipments joined to
  truck_runs, grouped by shipper and truck_runs.run_date. Cancelled shipments excluded.
- **Attainment (daily)** = actual volume / forecast_packages for that shipper and pickup date.
- **Attainment (weekly)** = sum of actual volume / sum of forecast_packages,
  per shipper per week (Sun–Sat). Used in WBR.
  - Healthy: within ±10% (90%–110%). Can exceed 100%.
- **Unplanned volume** = packages picked up on a day with no forecast (e.g. shipper
  shipped on a bank holiday without opting in). Attainment is not calculated for
  these days; report them separately.
- **Shipper schedules**: 80% Mon–Fri, 10% Mon–Sun, 10% six days (Mon–Sat or Tue–Sun).
- **Ad-hoc truck**: unplanned same-day truck, requested because a shipper had
  volume on a day with no forecast. Costs 1.6x a planned truck.
- **Wasted truck**: planned truck dispatched to a shipper that was closed
  (forecast > 0, actual = 0). Full run cost is still incurred; pallets_loaded = 0.
- **Ad-hoc rate** = ad-hoc runs / total runs.
- **Wasted truck rate** = wasted runs / planned runs.
- **Avoidable cost** = ad-hoc premium (cost_eur × 0.6 / 1.6) + wasted truck cost.
  Reviewed in WBR and followed up with the shipper's AM for root cause.
- **Milkrun delay blame**: delay added at a stop = its lateness minus the lateness
  inherited from the previous stop. A late milkrun is blamed on the stop that added the most.
- **SPP (packages per pallet)** = packages / pallets.
- **Truck utilisation** = pallets_loaded / pallet_capacity.
- **Cost per package** = truck run cost_eur / total packages on that run.
- **Peak**: Black Friday (2025-11-28) to Christmas Eve (2025-12-24).
- **WBR**: Weekly Business Review, where attainment, on-time rate, utilisation,
  cost per package and avoidable cost are reviewed.
- **Transport Planning team**: plans truck runs and capacity.

## Exception types
- Truck no-show
- Late arrival at node
- Partial pickup (shipper not ready)
- Node capacity rejection
- Weather site closure
- Customs hold
- Damaged freight
- Ad-hoc truck request
- Shipper closed on arrival (wasted truck)

## Planted scenarios (known truths for evaluation)
1. UK-only customs holds (~8% of UK shipments).
2. Milkruns: lower cost per package, higher late-arrival rate than direct runs.
3. Peak season: one node (N-UK-01) exceeds capacity, causing rollovers to the next day.
4. Forecast bias: 12 shippers consistently over-forecast (attainment ~65–70%),
   leading to low truck utilisation.
5. Country bank holidays shift pickups to the next operating day (e.g. Ferragosto, 15 Aug, IT).
6. Winter weather site closures, mostly in the UK.
7. Shippers onboarded in the last 60 days have more compliance holds.
8. De-listed shippers have zero volume after delisted_date.
9. Some shippers ship on bank holidays without opting in, creating unplanned volume with no forecast.
10. Days with no forecast but actual volume trigger ad-hoc trucks (1.6x cost).
11. Some shippers repeatedly close without notice, causing wasted trucks.
    Three AMs' portfolios account for most of the wasted-truck cost.
12. 20 "slow loader" shippers add 45–100 minutes at their stop and cause most late milkruns.