from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin


@dataclass(frozen=True)
class PageLink:
    url: str
    text: str


@dataclass(frozen=True)
class ParsedPage:
    url: str
    title: str
    text: str
    links: tuple[PageLink, ...]
    requires_login: bool
    has_captcha: bool


@dataclass(frozen=True)
class DiscoveredLinks:
    guideline_urls: tuple[str, ...]
    submission_urls: tuple[str, ...]


class _PageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[PageLink] = []
        self._in_title = False
        self._skip_depth = 0
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self.has_password = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and attributes.get("href"):
            self._anchor_href = attributes["href"]
            self._anchor_text = []
        if tag == "input" and attributes.get("type", "").lower() == "password":
            self.has_password = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._anchor_href:
            text = " ".join(" ".join(self._anchor_text).split())
            self.links.append(
                PageLink(urljoin(self.base_url, self._anchor_href), text)
            )
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)
        if self._anchor_href:
            self._anchor_text.append(data)


def parse_page(html: str, url: str) -> ParsedPage:
    parser = _PageParser(url)
    parser.feed(html)
    parser.close()
    text = " ".join(" ".join(parser.text_parts).split())
    lowered = text.lower()
    requires_login = parser.has_password or any(
        marker in lowered for marker in ("sign in", "log in", "login", "登录")
    )
    has_captcha = any(
        marker in lowered
        for marker in ("captcha", "verify you are human", "人机验证", "验证码")
    )
    return ParsedPage(
        url=url,
        title=" ".join(" ".join(parser.title_parts).split()),
        text=text,
        links=tuple(parser.links),
        requires_login=requires_login,
        has_captcha=has_captcha,
    )


def discover_page_links(page: ParsedPage) -> DiscoveredLinks:
    guideline_markers = (
        "guide for authors",
        "author guidelines",
        "instructions for authors",
        "submission guidelines",
        "作者指南",
        "投稿指南",
        "投稿须知",
    )
    submission_markers = (
        "submit your article",
        "submit your manuscript",
        "submit manuscript",
        "online submission",
        "author login",
        "submit now",
        "投稿系统",
        "在线投稿",
    )
    guidelines = tuple(
        dict.fromkeys(
            link.url
            for link in page.links
            if any(marker in link.text.lower() for marker in guideline_markers)
        )
    )
    submissions = tuple(
        dict.fromkeys(
            link.url
            for link in page.links
            if any(marker in link.text.lower() for marker in submission_markers)
        )
    )
    return DiscoveredLinks(guideline_urls=guidelines, submission_urls=submissions)
