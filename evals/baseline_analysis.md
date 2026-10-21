# Baseline Eval: Copilot v0

**Run:** 21 Oct 2026 · model `claude-haiku-5-5` · report `evals/results/eval_20261021_1217.csv`
**Copilot version:** schema + allowed category values in the prompt; **no business definitions**.

## Score

| | Passed |
|---|---|
| **Overall** | **6 / 15 (40%)** |
| Easy | 5 / 5 |
| Medium | 1 / 5 |
| Hard | 0 / 5 |

- Cost: $0.013 for the run, $0.0009 per question
- Time: 6.6 s average, 18.0 s slowest (H4)
- 1 question needed the SQL-error retry

**Reading:** the copilot handles lookups and simple counts, but fails anything that
needs a business definition.

## How correctness is judged

The copilot's result table is compared with the golden answer (`evals/compare.py`).
Each golden question lists the columns that *are* the answer (`-- Check:` in
`golden_queries.sql`). A question passes if those values appear in the copilot's
result, regardless of column names, column order, row order, rounding, or
percent vs fraction. Comparing SQL text is not used: different SQL can be equally correct.

## Failure analysis

Each failing query was re-run on the same data to find the exact cause.

| ID | Type | What went wrong | Business impact |
|---|---|---|---|
| M1 | DEF | On-time divided by delivered shipments only (94% vs 88%). Cost per package left out wasted trucks and counted cancelled packages. | Direct runs look more reliable and cheaper than they are |
| M2 | DATE + DEF | Actuals by created date instead of pickup date; Monday weeks instead of Sun–Sat; partial first/last weeks; unplanned volume included | A false 91% "drop" in the final (half) week |
| M3 | DATE (near-miss) | Created date instead of pickup date. 9 of 10 shippers correct; attainment off by about 1 point | Nearly the same conclusion |
| M5 | DEF | Average of per-truck ratios (64–65%) instead of total loaded ÷ total capacity (71%) | Utilisation understated by ~6 points; country ranking changes |
| H1 | FILTER + DEF | Peak taken as Oct–Dec instead of Black Friday–Christmas Eve; load measured by delivered pallets (after rollovers) instead of arrivals. Right node, 6 days vs 19 | Bottleneck looks 3× smaller than it was |
| H2 | DEF | Avoidable cost = wasted trucks only; ad-hoc premium missing. Top 3 correct | Totals 4–8% low |
| H3 | AMBIG (near-miss) | Correct logic, but "volume" reported in pallets instead of packages. In packages it matches golden exactly | Unit ambiguity only |
| H4 | DATE + DEF + TECH | Monday weeks, created date, weeks without forecast counted as misses: 873 shippers vs 268. First reply cut off at max_tokens | List 3× too long |
| H5 | JOIN | Joined late arrivals to shipments, but all late-arrival exceptions are run-level (`shipment_id` empty), so 0 rows returned | "No shipper causes late milkruns": confidently wrong |

Type key: **DEF** wrong business definition · **DATE** wrong date column or period ·
**FILTER** wrong filter · **JOIN** wrong join path · **AMBIG** ambiguous question ·
**TECH** technical failure. Judge errors (copilot right, judge wrong): **none found**.

## Patterns

| Cause | Failures | Planned fix (week 2) |
|---|---|---|
| Business definitions | 7 of 9 | Glossary in the system prompt, then a semantic layer (SQL views) |
| Date logic | 3 | Glossary + a worked example of Sun–Sat full weeks on pickup date |
| Schema knowledge | 1 | Notes on which exception types are run-level |
| Ambiguous units | 1 | Default unit for "volume" = packages |
| Output cut off | 1 | Raise max_tokens |

## Key findings

1. **The model writes valid SQL; it doesn't know the business.** Most failures ran
   without error and returned plausible numbers built on a different definition.
2. **Empty results are the most dangerous failure.** H5 returned nothing, which reads
   as "no problem" rather than "wrong query".
3. **Results are not stable.** M1's cost per package was correct in a manual test on
   20 Oct and wrong in this run, with no code change. Evals must be re-run, not run once.

## Limits of this eval (v1)

- 15 questions; expand to ~50 in week 3
- A wrong query could match the golden numbers by coincidence
- "Top N" questions accept a longer list, so ranking cut-offs are not checked
- Each question was run once; repeat runs are needed to measure consistency