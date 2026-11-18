"""Runs on disk. Each run gets its own folder and nothing is ever overwritten:

    data/runs/2026-11-17/20261118T070001-agentic-live/
        report.md      the digest
        run.json       everything needed to review it (RunRecord)
        snapshot.json  every page read, so the run can be replayed

Memory comes from the latest successful agentic live run of each of the last HISTORY_DAYS days:
the items those digests published, and the links they rejected on their content.
A failed run is saved too, but never replaces a good one.
"""

import json
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

from ai_newsletter.config import HISTORY_DAYS
from ai_newsletter.models import HistoryItem, Rejection, RunRecord
from ai_newsletter.web import Page


def save(data_dir: Path, record: RunRecord, pages: dict[str, Page]) -> Path:
    folder = data_dir / "runs" / str(record.day) / f"{record.started_at:%Y%m%dT%H%M%S}-{record.variant}-{record.mode}"
    folder.mkdir(parents=True)
    (folder / "report.md").write_text(record.report)
    (folder / "run.json").write_text(record.model_dump_json(indent=2))
    snapshot = {url: page.model_dump(mode="json") for url, page in pages.items()}
    (folder / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False))
    return folder


def load_snapshot(run_folder: Path) -> dict[str, Page]:
    data = json.loads((run_folder / "snapshot.json").read_text())
    return {url: Page.model_validate(page) for url, page in data.items()}


def load_history(data_dir: Path, before: date) -> list[HistoryItem]:
    """Items published by earlier digests."""
    return [
        HistoryItem(
            day=record.day, title=event.verdict.title, source_url=event.verdict.source_url, kind=event.verdict.kind
        )
        for record in _earlier_runs(data_dir, before)
        for event in record.events
        if event.selected and event.verdict
    ]


def load_rejections(data_dir: Path, before: date) -> dict[str, Rejection]:
    """Links rejected by earlier runs, by URL; the most recent decision wins."""
    return {rejection.url: rejection for record in _earlier_runs(data_dir, before) for rejection in record.rejected}


def _earlier_runs(data_dir: Path, before: date) -> Iterator[RunRecord]:
    for offset in range(HISTORY_DAYS, 0, -1):
        record = _latest_good_live_run(data_dir / "runs" / str(before - timedelta(days=offset)))
        if record:
            yield record


def _latest_good_live_run(day_folder: Path) -> RunRecord | None:
    for run_json in sorted(day_folder.glob("*-agentic-live/run.json"), reverse=True):
        try:
            record = RunRecord.model_validate_json(run_json.read_text())
        except ValueError:  # unreadable or from an older version of the app: skip it, don't block every run
            continue
        if record.status != "failed":
            return record
    return None
