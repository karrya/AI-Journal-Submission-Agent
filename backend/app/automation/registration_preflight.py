from urllib.parse import urlsplit

from app.automation.registration_contracts import (
    RegistrationAdapter,
    RegistrationAutomationError,
    RegistrationReceipt,
)
from app.crawlers.url_security import UrlSecurityError


class RegistrationAdapterRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, code: str, version: str, adapter: RegistrationAdapter) -> None:
        self._adapters[(code, version)] = adapter

    def get(self, code: str, version: str) -> RegistrationAdapter:
        try:
            return self._adapters[(code, version)]
        except KeyError:
            raise RegistrationAutomationError(
                "ADAPTER_NOT_REGISTERED", "平台适配器尚未注册"
            ) from None


class RegistrationPreflight:
    def __init__(self, *, adapters, url_checker):
        self.adapters = adapters
        self.url_checker = url_checker

    def evaluate(self, portal):
        adapter = self.adapters.get(portal.adapter_code, portal.adapter_version)
        try:
            parsed = urlsplit(portal.final_url)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            raise RegistrationAutomationError(
                "PLATFORM_DOMAIN_NOT_ALLOWED", "目标入口 URL 或端口不受信任"
            ) from None
        allowed_hosts = {
            str(domain).lower().rstrip(".") for domain in portal.adapter_allowed_domains or []
        }
        if (
            parsed.scheme.lower() != "https"
            or port not in {None, 443}
            or not host
            or host != (portal.normalized_host or "").lower().rstrip(".")
            or host not in allowed_hosts
        ):
            raise RegistrationAutomationError(
                "PLATFORM_DOMAIN_NOT_ALLOWED", "目标域名不在适配器白名单"
            )
        try:
            self.url_checker.assert_allowed(portal.final_url)
        except UrlSecurityError:
            return RegistrationReceipt(
                "NEEDS_MANUAL_REVIEW",
                {
                    "current_step": "HANDOFF_ROBOTS",
                    "manual_url": portal.final_url,
                },
            )
        return adapter
