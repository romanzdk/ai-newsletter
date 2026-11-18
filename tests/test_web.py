import functools

import httpx
import pytest

from ai_newsletter import web as web_module
from ai_newsletter.config import MAX_PAGE_CHARS
from ai_newsletter.web import Page, Web, html_to_text, page_text


def test_only_https_and_allowlisted_hosts():
    web = Web({})
    assert web.refusal("https://github.com/x/y") is None
    assert "https" in web.refusal("http://github.com/x/y")
    assert "allowlist" in web.refusal("https://evil.example/steal")
    assert "allowlist" in web.refusal("https://[broken")  # a malformed URL from a page or the model
    web.allow_hosts_of(["https://quillstack.dev/blog/post"])
    assert web.refusal("https://quillstack.dev/docs") is None


async def test_replay_answers_only_from_the_snapshot():
    saved = Page(url="https://github.com/a", status=200, body="hi")
    web = Web({saved.url: saved})
    assert (await web.get("https://github.com/a")).body == "hi"
    assert (await web.get("https://github.com/b")).error == "not in the saved snapshot"
    assert (await web.get("https://evil.example/")).error.startswith("refused")


@pytest.fixture
def fake_internet(monkeypatch):
    """Route the live client to an in-memory handler instead of the network."""

    def use(handler):
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(web_module.httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=transport))

    async def public(url):
        return None

    monkeypatch.setattr(web_module, "_private_address", public)
    return use


async def test_a_redirect_to_a_host_off_the_allowlist_is_refused(fake_internet):
    fake_internet(lambda request: httpx.Response(302, headers={"location": "https://evil.example/x"}))
    page = await Web().get("https://github.com/start")
    assert not page.ok
    assert "evil.example" in page.error


async def test_live_pages_are_kept_for_replay(fake_internet):
    fake_internet(lambda request: httpx.Response(200, text="<p>hello</p>", headers={"content-type": "text/html"}))
    web = Web()
    page = await web.get("https://github.com/x")
    assert page.ok and web.pages["https://github.com/x"] == page


async def test_server_errors_are_retried_once(fake_internet, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, text="ok")

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(web_module.asyncio, "sleep", no_wait)
    fake_internet(handler)
    assert (await Web().get("https://github.com/x")).ok
    assert len(calls) == 2


def test_long_pages_are_cut_with_a_visible_marker():
    page = Page(url="https://github.com/x", status=200, content_type="text/plain", body="a" * (MAX_PAGE_CHARS + 10))
    assert page_text(page).endswith(f"[CUT: only the first {MAX_PAGE_CHARS} of {MAX_PAGE_CHARS + 10} characters shown]")


def test_html_text_keeps_content_dates_and_links_but_not_scripts():
    html = (
        '<html><head><meta property="article:published_time" content="2026-03-10"></head><body>'
        '<script>var x = "hidden";</script><p>Visible <a href="/docs">docs</a></p></body></html>'
    )
    text = html_to_text(html, "https://quillstack.dev/blog")
    assert "article:published_time=2026-03-10" in text
    assert "Visible docs" in text
    assert "https://quillstack.dev/docs" in text
    assert "hidden" not in text
