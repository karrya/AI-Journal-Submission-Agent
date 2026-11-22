from app.automation.registration_browser import VisibleRegistrationBrowser
from app.automation.registration_contracts import (
    RegistrationAutomationError,
    RegistrationReceipt,
    registration_handoff,
)
from app.models import JournalSubmissionPortal
from app.workers.registration_worker import (
    RegistrationExecutionError,
    RegistrationExecutionResult,
    TaskCancelled,
    TaskLeaseLost,
)


class RegistrationAutomationExecutor:
    def __init__(
        self,
        *,
        preflight,
        provider,
        adapters,
        browser_factory=VisibleRegistrationBrowser,
        url_checker=None,
    ):
        self.preflight = preflight
        self.provider = provider
        self.adapters = adapters
        self.browser_factory = browser_factory
        self.url_checker = url_checker
        self._handoffs = {}

    def execute(self, task, session, checkpoint_callback):
        portal = session.get(JournalSubmissionPortal, task.portal_id)
        try:
            data = self.provider.load(task, session)
            decision = self.preflight.evaluate(portal)
        except RegistrationAutomationError as exc:
            if exc.retryable:
                raise RegistrationExecutionError(
                    str(exc), retryable=True, code=exc.code
                ) from exc
            step = {
                "ADAPTER_NOT_REGISTERED": "HANDOFF_ADAPTER_NOT_REGISTERED",
                "REGISTRATION_DATA_INCOMPLETE": "HANDOFF_DATA_INCOMPLETE",
            }.get(exc.code, "HANDOFF_PREFLIGHT")
            return registration_handoff(step, portal.final_url)
        if isinstance(decision, RegistrationReceipt):
            return RegistrationExecutionResult(decision.status, decision.checkpoint)

        handoff_id = task.browser_handoff_id
        if handoff_id and handoff_id not in self._handoffs:
            return registration_handoff("HANDOFF_SESSION_EXPIRED", data.portal_url)
        browser = None
        try:
            if handoff_id in self._handoffs:
                browser = self._handoffs[handoff_id][0]
            else:
                browser = self.browser_factory(
                    allowed_hosts=data.allowed_hosts,
                    headless=False,
                    url_checker=self.url_checker,
                )
            if handoff_id in self._handoffs:
                receipt = decision.resume(data, browser, checkpoint_callback)
            else:
                receipt = decision.execute(data, browser, checkpoint_callback)
        except (TaskCancelled, TaskLeaseLost):
            if browser is not None:
                browser.close()
            self._handoffs.pop(handoff_id, None)
            raise
        except RegistrationAutomationError as exc:
            if exc.retryable:
                if browser is not None:
                    browser.close()
                self._handoffs.pop(handoff_id, None)
                raise RegistrationExecutionError(
                    str(exc), retryable=True, code=exc.code
                ) from exc
            return self._browser_handoff(data, browser, "BROWSER_ERROR", handoff_id)
        except Exception:
            if browser is not None and getattr(browser, "stage", "") in {
                "SUBMITTING_REGISTRATION",
                "SUBMITTED_PENDING_RESULT",
            }:
                browser.close()
                self._handoffs.pop(handoff_id, None)
                return registration_handoff(
                    "HANDOFF_SUBMISSION_UNKNOWN",
                    data.portal_url,
                    last_external_action="SUBMISSION_UNKNOWN",
                )
            return self._browser_handoff(data, browser, "BROWSER_ERROR", handoff_id)

        if receipt.status == "NEEDS_MANUAL_REVIEW":
            new_handoff_id = receipt.checkpoint.get("browser_handoff_id")
            if new_handoff_id and not receipt.retryable:
                self._handoffs.pop(handoff_id, None)
                self._handoffs[new_handoff_id] = (browser, decision)
            else:
                browser.close()
                self._handoffs.pop(handoff_id, None)
        else:
            browser.close()
            self._handoffs.pop(handoff_id, None)
        return RegistrationExecutionResult(receipt.status, receipt.checkpoint)

    def _browser_handoff(self, data, browser, kind, previous_handoff_id):
        if browser is None:
            return registration_handoff(f"HANDOFF_{kind}", data.portal_url)
        receipt = registration_handoff(
            f"HANDOFF_{kind}",
            data.portal_url,
            browser_handoff_id=previous_handoff_id or None,
        )
        self._handoffs.pop(previous_handoff_id, None)
        self._handoffs[receipt.checkpoint["browser_handoff_id"]] = (browser, None)
        return receipt
