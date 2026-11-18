"""Command line: `ai-newsletter [--day 2026-11-17] [--replay RUN_FOLDER] [--single-pass]`."""

import argparse
import asyncio
from datetime import date
from pathlib import Path

from ai_newsletter import days
from ai_newsletter.models import RunRecord
from ai_newsletter.pipeline import run_day


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a verified digest of practical AI news for one day.")
    parser.add_argument("--day", type=date.fromisoformat, help="target day in Europe/Prague (default: yesterday)")
    parser.add_argument("--replay", type=Path, metavar="RUN_FOLDER", help="use the pages saved by an earlier run")
    parser.add_argument("--single-pass", action="store_true", help="baseline: the model may not read extra pages")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="where runs are saved (default: data)")
    args = parser.parse_args()

    day = args.day or days.yesterday()
    folder = asyncio.run(run_day(day, args.data_dir, replay_from=args.replay, agentic=not args.single_pass))
    record = RunRecord.model_validate_json((folder / "run.json").read_text())
    print(record.report)
    print(f"Status: {record.status}. Cost: ${record.usage.cost_usd:.4f}. Saved in {folder}")
    raise SystemExit(1 if record.status == "failed" else 0)
