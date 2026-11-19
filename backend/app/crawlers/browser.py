import hashlib
import os
from urllib.parse import urlsplit

from app.crawlers.url_security import FetchResult, SafeHttpClient, UrlSecurityError, UrlSecurityPolicy


class PlaywrightBrowserClient:
    def __init__(self, *, timeout_ms: int = 30000, max_bytes: int = 2_000_000):
        self.timeout_ms = timeout_ms
        self.max_bytes = max_bytes
        self.policy = UrlSecurityPolicy()
        self.http_client = SafeHttpClient()

    def get(self, url: str) -> FetchResult:
        resolved = self.policy.resolve(url)
        self.http_client.assert_allowed(url)
        pinned_host = resolved.host
        pinned_ip = resolved.ip_addresses[0]
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise UrlSecurityError("JavaScript 浏览器依赖未安装") from exc
        try:
            with sync_playwright() as playwright:
                channel = os.environ.get("PLAYWRIGHT_CHROMIUM_CHANNEL", "chrome")
                launch_args = [
                    f"--host-resolver-rules=MAP {pinned_host} {pinned_ip},MAP * 0.0.0.0",
                    "--no-proxy-server",
                ]
                try:
                    browser = playwright.chromium.launch(
                        headless=True, channel=channel, args=launch_args
                    )
                except Exception:
                    browser = playwright.chromium.launch(headless=True, args=launch_args)
                try:
                    context = browser.new_context(
                        accept_downloads=False,
                        ignore_https_errors=False,
                        java_script_enabled=True,
                    )
                    page = context.new_page()

                    def guard(route):
                        target = route.request.url
                        target_host = (urlsplit(target).hostname or "").lower().rstrip(".")
                        if target_host != pinned_host:
                            route.abort()
                            return
                        if not target.lower().startswith(("http://", "https://")):
                            route.abort()
                            return
                        try:
                            self.policy.resolve(target)
                            self.http_client.assert_allowed(target)
                        except UrlSecurityError:
                            route.abort()
                        else:
                            route.continue_()

                    page.route("**/*", guard)
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )
                    page.wait_for_timeout(500)
                    final_url = page.url
                    if (urlsplit(final_url).hostname or "").lower().rstrip(".") != pinned_host:
                        raise UrlSecurityError("浏览器重定向到了未固定的主机")
                    self.policy.resolve(final_url)
                    html = page.content()
                    body = html.encode("utf-8")
                    if len(body) > self.max_bytes:
                        raise UrlSecurityError("页面超过大小限制")
                    headers = dict(response.headers) if response else {}
                    return FetchResult(
                        final_url=final_url,
                        status=response.status if response else 200,
                        headers={key.lower(): value for key, value in headers.items()},
                        body=body,
                        text=html,
                        redirects=(),
                        content_sha256=hashlib.sha256(body).hexdigest(),
                    )
                finally:
                    browser.close()
        except UrlSecurityError:
            raise
        except Exception as exc:
            raise UrlSecurityError("JavaScript 页面访问失败") from exc
