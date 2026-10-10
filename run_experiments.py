#!/usr/bin/env python3
"""Run the three-design experiment on the real research pack and record what actually happened.

    python run_experiments.py SRVCABLE --pack research_pack --reference-date 2026-09-23

For each run this saves, under logs/runs/:
    runN_brief.md       the brief produced
    runN_meta.json      model, token counts, prompt hash, validator output
    runN_evidence.txt   the exact evidence pack the model saw
and writes logs/experiment_results.md: a table of MEASURED results plus the briefs.

Nothing in the results file is typed in by hand. Observations about WHY a run improved or failed
are for you to add to logs/test_log.md after reading the briefs.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import app
from citation_validator import split_sections
from document_loader import load_research_pack
from evidence_extractor import analyse
from llm_client import LLMError
from research_agent import AgentError, RunConfig, run_agent, save_outputs

PROJECT_DIR = Path(__file__).resolve().parent

RUNS = [
    (1, PROJECT_DIR / "experiments" / "system_prompt_v1_basic.md",
     "Baseline: basic summarisation prompt, raw documents, document-level citations, no pre-checks, no validation repair"),
    (2, PROJECT_DIR / "experiments" / "system_prompt_v2_evidence.md",
     "Chunk-level evidence with section labels, strict citation rules, generated Sources section"),
    (3, PROJECT_DIR / "system_prompt.md",
     "Full design: full system prompt, source-credibility flags, entity/date/conflict checks, injection quarantine, "
     "arithmetic checks, validator with one repair pass"),
]


def behaviour_checks(brief: str, analysis) -> dict:
    """Mechanical, ticker-independent observations (not judgements of quality)."""
    body = "\n".join(b for t, b in split_sections(brief).items() if not t.lower().startswith("source"))
    surfaced = []
    for c in analysis.conflicts:
        a, b = f"{c.a[2]:g}", f"{c.b[2]:g}"
        surfaced.append({"topic": c.topic, "values": f"{a} vs {b}",
                          "both_values_in_brief": bool(re.search(rf"\b{re.escape(a)}\b", body)
                                                       and re.search(rf"\b{re.escape(b)}\b", body))})
    return {
        "latest_period_named": bool(analysis.latest_period and analysis.latest_period in body),
        "conflict_values_both_mentioned": surfaced,
        "mentions_quarantine_or_hidden_instruction": bool(re.search(r"hidden instruction|instructions? (aimed|addressed|directed)|embedded instruction", body, re.I)),
    }


def main() -> int:
    app.load_dotenv(PROJECT_DIR / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticker")
    ap.add_argument("--pack", default=str(PROJECT_DIR / "research_pack"))
    ap.add_argument("--reference-date", default="2026-09-23")
    ap.add_argument("--provider", choices=["gemini", "anthropic"], default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--sleep", type=int, default=20, help="seconds to wait between runs (free-tier rate limits)")
    args = ap.parse_args()

    import os
    provider = args.provider or os.environ.get("LLM_PROVIDER", "gemini")
    ref = date.fromisoformat(args.reference_date)
    out_dir = PROJECT_DIR / "logs" / "runs"
    rows, sections = [], []

    for n, prompt_path, description in RUNS:
        print(f"\n=== Run {n}: {description}")
        cfg = RunConfig(args.ticker.upper(), Path(args.pack), ref, provider, args.model, design=n,
                        system_prompt_path=prompt_path)
        try:
            res = run_agent(cfg)
        except (AgentError, LLMError) as e:
            print(f"Run {n} failed: {e}", file=sys.stderr)
            print("Stopping: no results are recorded for runs that did not execute.", file=sys.stderr)
            return 1
        save_outputs(res, out_dir, f"run{n}")
        # rename to the documented file names
        (out_dir / f"run{n}_research_brief.md").replace(out_dir / f"run{n}_brief.md")
        (out_dir / f"run{n}_evidence_pack.txt").replace(out_dir / f"run{n}_evidence.txt")
        (out_dir / f"run{n}_run_meta.json").replace(out_dir / f"run{n}_meta.json")

        usable, analysis = analyse(load_research_pack(args.pack), args.ticker.upper(), ref)
        codes = Counter(i.code for i in res.issues if i.severity == "error")
        wcodes = Counter(i.code for i in res.issues if i.severity == "warning")
        checks = behaviour_checks(res.brief, analysis)
        rows.append((n, res, codes, wcodes, checks, description))
        print(f"  model={res.meta.get('model_used')} words~{res.meta['word_count_body']} "
              f"errors={res.meta['errors_final']} warnings={res.meta['warnings_final']} "
              f"repair={'yes' if res.meta.get('repair_attempted') else 'no'}")
        if n != RUNS[-1][0]:
            time.sleep(args.sleep)

    lines = [f"# Experiment results (auto-generated {datetime.now().isoformat(timespec='seconds')})", "",
             f"Ticker {args.ticker.upper()} | reference date {ref.isoformat()} | provider {provider}. "
             "All numbers below were measured by this script from real model outputs.", "",
             "| Run | Prompt file | Model | Words | Errors | Warnings | Repair pass | Tokens in/out (all calls) |",
             "|---|---|---|---|---|---|---|---|"]
    for n, res, codes, wcodes, checks, desc in rows:
        tin = sum(t["in"] or 0 for t in res.meta["tokens"])
        tout = sum(t["out"] or 0 for t in res.meta["tokens"])
        lines.append(f"| {n} | {res.meta['system_prompt_file']} | {res.meta.get('model_used')} | "
                     f"{res.meta['word_count_body']} | {res.meta['errors_final']} | {res.meta['warnings_final']} | "
                     f"{'yes' if res.meta.get('repair_attempted') else 'no'} | {tin}/{tout} |")
    for n, res, codes, wcodes, checks, desc in rows:
        lines += ["", f"## Run {n}", f"**Design:** {desc}", "",
                  f"**Validator errors:** {dict(codes) or 'none'}", f"**Validator warnings:** {dict(wcodes) or 'none'}",
                  f"**Latest period named in brief:** {checks['latest_period_named']}",
                  f"**Hidden-instruction source mentioned in brief:** {checks['mentions_quarantine_or_hidden_instruction']}",
                  "**Candidate conflicts: both figures appear in brief:** " +
                  (", ".join(f"{c['topic']} ({c['values']}): {c['both_values_in_brief']}"
                             for c in checks["conflict_values_both_mentioned"]) or "n/a")]
        if res.meta.get("issues_before_repair"):
            lines += ["", "**Issues found in the first draft (before the repair pass):**"] + \
                     [f"- {x}" for x in res.meta["issues_before_repair"]]
        lines += ["", "**Final issue list:**"] + ([f"- {x}" for x in res.meta["issues_final"]] or ["- none"])
        lines += ["", "<details><summary>Brief produced</summary>", "", res.brief, "", "</details>"]
    (PROJECT_DIR / "logs" / "experiment_results.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nWrote logs/experiment_results.md and logs/runs/. Read the briefs, then add your observations to logs/test_log.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
