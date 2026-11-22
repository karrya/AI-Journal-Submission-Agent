from uuid import uuid4

from app.automation.registration_browser import VisibleRegistrationBrowser
from app.automation.registration_adapters import LabelFormRegistrationAdapter
from app.automation.registration_contracts import RegistrationAutomationError, RegistrationData


class FakeVisibleBrowser:
    def __init__(self, *, intervene_on=None, account_id="account-123", fail_labels=False):
        self.intervene_on = intervene_on
        self.account_id = account_id
        self.fail_labels = fail_labels
        self.actions = []
        self.stopped_at = None
        self.submit_calls = 0
        self.browser_handoff_id = None

    def open(self, url):
        self.actions.append(("open", url))

    def fill(self, labels, value):
        if self.fail_labels:
            raise RegistrationAutomationError("FORM_FIELD_NOT_FOUND", labels[0])
        self.actions.append(("fill", labels, value))

    def click(self, labels):
        self.actions.append(("click", labels))
        if labels == ("Register", "Create Account"):
            self.submit_calls += 1

    def intervene(self, kind, checkpoint):
        self.stopped_at = kind
        self.browser_handoff_id = str(uuid4())
        return {
            "current_step": f"HANDOFF_{kind}",
            "browser_handoff_id": self.browser_handoff_id,
            **checkpoint,
        }

    def close(self):
        self.actions.append(("close",))

    def registration_account_id(self):
        return self.account_id


def data():
    return RegistrationData(
        task_id="task-1",
        login_name="synthetic-login",
        secret="classified-secret",
        profile={"given_name": "Ada", "family_name": "Lovelace"},
        portal_url="https://register.example/start",
        allowed_hosts=("register.example",),
        adapter_code="TEST_ADAPTER",
        adapter_version="1.0.0",
    )


def test_fills_database_values_and_returns_safe_receipt():
    browser = FakeVisibleBrowser()

    result = LabelFormRegistrationAdapter().execute(data(), browser, checkpoint=lambda value: None)

    assert result.status == "REGISTERED"
    assert result.checkpoint["external_evidence_ref"] == "account-123"
    assert "classified-secret" not in str(result.checkpoint)
    assert ("open", "https://register.example/start") in browser.actions
    assert ("fill", ("First Name", "Given Name"), "Ada") in browser.actions
    assert ("fill", ("Last Name", "Family Name"), "Lovelace") in browser.actions
    assert ("fill", ("Email",), "synthetic-login") in browser.actions
    assert ("fill", ("Password",), "classified-secret") in browser.actions
    assert browser.submit_calls == 1


def test_visible_steps_and_intervention_keep_handoff():
    browser = FakeVisibleBrowser(intervene_on="CAPTCHA")

    result = LabelFormRegistrationAdapter().execute(data(), browser, checkpoint=lambda value: None)

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_CAPTCHA"
    assert result.checkpoint["browser_handoff_id"]
    assert browser.stopped_at == "CAPTCHA"
    assert browser.submit_calls == 0
    assert "secret" not in result.checkpoint
    assert "classified-secret" not in str(result.checkpoint)


def test_unknown_submission_does_not_replay_final_action():
    browser = FakeVisibleBrowser(account_id=None)

    result = LabelFormRegistrationAdapter().execute(data(), browser, checkpoint=lambda value: None)

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "SUBMISSION_UNKNOWN"
    assert browser.submit_calls == 1


def test_missing_labels_become_manual_form_handoff():
    browser = FakeVisibleBrowser(fail_labels=True)

    result = LabelFormRegistrationAdapter().execute(data(), browser, checkpoint=lambda value: None)

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_FORM_CHANGED"
    assert result.checkpoint["browser_handoff_id"]
    assert browser.submit_calls == 0


def test_browser_uses_configured_chrome_channel(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_CHANNEL", "chrome")
    launches = []

    class FakeBrowser:
        def new_page(self):
            return object()

    class FakeChromium:
        def launch(self, **kwargs):
            launches.append(kwargs)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightManager:
        def start(self):
            return FakePlaywright()

    monkeypatch.setattr(
        "app.automation.registration_browser.sync_playwright",
        lambda: FakePlaywrightManager(),
    )
    browser = VisibleRegistrationBrowser(allowed_hosts=("register.example",))
    browser._start()

    assert launches == [{"headless": False, "channel": "chrome"}]
