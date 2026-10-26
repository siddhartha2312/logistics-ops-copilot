# v3 Results: Semantic Layer

**Date:** 26 Oct 2026 · model `claude-haiku-5-5` · dev (15) and held-out (10) sets.

## What changed from v2

| Change | File |
|---|---|
| Four verified views holding the business definitions: `v_shipments`, `v_attainment_daily`, `v_truck_runs`, `v_shipper_avoidable_cost` | `db/semantic.sql` |
| Tests: views add no rows, cost split adds back to the total, and 7 golden answers are reproduced through the views | `db/test_semantic.py` |
| View and column meanings sent with every question; prompt rule "prefer the views" | `docs/semantic_layer.md`, `copilot.py` |
| Worked examples rewritten on the views (same results as before) | `docs/sql_examples.md` |
| Views built automatically with the database | `generate_data.py` |

Views encode only definitions already in the glossary. Nothing was designed from a
held-out failure, so the held-out set stays unseen.

## Scores

| Version | Dev | Held-out | Cost / question | Avg time |
|---|---|---|---|---|
| v2 | 15/15 | 7–8/10 | $0.0014–0.0015 | 7.7 s |
| **v3** | **15/15** | **8/10** | **$0.0015** | **7.8 s** |

Accuracy, cost and speed are unchanged. The difference is in the SQL the AI writes.

## SQL written by the AI

| Measure | Dev v2 | Dev v3 | Held-out v2 | Held-out v3 |
|---|---|---|---|---|
| Queries using a view | 0 / 15 | **13 / 15** | 0 / 7 | **6 / 7** |
| JOINs | 28 | **8 (−71%)** | 15 | **3 (−80%)** |
| CASE logic (business rules) | 4 | **0** | 2 | 2 |
| Average lines | 19.9 | **15.7** | 17.0 | **13.9** |

Biggest simplifications: weekly attainment 29 → 9 lines, lowest attainment 28 → 11,
avoidable cost by AM 20 → 6. Unplanned holiday volume dropped from 5 joins to 0, the
same join that double-counted in a v2 run.

## Findings

1. **The semantic layer didn't change accuracy, because v2 already applied these
   definitions correctly.** Its value is risk: the AI no longer writes the business
   logic, so new questions have far fewer places to go wrong.
2. **Definitions now live in one verified place.** The tests prove the views reproduce
   the golden answers. Any dashboard reading the same views gets the same numbers.
3. **Uncovered logic is still rebuilt.** Milkrun delay blame has no view yet, so its
   SQL stayed at ~50 lines with 5 joins. A view is worth adding if logged questions
   show it is asked often.
4. **Answers can still generalise from the visible rows.** One answer described "the 50
   rows shown" despite the prompt rule. To fix with the answer prompt.

## Limits

- One run per set. Fewer joins should mean more stable results; repeat runs will show it.
- In production these views would live in dbt (or a BI semantic model), owned and
  tested by the data team.