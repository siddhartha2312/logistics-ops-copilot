# v1 Results: Business Glossary + Worked Examples

**Date:** 22 Oct 2026 · model `claude-haiku-5-5` · same 15 golden questions as v0.

## What changed from v0

| Change | File | Targets (v0 failure types) |
|---|---|---|
| Business glossary: agreed definitions of every metric, period and week | `docs/glossary.md` | DEF, DATE, FILTER, AMBIG |
| Three worked SQL patterns (forecast-driven join, run-level metric, on-time denominator) | `docs/sql_examples.md` | DATE, JOIN |
| Schema note: run-level exceptions have no shipment link | `docs/glossary.md` | JOIN |
| `max_tokens` 2000 → 4000 | `copilot.py` | TECH |
| 30 s SQL timeout, 60 s API timeout | `copilot.py` | Hangs (found during v1 testing) |

The worked examples use different questions, shippers and periods from the evaluation set.

## Scores (all against the same answer key)

| Version | Run | Score | Cost / question | Avg time | Slowest | Retries |
|---|---|---|---|---|---|---|
| v0 | 21 Oct 12:17 | 5 / 15 (33%) | $0.00087 | 6.6 s | 18.0 s | 1 |
| v1 | 22 Oct 12:10 | 15 / 15 | $0.00123 | 7.2 s | 17.4 s | 0 |
| v1 | 22 Oct 12:44 | 15 / 15 | $0.00120 | 7.2 s | 17.7 s | 0 |
| v1 | 22 Oct 12:47 | 15 / 15 | $0.00123 | 8.2 s | 16.7 s | 0 |

v0 was first scored at 6/15 (40%). After the E3 answer-key change
(see `golden_changes.md`) it re-scores at 5/15, because its E3 query counted
cancelled shipments. Every v1 run is scored against the updated key.

## Findings

1. **Definitions were the bottleneck.** Every v0 failure that was a definition error
   passed in v1. No change to the model was needed.
2. **A fix can expose an undecided definition.** In the first v1 run E3 "regressed":
   the copilot excluded cancelled shipments from the customs-hold rate. The domain
   owner decided that is the right definition for every shipment rate, so the answer
   key was updated and logged.
3. **Slow queries can freeze the tool.** During testing one H3 query ran with no end
   and could not be interrupted. With the 30 s timeout the same question timed out,
   retried with a more efficient query, and passed in 43 s.
4. **Cost rose ~40%** (larger prompt: glossary + examples), to about $0.0012 per question.

## Limits

- **Development score.** The glossary was written from these 15 questions' failures,
  so 100% overstates accuracy on new questions. Next: a held-out question set.
- **Small set.** One question is about 7 points.
- **Latency varies.** Same question: 10 s in one run, 43 s in another (timeout + retry).