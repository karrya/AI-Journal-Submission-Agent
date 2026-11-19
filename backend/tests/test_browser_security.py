from types import SimpleNamespace

from app.crawlers.browser import PlaywrightBrowserClient
from app.crawlers.url_security import ResolvedUrl


class FakeRoute:
    def __init__(self, url):
        self.request = SimpleNamespace(url=url)
        self.actions = []

    def abort(self):
        self.actions.append("abort")

    def continue_(self):
        self.actions.append("continue")


class FakePage:
    def __init__(self, url):
        self.url = url
        self.guard = None

    def route(self, pattern, guard):
        self.guard = guard

    def goto(self, url, **kwargs):
        return SimpleNamespace(status=200, headers={})

    def wait_for_timeout(self, milliseconds):
        return None

    def content(self):
        return "<title>Example</title>"


class FakeBrowser:
    def __init__(self, url):
        self.page = FakePage(url)

    def new_context(self, **kwargs):
        return SimpleNamespace(new_page=lambda: self.page)

    def close(self):
        return None


class FakePlaywrightManager:
    def __init__(self, chromium):
        self.chromium = chromium

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_browser_pins_dns_and_blocks_unmapped_hosts(monkeypatch):
    launches = []
    browser = FakeBrowser("https://example.com")
    chromium = SimpleNamespace(
        launch=lambda **kwargs: launches.append(kwargs) or browser
    )
    manager = FakePlaywrightManager(chromium)
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: manager,
    )
    client = PlaywrightBrowserClient()
    client.http_client = SimpleNamespace(assert_allowed=lambda url: None)
    resolved = ResolvedUrl(
        url="https://example.com",
        host="example.com",
        port=443,
        ip_addresses=("93.184.216.34",),
        scheme="https",
    )
    monkeypatch.setattr(client.policy, "resolve", lambda url: resolved)
    client.get("https://example.com")
    arguments = launches[0]["args"]
    assert any("MAP example.com 93.184.216.34" in argument for argument in arguments)
    assert "--no-proxy-server" in arguments

    external = FakeRoute("https://other.example/resource")
    browser.page.guard(external)
    assert external.actions == ["abort"]
