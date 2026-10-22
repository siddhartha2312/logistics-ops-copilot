# Held-out Results: v1 on Unseen Questions

**Date:** 22 Oct 2026 · model `claude-haiku-5-5` · copilot v1, unchanged.

The 10 held-out questions (`heldout_queries.sql`) were written by the domain owner
without the glossary in front of them, and were never used to write the glossary or
the worked examples. Two of them ask for data that does not exist, to test whether the
copilot says so. The answer key was committed before the run.

## Score

| Set | Score | Easy | Medium | Hard | Cost / question | Avg time |
|---|---|---|---|---|---|---|
| Dev (15) | 15 / 15 (100%) | 5 / 5 | 5 / 5 | 5 / 5 | $0.0012 | 7.2–8.2 s |
| **Held-out (10)** | **5 / 10 (50%)** | 2 / 3 | 2 / 5 | 1 / 2 | $0.0016 | 10.0 s |

First scored 5/10 with two judge errors that cancelled out (see `golden_changes.md`):
T9 was correct but failed, T6 was wrong but passed. Re-scored with the fixed judge,
no API calls.

## Failures

| ID | Question (short) | What the copilot did | Type |
|---|---|---|---|
| T6 | Trucks over their weight limit | No weight data exists. It swapped weight for pallet capacity and answered "no runs went over". | **No refusal** (silent substitute) |
| T3 | Node forecast vs actual | Forecasts aren't kept per node. It split each shipper's forecast by actual node share and returned 3,680 rows. The answer did say it was an allocation. | **No refusal** (disclosed substitute) |
| T4 | Nodes closed in IT, open in ES, Jul 2025 | Ignored the bank-holiday table and defined "closed" as "no truck runs all month". Concluded "no Italian nodes closed", the right answer for the wrong reason. | **No refusal** + DEF |
| T1 | Volume flat vs last year, week 20 | Counted week 1 as the week containing 1 Jan, so week 20 = 10–16 May (key: 17–23 May). | DATE (week numbers undefined) |
| T8 | Daily gap > 200 packages, 2026 | Used only days with a forecast, so it missed 2 days of unforecast volume (122 vs 124). | DEF (unforecast days) |

## Findings

1. **The biggest gap is honesty, not SQL.** 3 of 5 failures came from questions the data
   can't fully answer. The prompt says "reply with only the SQL", so the copilot always
   finds a substitute. T6 is the dangerous one: "no trucks were overweight" reads as
   good news, but there is no weight data at all.
2. **The other 2 are undefined terms.** "Week 20" and "any day" had no agreed definition.
   Both readings the copilot chose are defensible; the glossary is incomplete.
3. **The definitions that exist held up.** Volume, cancelled exclusion, pickup date,
   Sunday–Saturday weeks and the Liverpool node were all applied correctly.
4. **The answer step sees only the first 50 rows.** Several answers say "only the first
   50 of N are shown". For list questions the user needs the full table or a download.
5. **Judge errors go both ways.** One false fail, one false pass, net zero. Without
   checking each result, the score would have looked right for the wrong reasons.

## Next (v2)

| Change | Targets | Note |
|---|---|---|
| Allow "cannot answer": name the missing data instead of writing SQL | T3, T4, T6 | Must not make it refuse answerable questions; re-run dev to check |
| Answer states any substitute it used ("used pallet capacity, no weight data") | Trust | |
| Glossary: week-number rule, gap definition | T1, T8 | Adding these turns T1 and T8 into dev questions; a fresh held-out set is needed afterwards |

## Limits

- 10 questions: one question is 10 points.
- One run. Dev results were stable over 3 runs; held-out stability not yet checked.