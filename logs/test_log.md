# Test log

This log separates **what was actually executed** from **what is still to be done**.
Nothing here is estimated or invented. If a section says NOT RUN, it was not run.

---

## Part A. Checks executed during development (real)

Environment: Linux sandbox, Python 3.12.3, pytest 9.1.1, pypdf 5.9.0. No model API key was available and the
Gemini API was not reachable from that sandbox, so **no LLM call was made** in Part A.

### A1. Research pack inspection (real)

The uploaded research pack contained **7 source documents** (the assignment text mentions eight; no eighth document
or README came in the zip files). All 7 had a complete metadata header (source, url, published, type).

| ID | File | Published | Type |
|---|---|---|---|
| S1 | `ir_concall_2026-08-11.md` | 2026-08-11 | official company transcript |
| S2 | `ir_press_release_2026-08-08.md` | 2026-08-08 | official company filing |
| S3 | `marketwatchindia_2024-03-18.md` | 2024-03-18 | news article |
| S4 | `multibaggeralerts_2026-08-12.md` | 2026-08-12 | blog post |
| S5 | `nagpurcitytimes_2026-08-20.md` | 2026-08-20 | news article |
| S6 | `nse_announcement_2026-09-02.md` | 2026-09-02 | official exchange filing |
| S7 | `nse_shareholding_2026-07-15.md` | 2026-07-15 | official exchange filing |

All 7 are dated on or before the 23 September 2026 reference date. Pre-processing output on the real pack:
- latest reported period: **Q1 FY27** (S1, S2)
- S3: flagged **STALE** (919 days before reference date)
- S4: flagged **PROMOTIONAL** and **PROMPT_INJECTION** (hidden instructions aimed at AI tools in an HTML comment; chunk S4.4 quarantined)
- S5: flagged **ENTITY_MISMATCH** (refers to "Sarvottam Cable Network", a local operator; never names the company or ticker)
- Table recomputation on S2: revenue +18.0% consistent; EBITDA +2.6% and PAT +5.9% differ from recomputed 2.9% and 6.5% but lie within rounding of the displayed ₹ crore figures; margin change −170 bps consistent
- Possible conflicts listed: revenue growth 35% (S4.1) vs 18.0% (S2.2), close in time; promoter pledge 35% (S3.1, 2024) vs 4.1% (S7.1, 2026), far apart in time

### A2. Automated tests (real)

Command: `python3 -m pytest -q`  →  **55 passed** (with the research pack present).
On a clean copy with a fresh virtual environment, `pip install -r requirements.txt` then `python -m pytest`  →  **53 passed, 2 skipped**
(the 2 skipped tests need the real pack, which is not in the repository).

Coverage: metadata parsing and its error messages; stable IDs and chunking (bullets, speaker turns, table labels);
PDF parsing with page numbers and sidecar metadata; reference-date exclusion; stale/promotional/injection/entity flags;
injection quarantine; table arithmetic (consistent, within rounding, inconsistent); conflict candidates;
latest-period detection ignoring future mentions; citation integrity (unknown source/chunk, uncited numbers, numbers not in
the cited chunk, derived numbers, quote mismatch, recommendation language, laundered promotional claims, wrong-entity evidence,
stale-source dating); generated Sources section; proof that `system_prompt.md` is sent to the model; repair pass logic;
missing-key, missing-pack and bad-date errors; no hardcoded secrets.
All model calls in tests use a fake function. Test data is synthetic ("Examplecorp"). Two tests run on the real pack (skipped if it is absent): one checks loading and the expected red flags; the other uses a
**hand-written** fixture (`tests/fixtures/hand_written_validator_sample.md`, **not model output**) to confirm the validator
accepts a correct brief and rejects four kinds of tampering.

### A3. Command-line behaviour (real)

| Command | Result |
|---|---|
| `python3 app.py SRVCABLE --dry-run` | Loaded 7 documents, wrote the evidence pack, exit 0 |
| `python3 app.py SRVCABLE` with no `GEMINI_API_KEY` | Clear message with link to create a key, exit 1 |
| `python3 app.py SRVCABLE --pack /nonexistent --dry-run` | "Research-pack directory not found ...", exit 1 |
| `python3 app.py SRVCABLE --reference-date 23-09-2026 --dry-run` | Date-format error, exit 1 |
| `python3 run_experiments.py SRVCABLE` with no key | Stops at run 1 with the key message; writes no results |

The experiment runner's file handling and report generation were also exercised once in a temporary copy with a stand-in model
(plumbing test only). Those outputs were discarded and are **not** experiment results.

### A4. Bugs found by running the code (real) and fixed

1. Latest-period detection returned **Q3 FY27**, which is a forward-looking plant start date, not a results period. Fixed: only
   "Qn FYyy results / earnings / conference call" counts. Now returns Q1 FY27.
2. The arithmetic check treated the shareholding table (a time series) as growth columns and printed false "INCONSISTENT" verdicts.
   Fixed: only tables whose last header is a change column (YoY, QoQ, change, growth) are checked.
3. The wrong-company detector missed a similarly named company unless the first word matched exactly (found by a test). Fixed: compares a
   6-letter stem.
4. A bullet-list/sub-title chunking issue labelled unrelated paragraphs "Consolidated highlights". Fixed: a bold sub-title labels only the next block;
   bullets become one chunk each.
5. The validator flagged my own hand-written sample for saying "quarter ended 30 June 2026" while citing only the results table
   (that date is in a different chunk). That was a correct catch; the sample was fixed.

---

## Part B. Three-run experiment on the real pack

**STATUS: NOT RUN.**

Reason: the build environment had no model API key and could not reach the Gemini API, so no real model output exists yet.
No run results, excerpts, scores or "improvements" are reported here because none have been measured.

### How to complete it (about 5 minutes)

```bash
python3 run_experiments.py SRVCABLE --pack research_pack --reference-date 2026-09-23
```

This writes `logs/experiment_results.md` (measured tables and the three briefs) and `logs/runs/`.
Then fill in the sections below **from what you actually see**. Do not edit the measured numbers.

### Run 1: basic summarisation with citations
- Design: `experiments/system_prompt_v1_basic.md`, raw text, document-level `[S1]` citations, no pre-checks.
- Measured result: _(paste from `logs/experiment_results.md`)_
- Representative excerpt: _(paste a few lines from `logs/runs/run1_brief.md`)_
- What went wrong: _(your observation, e.g. any uncited number, any use of the blog or the Nagpur article, any restated promotional claim)_
- Change for next run: _(…)_
- Grounding / citation quality: _(better / same / worse, with evidence)_

### Run 2: improved evidence extraction and citation requirements
- Design: `experiments/system_prompt_v2_evidence.md`, chunk-level `[S2.2]` citations, section labels, generated Sources section.
- Measured result: _(…)_
- Representative excerpt: _(…)_
- What went wrong: _(e.g. were conflicts surfaced? was the wrong-entity article used? did the 35% vs 18.0% disagreement appear?)_
- Change for next run: _(…)_
- Grounding / citation quality: _(…)_

### Run 3: conflict detection, date awareness, facts vs interpretation
- Design: `system_prompt.md` + source flags + entity/date/conflict/arithmetic checks + injection quarantine + validator and repair.
- Measured result: _(…)_
- Representative excerpt: _(…)_
- What went wrong: _(anything still wrong; the validator does not check meaning)_
- Grounding / citation quality: _(…)_

### Final deliverable
`output/SRVCABLE_research_brief.md`: **NOT GENERATED YET.** Generate it with:

```bash
python3 app.py SRVCABLE --pack research_pack --reference-date 2026-09-23
```

If you edit the generated brief by hand, list every edit here:

| Edit | Reason |
|---|---|
| _(none yet)_ | |
