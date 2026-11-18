import json
from datetime import date

from ai_newsletter.config import Source
from ai_newsletter.sources import _collect_one, collect, hacker_news, hn_search_url
from ai_newsletter.web import Page, Web
from tests.helpers import DEMO_DAY, demo_web


def web_with(url: str, body: str) -> Web:
    return Web({url: Page(url=url, status=200, body=body)})


def feed(*items: tuple[str, str]) -> str:
    rows = "".join(
        f"<item><title>{t}</title><link>https://cursor.com/{t}</link><pubDate>{d}</pubDate></item>" for t, d in items
    )
    return f"<rss><channel>{rows}</channel></rss>"


RSS = Source("Feed", "rss", "https://cursor.com/feed.xml")


async def test_rss_keeps_items_of_the_day_and_reads_midnight_as_date_only():
    body = feed(
        ("new", "Tue, 10 Mar 2026 00:00:00 GMT"),
        ("timed", "Tue, 10 Mar 2026 15:30:00 GMT"),
        ("old", "Mon, 02 Mar 2026 00:00:00 GMT"),
    )
    found, coverage = await _collect_one(web_with(RSS.url, body), RSS, DEMO_DAY)
    assert coverage.ok
    assert [c.title for c in found] == ["new", "timed"]
    assert type(found[0].published) is date


async def test_a_feed_that_no_longer_reaches_the_day_is_a_gap_not_a_quiet_day():
    body = feed(("same day", "Tue, 10 Mar 2026 10:00:00 GMT"), ("newer", "Fri, 13 Mar 2026 10:00:00 GMT"))
    found, coverage = await _collect_one(web_with(RSS.url, body), RSS, DEMO_DAY)
    assert not coverage.ok
    assert "may not be fully covered" in coverage.error
    assert [c.title for c in found] == ["same day"]  # what was found is still used


async def test_listing_pages_take_the_date_shown_next_to_each_link():
    source = Source("Blog", "html_listing", "https://claude.com/blog", r"/blog/\w+-[\w-]+$")
    page = (
        '<div><a href="/blog/new-feature">New feature</a><span>Mar 10, 2026</span></div>'
        '<div><a href="/blog/older-post">Older post Mar 2, 2026</a></div>'
        '<a href="/blog/category">Category</a>'
    )
    found, _ = await _collect_one(web_with(source.url, page), source, DEMO_DAY)
    assert [(c.title, c.url) for c in found] == [("New feature", "https://claude.com/blog/new-feature")]


async def test_github_releases_skip_drafts_and_mark_prereleases():
    source = Source("GitHub org/tool", "github_releases", "https://api.github.com/repos/org/tool/releases")
    releases = [
        {
            "html_url": "https://github.com/org/tool/releases/1",
            "name": "v1.1",
            "tag_name": "v1.1",
            "draft": False,
            "prerelease": True,
            "published_at": "2026-03-10T10:00:00Z",
            "body": "notes",
        },
        {
            "html_url": "https://github.com/org/tool/releases/2",
            "name": "draft",
            "tag_name": "v2",
            "draft": True,
            "prerelease": False,
            "published_at": None,
            "body": "",
        },
        {
            "html_url": "https://github.com/org/tool/releases/0",
            "name": "v1.0",
            "tag_name": "v1.0",
            "draft": False,
            "prerelease": False,
            "published_at": "2026-02-01T10:00:00Z",
            "body": "",
        },
    ]
    found, _ = await _collect_one(web_with(source.url, json.dumps(releases)), source, DEMO_DAY)
    assert [c.title for c in found] == ["org/tool v1.1 (pre-release)"]


async def test_hacker_news_reads_every_page():
    source = Source("Hacker News", "hacker_news", "https://hn.algolia.com/api/v1/search_by_date")
    hit = {"title": "t", "url": None, "points": 50, "created_at_i": 1773140000}
    pages = {
        hn_search_url(source.url, DEMO_DAY, n): Page(
            url="", status=200, body=json.dumps({"hits": [{**hit, "objectID": str(n)}], "nbPages": 2})
        )
        for n in (0, 1)
    }
    found = await hacker_news(Web(pages), source, DEMO_DAY)
    assert [c.id for c in found] == ["hn-0", "hn-1"]
    assert found[0].url == "https://news.ycombinator.com/item?id=0"  # Ask HN: the discussion is the link


async def test_one_broken_source_does_not_stop_the_others():
    candidates, coverage = await collect(demo_web(), DEMO_DAY)
    broken = [c for c in coverage if not c.ok]
    assert [c.source for c in broken] == ["OpenAI News"]
    assert "503" in broken[0].error
    assert len(candidates) == 8
