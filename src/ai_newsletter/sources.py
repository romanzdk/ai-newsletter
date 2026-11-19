"""Step 2: collect candidates for the target day from every source. Plain code, no model.

A broken source does not stop the run: it is recorded in the coverage with its error,
and the other sources still count. A source that answers but contains nothing we can parse
is an error too (its layout probably changed), not "a quiet day".
"""

import asyncio
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ElementTree
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin

from ai_newsletter import days
from ai_newsletter.config import HN_MIN_POINTS, SOURCES, Source
from ai_newsletter.models import Candidate, SourceCoverage
from ai_newsletter.web import Web

HN_MAX_PAGES = 10


class SourceError(Exception):
    pass


async def collect(web: Web, day: date) -> tuple[list[Candidate], list[SourceCoverage]]:
    results = await asyncio.gather(*(_collect_one(web, source, day) for source in SOURCES))
    candidates = [candidate for found, _ in results for candidate in found]
    return candidates, [coverage for _, coverage in results]


async def _collect_one(web: Web, source: Source, day: date) -> tuple[list[Candidate], SourceCoverage]:
    try:
        items = await READERS[source.kind](web, source, day)
    except (SourceError, ValueError, KeyError, TypeError, ElementTree.ParseError) as error:
        return [], SourceCoverage(source=source.name, url=source.url, ok=False, error=str(error))
    found = [item for item in items if item.published and days.day_of(item.published) == day]
    # HN is searched by date and Trending is one day by definition; the other sources list only their
    # newest items and can cut the day off.
    gap = None if source.kind in ("hacker_news", "github_trending") else _coverage_gap(items, day)
    return found, SourceCoverage(source=source.name, url=source.url, ok=gap is None, candidates=len(found), error=gap)


def _coverage_gap(items: list[Candidate], day: date) -> str | None:
    """Why the source may not show the whole target day, or None when it does.

    Feeds and listing pages show only the newest N items. If even the oldest one is from the
    target day or later, older items of that day may have dropped off: say so, don't guess.
    The items that were found are still used.
    """
    dated = [item.published for item in items if item.published]
    if not dated:
        return "found no dated items; the page layout may have changed"
    oldest = min(days.day_of(published) for published in dated)
    # A GitHub repo whose very first release is on the target day is reported as possibly cut too.
    if oldest >= day:
        return f"the oldest item listed is from {oldest}, so {day} may not be fully covered"
    return None


async def _read(web: Web, url: str) -> str:
    page = await web.get(url)
    if not page.ok:
        raise SourceError(f"{url}: {page.error}")
    return page.body


def _id(prefix: str, url: str) -> str:
    return f"{prefix}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _plain(text: str, limit: int = 600) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()[:limit]


# --- Hacker News (Algolia API) -------------------------------------------------


def hn_search_url(base_url: str, day: date, page: int) -> str:
    start, end = days.window(day)
    filters = f"created_at_i>={int(start.timestamp())},created_at_i<{int(end.timestamp())},points>={HN_MIN_POINTS}"
    return f"{base_url}?{urlencode({'tags': 'story', 'numericFilters': filters, 'hitsPerPage': 200, 'page': page})}"


async def hacker_news(web: Web, source: Source, day: date) -> list[Candidate]:
    found = []
    for page in range(HN_MAX_PAGES):
        data = json.loads(await _read(web, hn_search_url(source.url, day, page)))
        for hit in data["hits"]:
            discussion = f"https://news.ycombinator.com/item?id={hit['objectID']}"
            found.append(
                Candidate(
                    id=f"hn-{hit['objectID']}",
                    source=source.name,
                    title=hit["title"],
                    url=hit.get("url") or discussion,
                    published=datetime.fromtimestamp(hit["created_at_i"], UTC),
                    points=hit.get("points"),
                    discussion_url=discussion,
                )
            )
        if page + 1 >= data["nbPages"]:
            if not found:  # every real day has popular stories; an empty answer means something broke
                raise SourceError("the search returned no stories at all")
            return found
    raise SourceError(f"more than {HN_MAX_PAGES} pages of results; the rest was not read")


# --- RSS and Atom feeds ------------------------------------------------------------

ATOM = "{http://www.w3.org/2005/Atom}"


async def rss(web: Web, source: Source, day: date) -> list[Candidate]:
    root = ElementTree.fromstring(await _read(web, source.url))
    if root.tag == f"{ATOM}feed":
        return [_atom_entry(source, entry) for entry in root.findall(f"{ATOM}entry")]
    items = root.findall("./channel/item")
    return [
        Candidate(
            id=_id("rss", item.findtext("link", "").strip()),
            source=source.name,
            title=item.findtext("title", "").strip(),
            url=item.findtext("link", "").strip(),
            published=_rss_date(item.findtext("pubDate")),
            summary=_plain(item.findtext("description", "")),
        )
        for item in items
    ]


def _atom_entry(source: Source, entry: ElementTree.Element) -> Candidate:
    links = entry.findall(f"{ATOM}link")
    url = next((link.get("href") for link in links if link.get("rel", "alternate") == "alternate"), "")
    published = entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated")
    return Candidate(
        id=_id("rss", url),
        source=source.name,
        title=entry.findtext(f"{ATOM}title", "").strip(),
        url=url,
        published=datetime.fromisoformat(published) if published else None,
        summary=_plain(entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or ""),
    )


def _rss_date(value: str | None) -> datetime | date | None:
    if not value:
        return None
    published = parsedate_to_datetime(value)
    # midnight UTC is read as "only the day is known" (OpenAI and Cursor publish it so);
    # a real post at exactly 00:00:00 UTC would lose its time, harmless for daily grouping
    if published.hour == published.minute == published.second == 0:
        return published.date()
    return published


# --- HTML listing pages (sites without a feed) ----------------------------------

_ANCHOR = re.compile(r"<a\b[^>]*href=\"([^\"#]+)\"[^>]*>(.*?)</a>", re.S)
_DATE = re.compile(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4})\b")
_DATE_NEAR = 3000  # characters between a link and the date shown next to it


async def html_listing(web: Web, source: Source, day: date) -> list[Candidate]:
    """Article links with the date shown next to them on a listing page.

    The date inside the link wins; otherwise the nearest date on the page counts.
    """
    page = await _read(web, source.url)
    dates = [(match.start(), _parse_listing_date(match.group(1))) for match in _DATE.finditer(page)]
    articles: dict[str, tuple[date, str]] = {}
    for anchor in _ANCHOR.finditer(page):
        href, text = anchor.group(1), _plain(anchor.group(2), 300)
        if not re.search(source.link_pattern, href):
            continue
        published = _date_of_link(text, anchor.start(), dates)
        url = urljoin(source.url, href)
        if published and (url not in articles or len(text) > len(articles[url][1])):
            articles[url] = (published, text)
    return [
        Candidate(
            id=_id("web", url), source=source.name, title=_DATE.sub("", text).strip(), url=url, published=published
        )
        for url, (published, text) in articles.items()
    ]


def _date_of_link(text: str, position: int, dates: list[tuple[int, date]]) -> date | None:
    if own := _DATE.search(text):
        return _parse_listing_date(own.group(1))
    near = [(abs(pos - position), found) for pos, found in dates if abs(pos - position) < _DATE_NEAR]
    return min(near)[1] if near else None


def _parse_listing_date(text: str) -> date:
    for pattern in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"unknown date format: {text}")


# --- GitHub releases ---------------------------------------------------------------


async def github_releases(web: Web, source: Source, day: date) -> list[Candidate]:
    repo = source.name.removeprefix("GitHub ")
    return [
        Candidate(
            id=_id("gh", release["html_url"]),
            source=source.name,
            title=_release_title(repo, release),
            url=release["html_url"],
            published=datetime.fromisoformat(release["published_at"]),
            summary=_plain(release.get("body") or "", 1500),
        )
        for release in json.loads(await _read(web, source.url))
        if not release["draft"] and release.get("published_at")
    ]


def _release_title(repo: str, release: dict) -> str:
    title = f"{repo} {release.get('name') or release['tag_name']}"
    return f"{title} (pre-release)" if release["prerelease"] else title


# --- GitHub Trending -------------------------------------------------------------

_TRENDING_ROW = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
_TRENDING_REPO = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([\w.-]+/[\w.-]+)"')
_TRENDING_ABOUT = re.compile(r'<p class="col-9[^"]*">(.*?)</p>', re.S)
_TRENDING_STARS = re.compile(r"([\d,]+) stars today")


async def github_trending(web: Web, source: Source, day: date) -> list[Candidate]:
    """Repositories with the most new stars in the last day. The page shows only "now", so a live run
    can cover only yesterday; a replay uses the page saved when that run was made."""
    if web.live and day != days.yesterday():
        raise SourceError(f"Trending shows only the last day, it cannot cover {day}")
    found = []
    for row in _TRENDING_ROW.findall(await _read(web, source.url)):
        if not (repo := _TRENDING_REPO.search(row)):
            raise SourceError("a row without a repository link; the page layout may have changed")
        about = _TRENDING_ABOUT.search(row)
        stars = _TRENDING_STARS.search(row)
        summary = _plain(about.group(1)) if about else ""
        if stars:
            summary = f"{summary} ({stars.group(1)} new stars that day)".strip()
        url = f"https://github.com/{repo.group(1)}"
        found.append(
            Candidate(
                id=_id("trend", url), source=source.name, title=repo.group(1), url=url, published=day, summary=summary
            )
        )
    if not found:
        raise SourceError("found no repositories; the page layout may have changed")
    return found


READERS = {
    "hacker_news": hacker_news,
    "rss": rss,
    "html_listing": html_listing,
    "github_releases": github_releases,
    "github_trending": github_trending,
}
