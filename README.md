# Super Investing Research Agent

A small, document-grounded AI research agent. Give it an **NSE ticker** and a folder of **company documents**
and it writes a one-page **Markdown research brief** (Snapshot, Bull case, Bear case, Open questions, Sources)
for a retail investor, with a citation on every material claim.

It was built for the Super Investing AI Innovator assignment (test company: Sarvottam Cables Ltd, `SRVCABLE`,
reference date 23 September 2026).

> **Not investment advice.** The agent never gives buy/sell recommendations or price targets.

## Design in one paragraph

An LLM is good at reading and writing, but bad at bookkeeping and easy to mislead. So the workflow splits the job:
plain Python handles the mechanical, checkable parts (reading files, tracking dates, flagging untrustworthy sources,
recomputing numbers, checking citations, writing the Sources list), and the LLM does only the part that needs
language skill: reading the evidence and writing the brief. Everything the model produces is then **verified by code**.

## Architecture and data flow

```
research_pack/*.md|txt|pdf
        │
        ▼
 document_loader.py ── parse metadata (source, url, date) ── split into citable chunks  [S2.3]
        │
        ▼
 evidence_extractor.py ── drop documents after the reference date
        │                 flag: stale / promotional / wrong company / hidden AI instructions
        │                 quarantine injected instructions
        │                 recompute table growth rates; list possible cross-source conflicts
        │                 find the latest reported period (not just the newest document)
        ▼
   evidence pack (text) ──┐
                          ├──► llm_client.py ──► Gemini or Anthropic model
   system_prompt.md  ─────┘            │
                                       ▼
                           draft brief (sections 1-4, inline [S2.3] citations)
                                       │
                                       ▼
 citation_validator.py ── every citation exists? every number in the cited chunk? quotes exact?
        │                 no buy/sell language? no promo claims stated as fact? no wrong-company evidence?
        │            errors found? → ONE repair pass (model gets the list of problems)
        ▼
 Sources section generated FROM THE FILES (titles, URLs, dates cannot be invented)
        ▼
 output/SRVCABLE_research_brief.md  (+ _run_meta.json, _evidence_pack.txt)
```

| File | Role |
|---|---|
| `app.py` | Command-line interface and `.env` loading |
| `research_agent.py` | Orchestrates the workflow |
| `document_loader.py` | Reads `.md`, `.txt`, `.pdf`; metadata; chunking with section/page labels |
| `evidence_extractor.py` | Source flags, injection quarantine, arithmetic checks, conflict candidates |
| `citation_validator.py` | Verifies the model's output; generates the Sources section |
| `llm_client.py` | Gemini and Anthropic REST calls (standard library only) |
| `system_prompt.md` | The instructions sent to the model on every run |
| `run_experiments.py` | Runs the three-design experiment and records measured results |
| `experiments/` | The two simpler prompts used as baselines (runs 1 and 2) |
| `tests/` | Automated tests (no network, no API key needed) |
| `logs/test_log.md` | Honest record of what was and was not tested |

### Why not a framework (LangChain etc.) or a vector database?

Eight short documents fit comfortably in the model's context window, so the whole evidence pack is sent every time.
There is no retrieval step to get wrong. A framework would add moving parts without improving accuracy.
(With hundreds of documents you would need retrieval; see Limitations.)

## Model choice and availability

| Provider | Default model | Cost | Needs |
|---|---|---|---|
| **Gemini** (default) | `gemini-2.5-flash` (set `GEMINI_MODEL` to change) | Free tier exists | Free key from [Google AI Studio](https://aistudio.google.com/apikey), no payment card |
| Anthropic (optional) | `claude-sonnet-5-5` (set `ANTHROPIC_MODEL`) | Paid | API key from the Anthropic Console |

Why Gemini by default: it has a free tier, so you can run everything without paying.

Free-tier caveats, which you should expect:
- Google's free tier is **rate-limited**, and which models are free and the exact limits change over time and are
  shown in your AI Studio console, not fixed in this README. If you see `model not found` or a quota error,
  pick a model your console lists as available and set `GEMINI_MODEL` in `.env`.
- Per Google's terms for the free tier, **content you send may be used to improve Google's products**
  (see Privacy below).

## Prerequisites

- macOS with **Python 3.10 or newer** (check: `python3 --version`; install from python.org or `brew install python`). The tests were run on Python 3.12.
- A Gemini API key (free) or an Anthropic API key
- Internet access to the model API (not needed for tests or `--dry-run`)

## Installation (macOS)

```bash
cd super-investing-research-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
open -e .env          # paste your key after GEMINI_API_KEY= then save
```

`.env` is in `.gitignore`, so it is never committed. You can also set the key in the shell instead:
`export GEMINI_API_KEY=your_key`.

## Supplying the research documents

Copy every document file into `research_pack/` (one file per document). Each file must begin with a metadata
header giving `source`, `url` and `published` (YYYY-MM-DD). See `research_pack/README.md` for the exact format.
PDFs also work if you add a sidecar `name.meta.txt` with the same three fields. The folder is empty in the
repository and its contents are ignored by git unless you change `.gitignore`.

## Running the agent

First check that your documents load. This needs **no API key** and makes **no model call**:

```bash
python3 app.py SRVCABLE --dry-run
```

Then generate the brief:

```bash
python3 app.py SRVCABLE --pack research_pack --reference-date 2026-09-23
```

Output (in `output/`):
- `SRVCABLE_research_brief.md`: the brief
- `SRVCABLE_run_meta.json`: model used, token counts, prompt hash, validator results
- `SRVCABLE_evidence_pack.txt`: exactly what the model was shown

The program prints the automated check results. Exit code: `0` clean, `1` input/credential error,
`2` the brief was saved but the validator still reports errors (read them before using the brief).

Useful options: `--provider anthropic`, `--model NAME`, `--system-prompt PATH`, `--no-repair`,
`--design 1|2|3` (experiment levels; 3 is the full pipeline and the default), `--output-dir`, `--company`.

## Running the tests

```bash
python3 -m pytest
```

All tests run offline with a fake model. Tests that use the real research pack are skipped automatically if
`research_pack/` has no documents.

## The three-run experiment

```bash
python3 run_experiments.py SRVCABLE --pack research_pack --reference-date 2026-09-23
```

This runs designs 1, 2 and 3 against the real pack and writes `logs/experiment_results.md` and `logs/runs/`.
All figures in that file are measured by the script. Then read the three briefs and record your own observations in
`logs/test_log.md`. The free tier may need the default 20-second pause between runs (`--sleep`).

| Run | What changes |
|---|---|
| 1 | Basic prompt, raw text, document-level citations, no pre-checks |
| 2 | Chunk-level citation IDs, explicit citation rules, Sources generated from files |
| 3 | Full system prompt, source flags, entity/date/conflict checks, injection quarantine, validator + repair |

## How the evidence rules are enforced

| Rule | Enforced by |
|---|---|
| Every claim cited with a stable ID | Prompt + validator (`UNCITED_NUMBER`, `UNKNOWN_CHUNK`) |
| Don't cite a source that doesn't say it | Validator checks each number and quote against the cited chunk |
| Sources list can't be fabricated | Generated by code from the files' own metadata |
| Respect the reference date | Documents after it are excluded before the model sees them |
| Publication date ≠ reporting period | Latest period found from "Qn FYyy results" in primary documents |
| Management claims ≠ facts | Prompt labels (*Reported / Management says / Our read / Unknown*) |
| Don't trust promotional or hostile sources | Source tiers, flags, and quarantine of embedded AI instructions |
| Don't confuse similarly named companies | Entity-mismatch flag; validator blocks it as evidence |
| No recommendations or invented targets | Prompt + validator (`RECOMMENDATION`, `PROMO_CLAIM_UNATTRIBUTED`) |

## Limitations and known failure modes

- **The validator checks numbers, quotes, IDs and rules, not meaning.** A claim with the right number but the wrong
  interpretation can still pass. A human must read the brief.
- **Heuristics are tuned to this style of document.** The latest-period finder looks for phrases like "Q1 FY27 results";
  the conflict finder only knows two topics (revenue growth, promoter pledge); the wrong-company detector compares the
  first six letters of the company's name. Other documents may need these extended.
- **No OCR.** Scanned PDFs are rejected with an error.
- **Whole-pack prompting.** Fine for ~8 short documents; for many or long documents you would add retrieval/chunk selection.
- **Model variability.** Output can differ between runs even at low temperature; free-tier models may be changed or limited.
- **The one-page length is approximate** (target ~450-550 words); the validator only warns above 650.
- **Designs 1 and 2 are deliberately unprotected** (they exist to show the effect of each improvement). Only design 3 quarantines injected instructions.
- Documents are assumed to be genuine scraper output. The agent cannot verify that a "filing" is authentic.

## Privacy and cost

- The full text of every document in `research_pack/` is sent to the model provider on each run.
  Do not put confidential or personal documents in it.
- Gemini's free tier may use submitted content to improve Google products; paid tiers have different terms. Check the current terms.
- Cost: free on Gemini's free tier. On paid plans, one run sends roughly 5 thousand input tokens (estimated from text length: system prompt + evidence pack are about 19,000 characters) and receives under a thousand
  output tokens (a second call happens only if the validator finds errors). That is a very small cost, but check current prices.
- API keys live only in `.env` / environment variables; `.env` is git-ignored and no key appears in the code
  (a test checks this).
