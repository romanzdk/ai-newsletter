"""The settings you are most likely to change. There is no config file: change the value here."""

from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic_ai.models.openrouter import OpenRouterModelSettings

MODEL = "openrouter:anthropic/claude-haiku-5.5"
# One upstream provider for the whole conversation: the model's thinking blocks are signed by the
# provider that made them, and OpenRouter switching provider between a tool call and the answer
# makes the next request fail. No prompt logging for training (the inputs are public pages anyway).
# if Anthropic's endpoint is down, model steps fail and the run reports it as partial/failed
MODEL_SETTINGS = OpenRouterModelSettings(
    openrouter_provider={"only": ["anthropic"], "allow_fallbacks": False, "data_collection": "deny"},
    timeout=120,  # seconds per model request
)
TIMEZONE = ZoneInfo("Europe/Prague")

MAX_ITEMS = 7  # items in the report, at most
MAX_EVENTS_TO_VERIFY = 10  # events the triage step may send to verification
MAX_FETCHES_PER_EVENT = 4  # extra pages the verifier may read for one event
RUN_COST_LIMIT_USD = 0.50  # one run stops calling the model once it has spent this much
MAX_REQUESTS_PER_RUN = 80  # model requests in one run, a safety net next to the cost limit
HISTORY_DAYS = 14  # how far back the "already reported?" check looks

HN_MIN_POINTS = 20  # Hacker News stories with fewer points are not even considered

MAX_PAGE_CHARS = 15_000  # what the model sees of one page; longer pages are cut and marked as cut
USER_AGENT = "ai-newsletter/0.1 (+https://github.com/romanzdk/ai-newsletter)"


@dataclass(frozen=True)
class Source:
    name: str
    kind: Literal["hacker_news", "rss", "html_listing", "github_releases"]
    url: str
    link_pattern: str = ""  # html_listing only: regex for article links on the listing page


GITHUB_REPOS = ["anthropics/claude-code", "openai/codex", "pingdotgg/t3code", "paperclipai/paperclip"]

SOURCES = [
    Source("Hacker News", "hacker_news", "https://hn.algolia.com/api/v1/search_by_date"),
    Source("OpenAI News", "rss", "https://openai.com/news/rss.xml"),
    Source("Cursor Changelog", "rss", "https://cursor.com/changelog/rss.xml"),
    # Category pages like /news/product are one word; articles have a hyphenated slug.
    Source("Anthropic News", "html_listing", "https://www.anthropic.com/news", r"^/news/\w+-[\w-]+$"),
    Source("Claude Blog", "html_listing", "https://claude.com/blog", r"(/blog/|/articles/)\w+-[\w-]+/?$"),
    *[
        Source(f"GitHub {repo}", "github_releases", f"https://api.github.com/repos/{repo}/releases?per_page=30")
        for repo in GITHUB_REPOS
    ],
]

# Named to the verifier as places to check a release.
OFFICIAL_CHANGELOGS = [
    "https://developers.openai.com/api/docs/changelog",
    "https://docs.claude.com/en/release-notes/overview",
    "https://cursor.com/changelog",
]

# Hosts the app may read. On top of these, a run may read the hosts of that day's candidate links
# (an HN story about a new tool points to the tool's own site). Anything else is refused in code,
# whatever a page or the model asks for.
ALLOWED_HOSTS = {
    "hn.algolia.com",
    "news.ycombinator.com",
    "api.github.com",
    "github.com",
    "openai.com",
    "developers.openai.com",
    "platform.openai.com",
    "help.openai.com",
    "www.anthropic.com",
    "anthropic.com",
    "claude.com",
    "www.claude.com",
    "claude.dev",
    "docs.claude.com",
    "code.claude.com",
    "support.claude.com",
    "cursor.com",
    "docs.cursor.com",
    "forum.cursor.com",
}
