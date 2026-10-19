# Data Model: Simulated European First-Mile Parcel Network

## Data volume
- Shippers: 1,000 (250 per country)
- Nodes: 40 (10 per country)
- Shipments: ~300,000
- Forecasts: weekly, per shipper (~91 weeks)


Synthetic dataset modelling inbound pickup from shipper warehouses to delivery
nodes across UK, FR, IT and ES. Date range: 2025-01-01 to 2026-09-30.

## Flow
Shipper Warehouse → Truck Run (Direct or Milkrun) → Node (Delivery Station / Warehouse)

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
| run_date | Date of the run |
| run_type | direct / milkrun |
| carrier | Trucking carrier name |
| node_id | Destination node |
| planned_pickup_time | Scheduled pickup at first shipper |
| actual_pickup_time | Actual pickup at first shipper |
| planned_arrival_time | Scheduled arrival at node |
| actual_arrival_time | Actual arrival at node |
| pallet_capacity | Max pallets the truck can carry |
| pallets_loaded | Pallets actually loaded |
| cost_eur | Total cost of the run |

### run_stops
| Column | Description |
|---|---|
| run_id | Truck run ID |
| shipper_id | Shipper visited |
| stop_sequence | Order of the stop (1 for direct; 1..n for milkrun) |
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
| week_start_date | Monday of the forecast week |
| forecast_packages | Forecasted packages for that week |

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
- **Shipper Warehouse**: shipper site where trucks pick up packages.
- **Node**: delivery station or warehouse where shipments are dropped.
- **Service levels**: 1DD = one-day delivery (promised = created + 1 day); NDD = next-day-plus delivery (promised = created + 2 to 3 days).
- **On-time delivery**: shipment delivered to node **on or before** promised_date. Cancelled shipments are excluded.
- **Pickup on-time**: actual_pickup_time within 30 minutes of planned_pickup_time.
- **Truck Run Type**:
  - Direct: one truck picks up from one shipper and drops at one node.
  - Milkrun: one truck picks up from 2+ nearby shippers and drops at one node.
- **Attainment** = actual packages received / forecast_packages, per shipper per week.
  - Healthy: within ±10% (90%–110%). Can exceed 100%.
- **SPP (packages per pallet)** = packages / pallets.
- **Truck utilisation** = pallets_loaded / pallet_capacity.
- **Cost per package** = truck run cost_eur / total packages on that run.
- **Last quarter (LQ)**: the full calendar quarter before today's quarter.
  Quarters: Q1 Jan–Mar, Q2 Apr–Jun, Q3 Jul–Sep, Q4 Oct–Dec.
  As of Oct 2026, LQ = Q3 2026 (Jul–Sep 2026).
- **WBR**: Weekly Business Review, where attainment, on-time rate, utilisation and cost per package are reviewed.
- **Transport Planning team**: plans truck runs and capacity.

## Exception types
- Truck no-show
- Late arrival at node
- Partial pickup (shipper not ready)
- Node capacity rejection
- Weather site closure
- Customs hold
- Damaged freight

## Planted scenarios (known truths for evaluation)
1. UK-only customs holds (~8% of UK shipments).
2. Milkruns: lower cost per package, higher late-arrival rate than direct runs.
3. Peak season (Black Friday to Christmas): one node exceeds capacity, causing rollovers to the next day.
4. Forecast bias: a few shippers consistently over-forecast (attainment ~70%), leading to low truck utilisation.
5. Country bank holidays shift pickups (e.g. Ferragosto, 15 Aug, IT).
6. Winter weather site closures, mostly in the UK.
7. Shippers onboarded in the last 60 days have more compliance holds.
8. De-listed shippers have zero volume after delisted_date.