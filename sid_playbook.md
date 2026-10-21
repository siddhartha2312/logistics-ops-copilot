# Sid's AI Build Playbook

Private checklist of lessons from building the Logistics Ops Copilot.
Use it two ways:
- **Before building anything similar:** run through every section as a checklist.
- **Before an interview:** each item is a "what I faced / what I did" story.

Add to it daily. Template for a new item:

```
### <Short title>  (Day N)
- What: <what happened or what the practice is>
- Why it matters: <the risk if you skip it>
- How: <the fix, code or rule>
- Interview line: <one sentence you'd say>
```

---

## 1. Observations (lessons learned)

### Fluency hides errors  (Day 4)
- What: the copilot's answers were fluent, confident and disclosed their
  assumptions, and were still wrong. On-time came out as 94% vs the true 88%
  (it divided by delivered shipments only), and "avoidable cost" was missing
  the ad-hoc premium. The same question gave different SQL on two days.
- Why it matters: a PM cannot tell a wrong answer from a right one by reading it.
- How: measure correctness with evals, repeatedly, against golden answers.
- Interview line: "Fluency hides errors, disclosure isn't correctness, and LLMs
  aren't deterministic, so correctness has to be measured repeatedly with evals."

---

## 2. Guardrails

### Secrets never in code  (Day 3)
- What: API keys live in a `.env` file, never in `.py` files, notebooks or chat.
- Why it matters: a leaked key on a public repo is found by bots within minutes
  and your credit is spent.
- How:
  - `.env` holds `ANTHROPIC_API_KEY=...`; code reads it with `load_dotenv()`.
  - `.env` is in `.gitignore`; confirm with `git check-ignore .env`.
  - Check `git status` before every push. If a key leaks, delete it in the
    console immediately and create a new one.
  - Set a monthly spend limit in the console.
- Interview line: "Config and secrets are separated from code; locally that's
  `.env`, in production a cloud secret store, with no code change."

### Read-only database for AI-written SQL  (Day 4)
- What: the copilot connects with `sqlite3.connect("file:logistics.db?mode=ro", uri=True)`.
- Why it matters: the prompt *asks* for SELECT only; that's a request, not a
  guarantee. A bug or prompt injection could produce `DELETE`.
- How: enforce it at the database level, so writing is impossible
  ("attempt to write a readonly database"). In real projects: a read-only DB user.
- Interview line: "Defence in depth: the prompt asks for read-only, the
  connection enforces it, and code rejects non-SELECT statements before they run."

### Retry once on SQL errors, then fail honestly  (Day 4)
- What: if the AI's SQL fails, send the SQL and the error back to the model and
  ask for a fix. One retry only.
- Why it matters: without it the tool crashes on small mistakes; without a
  limit it can loop and burn cost.
- How: `fix_sql()` builds a mini conversation (question → bad SQL → error →
  "fix it"). If the retry also fails, return "I couldn't answer this" instead
  of a crash or a made-up number.
- Interview line: "A bounded feedback loop: the model sees its own error once,
  and if it still fails the user gets an honest 'I can't answer' rather than a guess."

---

## 3. Data quality

### Give the AI clean data  (Day 3)
- What: if a category column has messy values, e.g.
  `shipments.status: ['Cancel', 'Cancelled', 'cancel', ...]`, the AI may filter
  on only one spelling and silently undercount.
- Why it matters: the query runs, returns a plausible number, and nobody notices.
- How, best first:
  1. Fix the data at the source.
  2. If you can't, give the AI a clean view and point it there:
     `CREATE VIEW shipments_clean AS SELECT ..., CASE WHEN LOWER(status) IN ('cancel','cancelled') THEN 'Cancelled' ... END AS status`
  3. Last resort: a prompt rule ("compare with LOWER(status)").
  4. Evals catch what slips through.
- Principle: don't make the LLM your data-cleaning layer. It's probabilistic,
  and data cleaning must be deterministic.
- Interview line: "In 'talk to your data' projects, messy data causes more
  wrong answers than the model does, so data profiling is the first deliverable."

---

## 4. Steps to improve UI / consumption

### Answer for the reader, not the analyst  (Day 4)
- What: a second LLM call with its own system prompt turns the result table
  into 2–4 plain sentences for an ops manager.
- Rules in that prompt and why:
  - Use only numbers in the result, never invent one (the most dangerous failure).
  - State the time period and filters used (e.g. "creation date, Jul–Sep 2026"),
    so the reader knows what was counted.
  - No SQL, table or column names (the PM cares about meaning).
  - Cap rows sent (50) to control cost and keep the answer readable.
- Output order: answer first → result table → SQL (for the DA team) → cost and time.
- Data privacy: result rows are sent to the LLM. Fine for aggregates; for
  personal or customer data, check with the client's security team first.
- Interview line: "Each LLM call gets one job and its own prompt; the answer
  call is constrained to the numbers it was given and must state its filters."

---

## 5. Checklist before shipping a similar tool

- [ ] Secrets in `.env` / secret store, ignored by Git, spend limit set
- [ ] Database connection is read-only
- [ ] Bounded retry on errors, honest failure message
- [ ] Data profiled: category values clean, or a clean view in place
- [ ] Answer prompt: only given numbers, filters stated, no jargon
- [ ] Evals on golden questions, run more than once