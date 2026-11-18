"""Reading the web: only allowed public hosts, and every page is kept so a run can be replayed.

Live mode downloads pages and remembers them. Replay mode answers only from the saved pages,
so the same inputs give the model exactly the same view of the web.
"""

import asyncio
import ipaddress
import re
import socket
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel

from ai_newsletter.config import ALLOWED_HOSTS, MAX_DOWNLOAD_BYTES, MAX_PAGE_CHARS, USER_AGENT

MAX_REDIRECTS = 5


class Page(BaseModel):
    url: str
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    body: str = ""
    fetched_at: datetime | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


class Web:
    def __init__(self, snapshot: dict[str, Page] | None = None, *, live: bool):
        self.live = live
        self.pages: dict[str, Page] = dict(snapshot or {})  # saved as snapshot.json at the end of the run
        self.extra_hosts: set[str] = set()

    def allow_hosts_of(self, urls: list[str]) -> None:
        self.extra_hosts |= {urlsplit(url).hostname or "" for url in urls}

    def refusal(self, url: str) -> str | None:
        """Why this URL may not be read, or None when it may."""
        parts = urlsplit(url)
        if parts.scheme != "https":
            return "only https is allowed"
        if parts.hostname not in ALLOWED_HOSTS | self.extra_hosts:
            return f"host {parts.hostname} is not on the allowlist"
        return None

    async def get(self, url: str) -> Page:
        if reason := self.refusal(url):
            return Page(url=url, error=f"refused: {reason}")
        if not self.live:
            return self.pages.get(url) or Page(url=url, error="not in the saved snapshot")
        if url not in self.pages:
            self.pages[url] = await _download(url, self.refusal)
        return self.pages[url]


async def _download(url: str, refusal) -> Page:
    """GET with manual redirects, so every hop is checked against the allowlist."""
    requested = url
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        for _ in range(MAX_REDIRECTS + 1):
            if reason := refusal(url) or await _private_address(url):
                return Page(url=requested, final_url=url, error=f"refused: {reason}")
            try:
                status, content_type, body, location = await _request(client, url)
            except httpx.HTTPError as error:
                return Page(url=requested, final_url=url, error=f"{type(error).__name__}: {error}")
            if location:
                url = urljoin(url, location)
                continue
            error = None if status == 200 else f"HTTP {status}"
            return Page(
                url=requested,
                final_url=url,
                status=status,
                content_type=content_type,
                body=body,
                fetched_at=datetime.now(UTC),
                error=error,
            )
    return Page(url=requested, final_url=url, error="too many redirects")


async def _request(client: httpx.AsyncClient, url: str) -> tuple[int, str, str, str | None]:
    """One request, retried once on 429/5xx or a network error."""
    for attempt in (1, 2):
        try:
            async with client.stream("GET", url) as response:
                if response.status_code in (429, 500, 502, 503, 504) and attempt == 1:
                    await asyncio.sleep(min(float(response.headers.get("retry-after", 2)), 10))
                    continue
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_DOWNLOAD_BYTES:
                        break  # the model sees only the start of a page anyway
                location = response.headers.get("location") if response.is_redirect else None
                text = body.decode(response.encoding or "utf-8", errors="replace")
                return response.status_code, response.headers.get("content-type", ""), text, location
        except httpx.TransportError:
            if attempt == 2:
                raise
            await asyncio.sleep(2)
    raise AssertionError("unreachable")


async def _private_address(url: str) -> str | None:
    host = urlsplit(url).hostname or ""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, 443)
    except OSError:
        return None  # the request itself will fail with a clear error
    # ponytail: checked before the request, not pinned to it (DNS rebinding); fine for a read-only allowlist
    if any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        return f"host {host} resolves to a private address"
    return None


# --- What the model sees of a page -------------------------------------------


def page_text(page: Page) -> str:
    """The page as plain text for the model, cut to MAX_PAGE_CHARS with a visible marker."""
    if not page.ok:
        return f"Could not read {page.url}: {page.error}"
    text = html_to_text(page.body, page.final_url or page.url) if "html" in page.content_type else page.body
    if len(text) > MAX_PAGE_CHARS:
        text = text[:MAX_PAGE_CHARS] + f"\n[CUT: only the first {MAX_PAGE_CHARS} of {len(text)} characters shown]"
    return text


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "template", "head"}
    BLOCKS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "article", "section", "header", "time"}
    DATE_META = re.compile(r"published|modified|date", re.I)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.skipping = 0
        self.parts: list[str] = []
        self.links: list[str] = []
        self.meta: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and self.DATE_META.search(attrs.get("property") or attrs.get("name") or ""):
            self.meta.append(f"{attrs.get('property') or attrs.get('name')}={attrs.get('content')}")
        if tag in self.SKIP:
            self.skipping += 1
        elif tag == "a" and attrs.get("href", "").startswith(("http", "/")):
            self.links.append(urljoin(self.base_url, attrs["href"]))
        elif tag == "time" and attrs.get("datetime"):
            self.parts.append(f"[time {attrs['datetime']}] ")
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str, base_url: str) -> str:
    parser = _TextExtractor(base_url)
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", unescape("".join(parser.parts)))
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    meta = "Page date metadata: " + ", ".join(parser.meta) + "\n\n" if parser.meta else ""
    links = "\n\nLinks on the page:\n" + "\n".join(dict.fromkeys(parser.links[:80])) if parser.links else ""
    return meta + text + links
