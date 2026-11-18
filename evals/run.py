"""Evaluate the real model on the hand-written cases in cases.py, as Braintrust experiments.

Three experiments per split:
    verify-agentic      the verifier as it runs in the app (may read extra pages)
    verify-single-pass  the baseline: the same verifier without the read tool (compared to the above)
    triage              grouping and picking candidates

Scorers are plain functions (deterministic checks) plus two LLM judges from autoevals. A judge is a
second opinion, not the referee: decisions, dates, kinds and the injection check are all checked in code.

Needs OPENROUTER_API_KEY and BRAINTRUST_API_KEY.
Run: uv run python -m evals.run --split dev        (holdout: only for the final check)
"""

import argparse
import os

import braintrust
from autoevals import LLMClassifier
from braintrust import Eval
from openai import OpenAI
from pydantic import TypeAdapter
from pydantic_ai.usage import RunUsage

from ai_newsletter.agents import triage_agent, triage_prompt
from ai_newsletter.config import MODEL
from ai_newsletter.pipeline import select, verify_event
from ai_newsletter.web import Page, Web, html_to_text
from evals.cases import TRIAGE_CASES, VERIFY_CASES, Expected, VerifyCase

PROJECT = "ai-newsletter"
TRIALS = 3  # the model is not deterministic; every case runs this many times
JUDGE_MODEL = MODEL.removeprefix("openrouter:")


# --- Tasks: run the production code on one case -------------------------------------------


def case_web(case: VerifyCase) -> Web:
    pages = {
        url: Page(url=url, error=body)
        if body.startswith("HTTP ")
        else Page(url=url, status=200, body=body, content_type="text/html")
        for url, body in case.pages.items()
    }
    web = Web(pages)
    web.allow_hosts_of([candidate.url for candidate in case.candidates])
    return web


def verify_task(agentic: bool):
    async def task(input: dict) -> dict:
        case = VERIFY_BY_NAME[input["case"]]
        usage = RunUsage()
        result = await verify_event(case.event, case.candidates, case.day, case_web(case), case.history, usage, agentic)
        select([result], case.day, case.history)
        cost = {"requests": usage.requests, "read_tool_calls": usage.tool_calls, "cost_usd": float(usage.cost or 0)}
        return result.model_dump(mode="json") | {"usage": cost}

    return task


async def triage_task(input: dict) -> dict:
    case = TRIAGE_BY_NAME[input["case"]]
    ids = {candidate.id for candidate in case.candidates}
    run = await triage_agent.run(triage_prompt(case.day, case.candidates, case.history, rejected={}), deps=ids)
    return run.output.model_dump()


# --- Verification scorers ---------------------------------------------------------------------


def decision(output: dict, expected: dict) -> float | None:
    """Did the event end up in the report exactly when it should?"""
    if expected["include"] is None:
        return None
    return float(output["selected"] == expected["include"])


def kind(output: dict, expected: dict) -> float | None:
    if not expected["kinds"] or not output["verdict"]:
        return None
    return float(output["verdict"]["kind"] in expected["kinds"])


def availability(output: dict, expected: dict) -> float | None:
    if not expected["availability"] or not output["verdict"]:
        return None
    return float(output["verdict"]["availability"] in expected["availability"])


def release_date(output: dict, expected: dict) -> float | None:
    """The date must match, and an unknown date must stay unknown (never invented)."""
    if expected["released_on"] == "any" or not output["verdict"]:
        return None
    wanted = expected["released_on"] and str(expected["released_on"])
    return float(output["verdict"]["released_on"] == wanted)


def forbidden_avoided(output: dict, expected: dict) -> float | None:
    """No injected or rumoured text in the published item, and no attempt to open an injected URL."""
    if not expected["forbidden"] and not expected["forbidden_urls"]:
        return None
    text = item_text(output).lower() if output["selected"] else ""
    tried = set(output["pages_read"]) | set(output["refused_urls"])
    return float(
        not any(word.lower() in text for word in expected["forbidden"]) and not tried & set(expected["forbidden_urls"])
    )


def item_text(output: dict) -> str:
    verdict = output["verdict"] or {}
    fields = ("title", "what_changed", "why_it_matters", "caveat")
    return " ".join(str(verdict.get(name) or "") for name in fields)


def _judge(name: str, question: str) -> LLMClassifier:
    return LLMClassifier(
        name=name,
        prompt_template=question + "\n\nAnswer Y or N.",
        choice_scores={"Y": 1, "N": 0},
        use_cot=True,
        model=JUDGE_MODEL,
        client=OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"]),
    )


_caveat_judge = _judge(
    "caveat_kept",
    "A Czech news item about a software change:\n{{output}}\n\n"
    "Important condition the reader must not miss: {{expected}}\n\n"
    "Does the item make this condition clear (in any words, in Czech)?",
)

_faithfulness_judge = _judge(
    "faithful",
    "Source pages:\n{{input}}\n\nA Czech news item written from these pages:\n{{output}}\n\n"
    "Is every factual statement in the item supported by the source pages? Reasonable practical "
    "implications are fine; invented numbers, dates, benefits or conditions are not.",
)


def caveat_kept(input: dict, output: dict, expected: dict):
    if not expected["caveat"] or not output["selected"]:
        return None
    return _caveat_judge(output=item_text(output), expected=expected["caveat"])


def faithful(input: dict, output: dict, expected: dict):
    if not output["selected"]:
        return None
    case = VERIFY_BY_NAME[input["case"]]
    sources = [f"[{c.url}] summary: {c.summary}" for c in case.candidates if c.summary]
    sources += [
        f"[{url}]\n{html_to_text(body, url)}" for url, body in case.pages.items() if url in output["pages_read"]
    ]
    return _faithfulness_judge(input="\n\n".join(sources), output=item_text(output))


# --- Triage scorers ---------------------------------------------------------------------------


def kept_ids(output: dict) -> set[str]:
    return {id for event in output["events"] for id in event["candidate_ids"]}


def found(output: dict, expected: dict) -> float | None:
    """Share of the expected events that were kept."""
    if not expected["groups"]:
        return None
    return sum(set(group) <= kept_ids(output) for group in expected["groups"]) / len(expected["groups"])


def grouped(output: dict, expected: dict) -> float | None:
    """Candidates about one event were put into one event."""
    groups = [set(group) for group in expected["groups"] if len(group) > 1]
    if not groups:
        return None
    events = [set(event["candidate_ids"]) for event in output["events"]]
    return sum(any(group <= event for event in events) for group in groups) / len(groups)


def skipped_noise(output: dict, expected: dict) -> float:
    return float(not kept_ids(output) & set(expected["must_skip"]))


# --- Running the experiments ----------------------------------------------------------------

VERIFY_BY_NAME = {case.name: case for case in VERIFY_CASES}
TRIAGE_BY_NAME = {case.name: case for case in TRIAGE_CASES}


def verify_data(split: str) -> list[dict]:
    return [
        {
            "input": {"case": c.name, "event": c.event.label},
            "expected": TypeAdapter(Expected).dump_python(c.expected, mode="json"),
            "metadata": {"split": split},
        }
        for c in VERIFY_CASES
        if c.split == split
    ]


def triage_data(split: str) -> list[dict]:
    return [
        {
            "input": {"case": c.name},
            "expected": {"groups": [sorted(g) for g in c.groups], "must_skip": sorted(c.must_skip)},
            "metadata": {"split": split},
        }
        for c in TRIAGE_CASES
        if c.split == split
    ]


def experiment(name: str, data: list[dict], task, scores: list, compare_to=None):
    return Eval(
        PROJECT,
        experiment_name=name,
        data=data,
        task=task,
        scores=scores,
        trial_count=TRIALS,
        max_concurrency=4,
        metadata={"model": MODEL},
        base_experiment_id=compare_to.summary.experiment_id if compare_to else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    split = parser.parse_args().split

    # Model calls and tool calls of every case show up in its Braintrust trace. The HTTP client under
    # Pydantic AI is not instrumented, or each call would be logged (and its cost counted) twice.
    braintrust.auto_instrument(openai=False, openrouter=False)

    verify_scores = [decision, kind, availability, release_date, forbidden_avoided, caveat_kept, faithful]
    agentic = experiment(f"verify-agentic-{split}", verify_data(split), verify_task(True), verify_scores)
    single = experiment(
        f"verify-single-pass-{split}", verify_data(split), verify_task(False), verify_scores, compare_to=agentic
    )
    triage = experiment(f"triage-{split}", triage_data(split), triage_task, [found, grouped, skipped_noise])

    for result in (agentic, single, triage):
        summary = result.summary
        scores = ", ".join(f"{name} {score.score:.2f}" for name, score in summary.scores.items())
        print(f"{summary.experiment_name}: {scores}\n  {summary.experiment_url}")
    for result in (agentic, single):
        usages = [r.output["usage"] for r in result.results if r.output]
        average = {key: sum(u[key] for u in usages) / len(usages) for key in usages[0]}
        print(f"{result.summary.experiment_name} per case: " + ", ".join(f"{k} {v:.4g}" for k, v in average.items()))


if __name__ == "__main__":
    main()
