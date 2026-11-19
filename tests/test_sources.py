import json
from datetime import date, timedelta

from ai_newsletter import days
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


async def test_atom_feeds_are_read_too():
    body = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>llm 1.0</title>'
        '<link href="https://simonwillison.net/2026/Mar/10/llm/" rel="alternate"/>'
        "<published>2026-03-10T15:00:00+00:00</published><summary>&lt;p&gt;New release&lt;/p&gt;</summary></entry>"
        '<entry><title>older</title><link href="https://simonwillison.net/old"/>'
        "<updated>2026-03-02T10:00:00+00:00</updated></entry></feed>"
    )
    found, coverage = await _collect_one(web_with(RSS.url, body), RSS, DEMO_DAY)
    assert coverage.ok
    assert [(c.title, c.url, c.summary) for c in found] == [
        ("llm 1.0", "https://simonwillison.net/2026/Mar/10/llm/", "New release")
    ]


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
    assert len(candidates) == 9


TRENDING = Source("GitHub Trending Python", "github_trending", "https://github.com/trending/python?since=daily")


async def test_trending_repositories_belong_to_the_day_and_keep_their_new_stars():
    row = (
        '<article class="Box-row"><h2 class="h3"><a href="/org/tool">org / tool</a></h2>'
        '<p class="col-9 color-fg-muted">Agent &amp; CLI</p> 1,353 stars today</article>'
    )
    found, coverage = await _collect_one(web_with(TRENDING.url, row), TRENDING, DEMO_DAY)
    assert coverage.ok
    assert [(c.title, c.url, c.published, c.summary) for c in found] == [
        ("org/tool", "https://github.com/org/tool", DEMO_DAY, "Agent & CLI (1,353 new stars that day)")
    ]


async def test_trending_with_a_changed_layout_is_an_error_not_a_quiet_day():
    _, coverage = await _collect_one(web_with(TRENDING.url, "<html>new layout</html>"), TRENDING, DEMO_DAY)
    assert not coverage.ok
    assert "layout" in coverage.error


async def test_a_live_run_cannot_take_todays_trending_for_an_older_day():
    _, coverage = await _collect_one(Web(), TRENDING, days.yesterday() - timedelta(days=3))
    assert not coverage.ok
    assert "only the last day" in coverage.error
