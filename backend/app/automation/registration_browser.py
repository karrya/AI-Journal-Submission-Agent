import os
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

from playwright.sync_api import sync_playwright

from app.automation.registration_contracts import RegistrationAutomationError


class VisibleRegistrationBrowser:
    def __init__(self, *, allowed_hosts=(), headless=False, url_checker=None):
        self.allowed_hosts = {host.lower().rstrip(".") for host in allowed_hosts}
        self.headless = headless
        self.url_checker = url_checker
        self.stage = ""
        self._playwright = None
        self._browser = None
        self._page = None

    def _start(self):
        if self._page is not None:
            return
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            channel=os.environ.get("PLAYWRIGHT_CHROMIUM_CHANNEL", "chrome"),
        )
        self._page = self._browser.new_page()
        self._page.route("**/*", self._guard_request)

    def _assert_allowed(self, url):
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme.lower() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or host not in self.allowed_hosts
        ):
            raise RegistrationAutomationError(
                "PLATFORM_DOMAIN_NOT_ALLOWED", "目标域名不在适配器白名单"
            )

    def _guard_request(self, route):
        try:
            self._assert_allowed(route.request.url)
        except RegistrationAutomationError:
            route.abort()
            return
        route.continue_()

    def open(self, url):
        self._assert_allowed(url)
        self._start()
        self._page.goto(url, wait_until="domcontentloaded")
        self._assert_allowed(self._page.url)
        if self.url_checker is not None:
            self.url_checker.assert_allowed(self._page.url)

    def fill(self, labels, value):
        self._assert_allowed(self._page.url)
        for label in labels:
            field = self._page.get_by_label(label, exact=False)
            if field.count():
                field.first.fill(value)
                return
        raise RegistrationAutomationError("FORM_FIELD_NOT_FOUND", labels[0])

    def click(self, labels):
        for label in labels:
            button = self._page.get_by_role("button", name=label, exact=False)
            if button.count():
                action = button.first.evaluate(
                    """button => button.getAttribute('formaction')
                        || button.form?.getAttribute('action')
                        || window.location.href"""
                )
                self._assert_allowed(urljoin(self._page.url, action))
                button.first.click()
                return
        raise RegistrationAutomationError("FORM_ACTION_NOT_FOUND", labels[0])

    @property
    def intervene_on(self):
        text = self._page.locator("body").inner_text().lower()
        if "captcha" in text:
            return "CAPTCHA"
        if any(marker in text for marker in ("mfa", "2fa", "verification code", "多因素", "验证码")):
            return "MFA"
        return None

    def intervene(self, kind, checkpoint):
        return {
            "current_step": f"HANDOFF_{kind}",
            "browser_handoff_id": str(uuid4()),
            **checkpoint,
        }

    def registration_account_id(self):
        marker = self._page.locator("[data-account-id]")
        if not marker.count():
            return None
        return marker.first.get_attribute("data-account-id")

    def close(self):
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._page = None
