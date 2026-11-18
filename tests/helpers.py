"""Shared test data: the fictional demo day and fake models that stand in for the real one."""

import json
from datetime import date
from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ai_newsletter.store import load_snapshot
from ai_newsletter.web import Web

DEMO_RUN = Path(__file__).parent.parent / "examples" / "demo-run"
DEMO_DAY = date(2026, 3, 10)


def demo_web() -> Web:
    return Web(load_snapshot(DEMO_RUN))


def answer(output: dict) -> FunctionModel:
    """A fake model that immediately returns `output` as the structured result."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, json.dumps(output))])

    return FunctionModel(respond)


def read_then_answer(url: str, output: dict) -> FunctionModel:
    """A fake model that first asks to read `url`, then returns `output`."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        already_read = any(isinstance(part, ToolReturnPart) for message in messages for part in message.parts)
        if not already_read:
            return ModelResponse(parts=[ToolCallPart("fetch_page", {"url": url})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, json.dumps(output))])

    return FunctionModel(respond)


def verdict(**changes) -> dict:
    """A valid verifier answer for the demo's Quillstack event; override fields per test."""
    return {
        "include": True,
        "reason": "Stable release confirmed by the release notes.",
        "kind": "stable_release",
        "availability": "available",
        "released_on": "2026-03-10",
        "date_note": None,
        "impact": 4,
        "claims": [{"text": "Resumable runs are stable.", "source_url": "https://quillstack.dev/blog/quillstack-2-0"}],
        "title": "Quillstack 2.0: obnovitelné běhy",
        "what_changed": "Běh agenta pokračuje od posledního uloženého kroku.",
        "why_it_matters": "Přerušený běh se nemusí spouštět znovu.",
        "caveat": "Kroky se zápisem ven se automaticky neopakují.",
        "source_url": "https://quillstack.dev/blog/quillstack-2-0",
    } | changes


QUILLSTACK_EVENT = {
    "events": [
        {
            "candidate_ids": ["hn-9000001", "hn-9000008"],
            "label": "Quillstack 2.0",
            "reason": "Stable resumable runs.",
            "to_verify": "Stable? Which plans?",
        }
    ],
    "skipped": [{"candidate_ids": ["hn-9000004"], "reason": "funding news"}],
}


def events(count: int) -> dict:
    """A triage answer with `count` events about the demo's Quillstack story."""
    plan = QUILLSTACK_EVENT["events"][0]
    return {"events": [plan | {"label": f"event {n}"} for n in range(1, count + 1)]}
