"""Delivering a finished report to Telegram. Kept apart from the pipeline: preparing a report is not
delivering it.

At most one report per day is delivered. The state is kept in data/runs/<day>/telegram.json:

    sending    written before the first message; if it stays, the send was interrupted
    sent       every part was delivered
    failed     Telegram answered with an error before any part was delivered: safe to try again
    uncertain  the connection broke, or only some parts were delivered: check the chat yourself

Only "failed" may be retried automatically. In every other case nothing is sent again, so a re-run or
a retry never delivers the same digest twice. To send again after checking, delete telegram.json.

Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID. Resend an earlier run:
    uv run python -m ai_newsletter.telegram data/runs/2026-11-17/<run>
"""

import asyncio
import html
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ai_newsletter.models import RunRecord

MAX_MESSAGE = 4096  # Telegram's limit per message


class NotSent(Exception):
    pass


async def send(run_folder: Path) -> str:
    """Send the run's report once and return what happened. Raises NotSent when nothing was sent."""
    record = RunRecord.model_validate_json((run_folder / "run.json").read_text())
    if (record.mode, record.variant) != ("live", "agentic"):
        raise NotSent("only live agentic runs are delivered, not replays or baselines")
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise NotSent("set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

    state_file = run_folder.parent / "telegram.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    if state and not (state["status"] == "failed" and state["parts_sent"] == 0):
        raise NotSent(f"already {state['status']} for {record.day} ({state_file}); delete it to send again")

    parts = split(telegram_html(record.report))
    state = {"run": run_folder.name, "status": "sending", "parts": len(parts), "parts_sent": 0, "error": None}
    _save(state_file, state)
    async with httpx.AsyncClient(timeout=30) as client:
        for part in parts:
            try:
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": part,
                        "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": True},
                    },
                )
            except httpx.HTTPError as error:  # the message may or may not have arrived
                state |= {"status": "uncertain", "error": type(error).__name__}
                break
            if error := _refusal(response):
                state |= {"status": "uncertain" if state["parts_sent"] else "failed", "error": error}
                break
            state["parts_sent"] += 1
        else:
            state["status"] = "sent"
    _save(state_file, state)
    if state["status"] != "sent":
        raise NotSent(f"{state['status']}: {state['error']} ({state['parts_sent']} of {len(parts)} parts sent)")
    return f"sent to Telegram in {len(parts)} message(s)"


def _refusal(response: httpx.Response) -> str | None:
    """Telegram's error message, or None when the message was accepted."""
    try:
        answer = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    return None if answer.get("ok") else answer.get("description", f"HTTP {response.status_code}")


def _save(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state | {"updated_at": datetime.now(UTC).isoformat()}, indent=2))


def telegram_html(markdown: str) -> str:
    """Our report's small Markdown subset in Telegram's HTML: headings and **bold**, nothing else."""
    text = html.escape(markdown, quote=False)
    text = re.sub(r"^# (.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r" {2}$", "", text, flags=re.M)  # Markdown line breaks
    return re.sub(r"\n+---\n", "\n\n", text).strip()


def split(text: str) -> list[str]:
    """Messages of at most MAX_MESSAGE characters, cut between paragraphs (one item each)."""
    parts = [""]
    for paragraph in text.split("\n\n"):
        candidate = f"{parts[-1]}\n\n{paragraph}" if parts[-1] else paragraph
        if len(candidate) <= MAX_MESSAGE:
            parts[-1] = candidate
        else:
            parts.append(paragraph[:MAX_MESSAGE])  # an item is far shorter; the cut is only a safety net
    return parts


if __name__ == "__main__":
    try:
        print(asyncio.run(send(Path(sys.argv[1]))))
    except NotSent as error:
        sys.exit(f"Not sent: {error}")
