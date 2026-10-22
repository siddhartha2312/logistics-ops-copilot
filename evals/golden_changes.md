# Golden Answer Changes

Every change to a golden question after it was first written is logged here,
so a score change can always be traced to either the copilot or the answer key.

| Date | Question | Change | Reason | Effect on scores |
|---|---|---|---|---|
| 2026-10-22 | E3 (% UK shipments held at customs) | Denominator changed from all UK shipments to **non-cancelled** UK shipments (8.22% → 8.54%) | Cancelled shipments never reach customs, so including them understates the rate. Makes every shipment rate use the same denominator as on-time. Decided by the domain owner on business grounds after the v1 run exposed that the definition had never been agreed. | All versions re-scored against the updated golden (see `rescore.py`) |