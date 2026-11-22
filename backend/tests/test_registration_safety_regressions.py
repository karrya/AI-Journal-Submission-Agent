from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.automation.registration_adapters import LabelFormRegistrationAdapter
from app.automation.registration_browser import VisibleRegistrationBrowser
from app.automation.registration_contracts import RegistrationAutomationError, RegistrationData
from app.automation.registration_executor import RegistrationAutomationExecutor
from app.core.errors import AppError
from app.models import RegistrationTask
from app.services.registration_workflow import RegistrationWorkflowService


class SafetyBrowser:
    def __init__(self, *, account_id=None):
        self.account_id = account_id
        self.stage = ""
        self.events = []
        self.intervene_on = None
        self.open_calls = 0
        self.submit_calls = 0
        self.closed = False

    def open(self, url):
        self.open_calls += 1
        self.events.append("open")

    def fill(self, labels, value):
        self.events.append(f"fill:{labels[0]}")

    def click(self, labels):
        self.submit_calls += 1
        self.events.append("click")

    def intervene(self, kind, checkpoint):
        return {
            "current_step": f"HANDOFF_{kind}",
            "browser_handoff_id": str(uuid4()),
            **checkpoint,
        }

    def registration_account_id(self):
        return self.account_id

    def close(self):
        self.closed = True


def registration_data():
    return RegistrationData(
        task_id="task-safety",
        login_name="synthetic-login",
        secret="classified-secret",
        profile={"given_name": "Ada", "family_name": "Lovelace"},
        portal_url="https://register.example/start",
        allowed_hosts=("register.example",),
        adapter_code="TEST_ADAPTER",
        adapter_version="1.0.0",
    )


def test_final_click_marker_is_saved_before_click_and_unknown_is_final():
    browser = SafetyBrowser(account_id="account-1")
    checkpoints = []

    result = LabelFormRegistrationAdapter().execute(
        registration_data(), browser, checkpoints.append
    )

    click_index = browser.events.index("click")
    assert click_index > 0
    assert any(
        checkpoint.get("last_external_action") == "SUBMITTING"
        for checkpoint in checkpoints
    )
    assert result.checkpoint["last_external_action"] == "SUBMITTING"


def test_unknown_result_uses_handoff_and_never_allows_replay():
    browser = SafetyBrowser(account_id=None)

    result = LabelFormRegistrationAdapter().execute(
        registration_data(), browser, lambda value: None
    )

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_SUBMISSION_UNKNOWN"
    assert result.checkpoint["last_external_action"] == "SUBMISSION_UNKNOWN"
    assert result.checkpoint["browser_handoff_id"]
    assert "classified-secret" not in str(result.checkpoint)


def test_post_submit_captcha_keeps_marked_handoff_without_replay():
    class ChallengeAfterClickBrowser(SafetyBrowser):
        def click(self, labels):
            super().click(labels)
            self.intervene_on = "CAPTCHA"

    browser = ChallengeAfterClickBrowser(account_id="account-after-captcha")

    result = LabelFormRegistrationAdapter().execute(
        registration_data(), browser, lambda value: None
    )

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_CAPTCHA"
    assert result.checkpoint["last_external_action"] == "SUBMITTING"
    assert result.checkpoint["browser_handoff_id"]
    assert browser.submit_calls == 1


def test_cancel_during_browser_step_closes_browser():
    browser = SafetyBrowser()
    executor = RegistrationAutomationExecutor(
        preflight=SimpleNamespace(evaluate=lambda portal: LabelFormRegistrationAdapter()),
        provider=SimpleNamespace(load=lambda task, session: registration_data()),
        adapters=SimpleNamespace(),
        browser_factory=lambda **kwargs: browser,
    )
    task = SimpleNamespace(
        id="task-safety",
        portal_id="portal-1",
        current_step=None,
        browser_handoff_id=None,
    )
    portal = SimpleNamespace(final_url="https://register.example/start")
    session = SimpleNamespace(get=lambda model, key: portal)

    from app.workers.registration_worker import TaskCancelled

    with pytest.raises(TaskCancelled):
        executor.execute(task, session, lambda value: (_ for _ in ()).throw(TaskCancelled()))
    assert browser.closed is True



def test_cross_origin_form_action_is_rejected_before_click():
    browser = VisibleRegistrationBrowser(allowed_hosts=("register.example",))

    class Button:
        def evaluate(self, script):
            return "https://outside.example/register"

        def click(self):
            raise AssertionError("cross-origin form must not be clicked")

    class Locator:
        def count(self):
            return 1

        @property
        def first(self):
            return Button()

    class Page:
        url = "https://register.example/start"

        def get_by_role(self, role, **kwargs):
            return Locator()

    browser._page = Page()
    with pytest.raises(RegistrationAutomationError) as error:
        browser.click(("Register",))
    assert error.value.code == "PLATFORM_DOMAIN_NOT_ALLOWED"


def test_request_guard_blocks_cross_origin_post_before_network():
    browser = VisibleRegistrationBrowser(allowed_hosts=("register.example",))

    class Route:
        request = SimpleNamespace(url="https://outside.example/register")
        aborted = False
        continued = False

        def abort(self):
            self.aborted = True

        def continue_(self):
            self.continued = True

    route = Route()
    browser._guard_request(route)

    assert route.aborted is True
    assert route.continued is False



def test_resume_does_not_reload_or_click_again():
    browser = SafetyBrowser(account_id="account-resumed")
    browser.stage = "SUBMITTED_PENDING_RESULT"

    result = LabelFormRegistrationAdapter().resume(
        registration_data(), browser, lambda value: None
    )

    assert result.status == "REGISTERED"
    assert browser.open_calls == 0
    assert browser.submit_calls == 0


def test_missing_handoff_session_does_not_restart_browser():
    portal = SimpleNamespace(
        final_url="https://register.example/start",
        adapter_code="TEST_ADAPTER",
        adapter_version="1.0.0",
    )
    task = SimpleNamespace(
        id="task-safety",
        portal_id="portal-1",
        current_step="HANDOFF_CAPTCHA",
        browser_handoff_id="missing-handoff",
    )
    provider = SimpleNamespace(load=lambda task, session: registration_data())
    adapter = LabelFormRegistrationAdapter()
    preflight = SimpleNamespace(evaluate=lambda portal: adapter)
    executor = RegistrationAutomationExecutor(
        preflight=preflight,
        provider=provider,
        adapters=SimpleNamespace(),
        browser_factory=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("missing handoff must not open a new browser")
        ),
    )
    session = SimpleNamespace(get=lambda model, key: portal)

    result = executor.execute(task, session, lambda value: None)

    assert result.status == "NEEDS_MANUAL_REVIEW"
    assert result.checkpoint["current_step"] == "HANDOFF_SESSION_EXPIRED"


def test_nonresumable_robots_and_resumed_checkpoint_are_not_requeued():
    task = RegistrationTask(
        task_status="NEEDS_MANUAL_REVIEW",
        current_step="HANDOFF_ROBOTS",
    )
    with pytest.raises(AppError, match="人工接管"):
        RegistrationWorkflowService().resume_handoff(task, actor_id="user-1")

    task.current_step = "HANDOFF_CAPTCHA"
    result = RegistrationWorkflowService().resume_handoff(task, actor_id="user-1")
    assert result.task_status == "PENDING"
    assert result.current_step == "RESUMING"
