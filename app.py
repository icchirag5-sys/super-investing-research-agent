#!/usr/bin/env python3
"""Command-line interface for the research agent.

Example:
    python app.py SRVCABLE --pack research_pack --reference-date 2026-09-23
    python app.py SRVCABLE --dry-run          # no API call; shows what the model would receive
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE per line). Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Document-grounded research brief generator for an NSE stock.")
    p.add_argument("ticker", help="NSE ticker, e.g. SRVCABLE")
    p.add_argument("--pack", default=str(PROJECT_DIR / "research_pack"),
                   help="directory containing the source documents (default: ./research_pack)")
    p.add_argument("--reference-date", default="2026-09-23", help="as-of date, YYYY-MM-DD (default: 2026-09-23)")
    p.add_argument("--provider", choices=["gemini", "anthropic"], default=None,
                   help="model provider (default: gemini, or LLM_PROVIDER from .env)")
    p.add_argument("--model", default=None, help="model name override")
    p.add_argument("--design", type=int, choices=[1, 2, 3], default=3,
                   help="pipeline level used for experiments: 1 basic, 2 evidence, 3 full (default 3)")
    p.add_argument("--system-prompt", default=None, help="path to a system prompt file (default: system_prompt.md)")
    p.add_argument("--company", default=None, help="legal company name (default: inferred from the documents)")
    p.add_argument("--output-dir", default=str(PROJECT_DIR / "output"))
    p.add_argument("--output-stem", default=None, help="output file prefix (default: the ticker)")
    p.add_argument("--no-repair", action="store_true", help="skip the automatic repair pass (design 3)")
    p.add_argument("--dry-run", action="store_true", help="build the prompt and stop; no API call is made")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    args = parse_args(argv)

    # imported after .env is loaded so llm_client sees GEMINI_MODEL / ANTHROPIC_MODEL
    from research_agent import AgentError, DEFAULT_SYSTEM_PROMPT, RunConfig, run_agent, save_outputs
    from llm_client import LLMError

    try:
        ref = date.fromisoformat(args.reference_date)
    except ValueError:
        print(f"Error: --reference-date must be YYYY-MM-DD, got {args.reference_date!r}", file=sys.stderr)
        return 1

    provider = args.provider or os.environ.get("LLM_PROVIDER", "gemini")
    cfg = RunConfig(
        ticker=args.ticker.upper(), pack_dir=Path(args.pack), reference_date=ref, provider=provider,
        model=args.model, design=args.design,
        system_prompt_path=Path(args.system_prompt) if args.system_prompt else DEFAULT_SYSTEM_PROMPT,
        company_name=args.company, repair=not args.no_repair,
    )
    stem = args.output_stem or cfg.ticker

    try:
        res = run_agent(cfg, dry_run=args.dry_run)
    except (AgentError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    paths = save_outputs(res, Path(args.output_dir), stem)
    if args.dry_run:
        print(f"DRY RUN: no model call made. Documents loaded: {len(res.meta['documents'])}")
        print(f"Evidence pack ({len(res.evidence_pack)} chars) saved to: {paths['evidence']}")
        print(f"System prompt: {res.meta['system_prompt_file']} (sha256 {res.meta['system_prompt_sha256']})")
        if res.meta["excluded_after_reference_date"]:
            print("Excluded (after reference date):", ", ".join(res.meta["excluded_after_reference_date"]))
        return 0

    print(f"Brief saved to: {paths['brief']}")
    print(f"Run metadata:   {paths['meta']}")
    print(f"Model: {res.meta.get('model_used')}  |  design {cfg.design}  |  ~{res.meta['word_count_body']} words")
    if res.issues:
        print(f"\nAutomated checks: {res.meta['errors_final']} error(s), {res.meta['warnings_final']} warning(s)")
        for i in res.issues:
            print("  ", i)
    else:
        print("\nAutomated checks: no issues found.")
    return 2 if res.meta["errors_final"] else 0


if __name__ == "__main__":
    sys.exit(main())
