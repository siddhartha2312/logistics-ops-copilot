# Golden Answer Changes

Every change to a golden question after it was first written is logged here,
so a score change can always be traced to either the copilot or the answer key.

| Date | Question | Change | Reason | Effect on scores |
|---|---|---|---|---|
| 2026-10-22 | E3 (% UK shipments held at customs) | Denominator changed from all UK shipments to **non-cancelled** UK shipments (8.22% → 8.54%) | Cancelled shipments never reach customs, so including them understates the rate. Makes every shipment rate use the same denominator as on-time. Decided by the domain owner on business grounds after the v1 run exposed that the definition had never been agreed. | All versions re-scored against the updated golden (see `rescore.py`) |
| 2026-10-22 | Judge: numeric matching (`compare.py`) | Golden and AI values are now sorted and matched in order, instead of in their original order | Held-out T9: 928 correct ADVs failed because, with many values close together, an AI value that fit two golden values was taken by the wrong one. Sorted matching finds a match whenever one exists, so no earlier pass can turn into a fail. | Held-out T9 FAIL → PASS |
| 2026-10-22 | Judge: refusal questions (`run_evals.py`, `rescore.py`) | An empty result no longer counts as a refusal; only "no answer returned" passes | Held-out T6: the copilot swapped weight for pallet capacity and answered "no trucks over the limit". An empty answer is still an answer, and here a misleading one. | Held-out T6 PASS → FAIL |