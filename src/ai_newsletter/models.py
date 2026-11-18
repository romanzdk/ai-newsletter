"""The data that flows through one run, in the order it is created.

Candidate -> EventPlan (triage) -> Verdict (verification) -> EventResult -> RunRecord
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """One link found in a source: an HN story, a blog post or a GitHub release."""

    id: str
    source: str
    title: str
    url: str
    published: datetime | date | None = Field(description="A bare date when the source gives only the day.")
    summary: str = ""
    points: int | None = None
    discussion_url: str | None = None


class SourceCoverage(BaseModel):
    source: str
    url: str
    ok: bool
    candidates: int = 0
    error: str | None = None


class EventPlan(BaseModel):
    """Triage output: candidates that describe the same event, and what to verify about it."""

    candidate_ids: list[str] = Field(description="All candidates about this one event.")
    label: str = Field(description="Short English name of the event, e.g. 'Toolname 2.0 stable release'.")
    reason: str = Field(description="Why it may matter to developers using AI tools.")
    to_verify: str = Field(description="The open questions verification must answer.")


class Skip(BaseModel):
    candidate_ids: list[str]
    reason: str = Field(description="E.g. 'already reported on 2026-03-02', 'funding news', 'minor fix'.")


class Triage(BaseModel):
    events: list[EventPlan] = Field(description="Events worth verifying, most promising first.")
    skipped: list[Skip] = Field(
        default_factory=list,
        description="AI-related candidates you decided against, with the reason. Unrelated ones need not be listed.",
    )


class Claim(BaseModel):
    text: str
    source_url: str = Field(description="The page you read that supports this claim.")


Kind = Literal["release", "stable_release", "update", "announcement", "discovery", "old_news", "unconfirmed"]
Availability = Literal["available", "preview", "beta", "nightly", "source_only", "announced_only", "unknown"]


class Verdict(BaseModel):
    """Verification output for one event. The Czech fields are the text of the report item."""

    include: bool = Field(
        description="True only if the event is useful in practice, new on the target day (or a clearly labelled "
        "discovery) and its key claims are supported by pages you read."
    )
    reason: str = Field(description="English: why it is included or not, based on what you read.")
    kind: Kind = Field(
        description="release: new product or version; stable_release: stable version of something seen before in "
        "preview/beta/nightly; update: change to an existing product; announcement: announced, not yet usable; "
        "discovery: older project newly noticed; old_news: nothing new on the target day; unconfirmed: could not "
        "be confirmed from a reliable source."
    )
    availability: Availability
    released_on: date | None = Field(description="Day the change became public per the sources. None if unknown.")
    date_note: str | None = Field(description="Any doubt or conflict about the date, else null.")
    impact: int = Field(ge=1, le=5, description="Practical impact for developers: 1 minor, 5 major.")
    claims: list[Claim] = Field(description="The key facts, each with the page that supports it.")
    title: str = Field(description="Czech: short, concrete headline.")
    what_changed: str = Field(description="Czech: one short sentence on what changed.")
    why_it_matters: str = Field(description="Czech: one short sentence on the practical use. No invented benefits.")
    caveat: str | None = Field(description="Czech: the most important limit or condition (plan, preview, region...).")
    source_url: str = Field(description="The decisive source, a page you read.")


class EventResult(BaseModel):
    plan: EventPlan
    verdict: Verdict | None = None
    error: str | None = None
    pages_read: list[str] = []
    refused_urls: list[str] = []
    selected: bool = False
    drop_reason: str | None = None


class Usage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)


Status = Literal["complete", "partial", "failed"]


class RunRecord(BaseModel):
    """Everything needed to review a run later. Saved as run.json next to the report."""

    day: date
    window_start: datetime
    window_end: datetime
    started_at: datetime
    finished_at: datetime | None = None
    mode: Literal["live", "replay"]
    variant: Literal["agentic", "single_pass"]
    model: str
    status: Status = "failed"
    coverage: list[SourceCoverage] = []
    candidates: list[Candidate] = []
    skipped: list[Skip] = []
    events: list[EventResult] = []
    errors: list[str] = []
    usage: Usage = Usage()
    report: str = ""


class HistoryItem(BaseModel):
    """An item published in an earlier report."""

    day: date
    title: str
    source_url: str
    kind: Kind
