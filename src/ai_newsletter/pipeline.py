"""One run for one day, start to finish. Read this file first: it is the whole flow.

    collect (code) -> triage (model) -> verify each event (model + read tool) -> select (code)
    -> render the report (code) -> save the run (code)

The run always ends with a truthful status:
    complete  every source was read and every chosen event verified
    partial   the report exists, but a source or a verification is missing (the report says which)
    failed    no usable result; the report says so and history keeps the last good run
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic_ai.exceptions import AgentRunError, UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

from ai_newsletter import days, report, store
from ai_newsletter.agents import FETCH_TOOL, VerifyDeps, triage_agent, triage_prompt, verifier, verify_prompt
from ai_newsletter.config import MAX_EVENTS_TO_VERIFY, MAX_ITEMS, MODEL, RUN_COST_LIMIT_USD
from ai_newsletter.models import Candidate, EventPlan, EventResult, HistoryItem, RunRecord, Usage
from ai_newsletter.sources import collect
from ai_newsletter.web import Web

PREFETCH_PER_EVENT = 3  # the event's own links, read before the model starts
LIMITS = UsageLimits(cost_limit=Decimal(str(RUN_COST_LIMIT_USD)), request_limit=None)  # for the whole run


class RunFailed(Exception):
    pass


async def run_day(day: date, data_dir: Path, replay_from: Path | None = None, agentic: bool = True) -> Path:
    """Run the whole pipeline for `day` and return the folder with report.md and run.json.

    replay_from: a previous run folder; its saved pages are used instead of the live web.
    agentic: False gives the single-pass baseline, which may not read any extra page.
    """
    web = Web(store.load_snapshot(replay_from) if replay_from else None, live=replay_from is None)
    start, end = days.window(day)
    record = RunRecord(
        day=day,
        window_start=start,
        window_end=end,
        started_at=datetime.now(UTC),
        mode="replay" if replay_from else "live",
        variant="agentic" if agentic else "single_pass",
        model=MODEL,
    )
    usage = RunUsage()
    try:
        await _run(record, web, store.load_history(data_dir, day), usage, agentic)
        problems = any(not c.ok for c in record.coverage) or any(e.error for e in record.events)
        record.status = "partial" if problems else "complete"
    except (RunFailed, AgentRunError) as error:
        record.status = "failed"
        record.errors.append(f"{type(error).__name__}: {error}")
    record.finished_at = datetime.now(UTC)
    record.usage = Usage(
        requests=usage.requests,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost or Decimal(0),
    )
    record.report = report.render(record)
    return store.save(data_dir, record, web.pages)


async def _run(record: RunRecord, web: Web, history: list[HistoryItem], usage: RunUsage, agentic: bool) -> None:
    record.candidates, record.coverage = await collect(web, record.day)
    if not any(source.ok for source in record.coverage):
        raise RunFailed("no source could be read")
    web.allow_hosts_of([candidate.url for candidate in record.candidates])

    if not record.candidates:
        return
    by_id = {candidate.id: candidate for candidate in record.candidates}
    triage = await triage_agent.run(
        triage_prompt(record.day, record.candidates, history), deps=set(by_id), usage=usage, usage_limits=LIMITS
    )
    record.skipped = triage.output.skipped

    for plan in triage.output.events[:MAX_EVENTS_TO_VERIFY]:
        candidates = [by_id[id] for id in plan.candidate_ids]
        record.events.append(await verify_event(plan, candidates, record.day, web, history, usage, agentic))
    select(record.events, record.day, history)


async def verify_event(
    plan: EventPlan,
    candidates: list[Candidate],
    day: date,
    web: Web,
    history: list[HistoryItem],
    usage: RunUsage,
    agentic: bool,
) -> EventResult:
    result = EventResult(plan=plan)
    deps = VerifyDeps(web)
    for candidate in candidates[:PREFETCH_PER_EVENT]:
        deps.pages[candidate.url] = await web.get(candidate.url)
    deps.summaries = {candidate.url: candidate.summary for candidate in candidates if candidate.summary}
    prompt = verify_prompt(day, plan, candidates, deps, history)
    try:
        run = await verifier.run(
            prompt, deps=deps, toolsets=[FETCH_TOOL] if agentic else [], usage=usage, usage_limits=LIMITS
        )
        result.verdict = run.output
    except UsageLimitExceeded as error:
        result.error = f"run cost limit reached: {error}"
    except AgentRunError as error:
        result.error = f"{type(error).__name__}: {error}"
    result.pages_read = [url for url, page in deps.pages.items() if page.ok]
    result.refused_urls = deps.refused
    return result


def select(events: list[EventResult], day: date, history: list[HistoryItem]) -> None:
    """Step 7-8 in code: drop what is not new, already reported or weak, keep the top MAX_ITEMS."""
    reported = {item.source_url for item in history}
    keep = []
    for event in events:
        verdict = event.verdict
        if verdict is None:
            event.drop_reason = "not verified"
        elif not verdict.include:
            event.drop_reason = f"verifier excluded it: {verdict.reason}"
        elif verdict.kind in ("old_news", "unconfirmed"):
            event.drop_reason = f"kind is {verdict.kind}"
        elif verdict.source_url in reported:
            event.drop_reason = "already reported in an earlier digest"
        # Vendors date posts in US time, so the day before still counts; a repeat is caught by history.
        elif (
            verdict.kind != "discovery" and verdict.released_on and not day - timedelta(1) <= verdict.released_on <= day
        ):
            event.drop_reason = f"released on {verdict.released_on}, not on the target day"
        else:
            keep.append(event)
    keep.sort(key=lambda event: (event.verdict.kind == "discovery", -event.verdict.impact))
    for rank, event in enumerate(keep):
        event.selected = rank < MAX_ITEMS
        event.drop_reason = None if event.selected else f"not in the top {MAX_ITEMS}"
