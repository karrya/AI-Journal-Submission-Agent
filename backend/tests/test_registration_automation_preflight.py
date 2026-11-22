from types import SimpleNamespace

import pytest

from app.automation.registration_preflight import RegistrationAdapterRegistry, RegistrationPreflight
from app.automation.registration_contracts import RegistrationAutomationError
from app.crawlers.url_security import UrlSecurityError


class FakeUrlChecker:
    def __init__(self, *, allowed: bool):
        self.allowed = allowed
        self.calls = []

    def assert_allowed(self, url: str) -> None:
        self.calls.append(url)
        if not self.allowed:
            raise UrlSecurityError("robots 规则禁止访问该路径")


def portal(**overrides):
    values = {
        "final_url": "https://wiley.atyponrex.com/journal/APEC",
        "normalized_host": "wiley.atyponrex.com",
        "adapter_code": "TEST_ADAPTER",
        "adapter_version": "1.0.0",
        "adapter_allowed_domains": ["wiley.atyponrex.com"],
        "platform_code": "WILEY_RESEARCH_EXCHANGE",
    }
    return SimpleNamespace(**(values | overrides))


def test_apec_returns_manual_handoff_without_opening_browser():
    registry = RegistrationAdapterRegistry()
    registry.register("TEST_ADAPTER", "1.0.0", object())
    checker = FakeUrlChecker(allowed=False)
    preflight = RegistrationPreflight(adapters=registry, url_checker=checker)

    result = preflight.evaluate(portal())

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_ROBOTS"
    assert result.checkpoint["manual_url"] == portal().final_url
    assert checker.calls == [portal().final_url]


def test_missing_adapter_cannot_be_fabricated():
    with pytest.raises(RegistrationAutomationError) as error:
        RegistrationAdapterRegistry().get("WILEY_RESEARCH_EXCHANGE", "1.0.0")

    assert error.value.code == "ADAPTER_NOT_REGISTERED"


def test_allowed_target_returns_exact_registered_adapter():
    adapter = object()
    registry = RegistrationAdapterRegistry()
    registry.register("TEST_ADAPTER", "1.0.0", adapter)
    checker = FakeUrlChecker(allowed=True)
    preflight = RegistrationPreflight(adapters=registry, url_checker=checker)

    assert preflight.evaluate(portal()) is adapter
    assert checker.calls == [portal().final_url]
