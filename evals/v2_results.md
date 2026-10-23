# v2 Results: Honest Refusals, Assumptions, Guardrails

**Date:** 23 Oct 2026 · model `claude-haiku-5-5` · dev (15) and held-out (10) sets.

## What changed from v1

| Change | File | Targets |
|---|---|---|
| Model replies in JSON: `sql` **or** `cannot_answer`, plus `assumptions` | `copilot.py` | Held-out: invented substitutes when data didn't exist |
| Prompt: refuse only when the data is missing, never when a term is just undefined | `copilot.py` | Over-refusal |
| Assumptions shown to the user under the answer | `copilot.py` | Trust: every interpretation is visible |
| SELECT-only check before any SQL runs (single statement, no write keywords) | `copilot.py` | Safety, second layer behind the read-only connection |
| Row limit (10,000) on any result | `copilot.py` | Memory, runaway queries |
| Answers give the full row count; full results saved to CSV | `copilot.py` | Answers said "only the first 50 shown" or generalised from 50 rows |
| 10 database indexes + `ANALYZE` | `generate_data.py` | Slow AI-written queries hit the 30 s timeout |

No glossary or worked-example changes: the held-out questions stay unseen.

## Scores

| Version | Dev | Held-out | Cost / question | Avg time | Slowest | Retries |
|---|---|---|---|---|---|---|
| v1 | 15/15 (×3 runs) | 5/10 | $0.0012–0.0016 | 7–10 s | 43 s | 0–1 |
| v2, before indexes | 14/15 | 7/10 | $0.0015 | 10.5 s | 44 s | 1 |
| **v2** | **15/15** | **8/10** | **$0.0014** | **7.7 s** | **18.6 s** | **0** |

All scores use the current answer key ([change log](golden_changes.md)).

## What each change did

| Question | v1 | v2 | |
|---|---|---|---|
| T6 trucks over weight limit (no weight data) | Swapped in pallet capacity, answered "none over" | **Refused**: "no weight data; truck_runs holds pallet capacity and pallets loaded" | Fixed |
| T3 node forecast vs actual (no node-level forecast) | Allocated shipper forecasts by actual share, 3,680 rows | **Refused**: forecasts are per shipper, no node_id | Fixed |
| H3 unplanned holiday volume | Timed out, retried, passed once; failed once with a join fan-out after the retry | Passes in ~8 s, no retry | Fixed by indexes |
| T4 nodes closed in IT, open in ES | Invented "closed = no truck runs" | Refused: no open/closed field | Still fails: "closed = bank holiday" is not in the glossary |
| T5 most wasted trucks, week 30 | Pass | Fail, then pass | Week numbering is undefined; the model picks a convention per run |
| T8 daily gap > 200 | Fail | Fail | Days with volume but no forecast are skipped |
| Dev (15) | 15/15 | 15/15 | **No over-refusal** on answerable questions |

## Findings

1. **The copilot can now say "I don't have that data."** Both missing-data questions
   are refused with the exact missing field named, and no dev question was refused.
2. **The remaining held-out failures are all glossary gaps** (week numbering, "closed",
   unforecast days), not SQL or honesty. They are fixed next, followed by a fresh
   held-out set, since fixing them turns these questions into dev questions.
3. **Undefined terms make results vary between runs.** In one run the model numbered
   weeks two ways (T1 one way, T5 the other); T5 passed in one v2 run and failed in the
   other. Held-out v2 is 7–8/10 across two runs.
4. **Speed was a data problem, not a model problem.** The database had no indexes.
   With indexes the slowest question dropped from 44 s to 19 s and timeouts stopped.
5. **Assumptions make vague questions checkable.** "Which shippers had a big drop
   recently?" now lists: Sep vs Aug 2026, drop ≥ 20%, zero-volume shippers included,
   no minimum volume. A PM can disagree with a line instead of reverse-engineering SQL.

## Limits

- Held-out is 10 questions over 2 runs; one question is 10 points.
- The refusal rule is judged on 2 refusal questions only. More are needed in the 50-question set.
- The SELECT-only check is keyword-based; it sits behind a read-only connection, which
  is the real protection.