import functools
import json

import httpx
import pytest

from ai_newsletter import store, telegram
from ai_newsletter.models import RunRecord
from tests.helpers import DEMO_RUN


@pytest.fixture
def run_folder(tmp_path, monkeypatch):
    """A saved live run of the demo day, ready to send."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    record = RunRecord.model_validate_json((DEMO_RUN / "run.json").read_text())
    return store.save(tmp_path, record.model_copy(update={"mode": "live", "variant": "agentic"}), {})


@pytest.fixture
def telegram_api(monkeypatch):
    """Answer Telegram requests with `answers` in turn; returns the list of sent texts."""
    sent = []

    def use(*answers):
        replies = iter(answers)

        def handler(request):
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            sent.append(json.loads(request.content)["text"])
            return reply

        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(telegram.httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=transport))
        return sent

    return use


OK = httpx.Response(200, json={"ok": True})


def state(run_folder) -> dict:
    return json.loads((run_folder.parent / "telegram.json").read_text())


async def test_the_report_is_sent_once_per_day(run_folder, telegram_api):
    sent = telegram_api(OK, OK)
    assert await telegram.send(run_folder) == "sent to Telegram in 1 message(s)"
    assert sent[0].startswith("<b>AI novinky za 10. 3. 2026</b>")
    assert state(run_folder)["status"] == "sent"
    with pytest.raises(telegram.NotSent, match="already sent"):
        await telegram.send(run_folder)  # a re-run of the same day does not deliver twice
    assert len(sent) == 1


async def test_a_clear_refusal_can_be_retried(run_folder, telegram_api):
    telegram_api(httpx.Response(429, json={"ok": False, "description": "Too Many Requests"}), OK)
    with pytest.raises(telegram.NotSent, match="failed: Too Many Requests"):
        await telegram.send(run_folder)
    assert await telegram.send(run_folder) == "sent to Telegram in 1 message(s)"


async def test_a_broken_connection_is_not_retried_blindly(run_folder, telegram_api):
    telegram_api(httpx.ReadTimeout("timed out"))
    with pytest.raises(telegram.NotSent, match="uncertain: ReadTimeout"):
        await telegram.send(run_folder)
    with pytest.raises(telegram.NotSent, match="already uncertain"):
        await telegram.send(run_folder)
    assert "secret" not in (run_folder.parent / "telegram.json").read_text()  # the token never lands on disk


async def test_replays_are_not_delivered(run_folder, telegram_api):
    record = RunRecord.model_validate_json((run_folder / "run.json").read_text())
    replay = store.save(run_folder.parent.parent.parent, record.model_copy(update={"mode": "replay"}), {})
    with pytest.raises(telegram.NotSent, match="only live agentic runs"):
        await telegram.send(replay)


def test_markdown_becomes_telegram_html_and_long_reports_are_split():
    text = telegram.telegram_html("# Title\n\n**1. A < B**  \nText & more\n\n---\nKontrola: úplná.")
    assert text == "<b>Title</b>\n\n<b>1. A &lt; B</b>\nText &amp; more\n\nKontrola: úplná."
    parts = telegram.split("\n\n".join(["x" * 3000] * 3))
    assert [len(part) for part in parts] == [3000, 3000, 3000]
