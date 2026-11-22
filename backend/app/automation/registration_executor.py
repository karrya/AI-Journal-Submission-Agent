from app.automation.registration_browser import VisibleRegistrationBrowser
from app.automation.registration_contracts import RegistrationAutomationError, RegistrationReceipt
from app.models import JournalSubmissionPortal
from app.workers.registration_worker import RegistrationExecutionResult


class RegistrationAutomationExecutor:
    def __init__(
        self,
        *,
        preflight,
        provider,
        adapters,
        browser_factory=VisibleRegistrationBrowser,
    ):
        self.preflight = preflight
        self.provider = provider
        self.adapters = adapters
        self.browser_factory = browser_factory
        self._handoffs = {}

    def execute(self, task, session, checkpoint_callback):
        portal = session.get(JournalSubmissionPortal, task.portal_id)
        try:
            data = self.provider.load(task, session)
            decision = self.preflight.evaluate(portal)
        except RegistrationAutomationError as exc:
            return RegistrationExecutionResult(
                "NEEDS_MANUAL_REVIEW",
                {
                    "current_step": exc.code,
                    "manual_url": portal.final_url,
                },
            )
        if isinstance(decision, RegistrationReceipt):
            return RegistrationExecutionResult(decision.status, decision.checkpoint)

        handoff_id = task.browser_handoff_id
        if handoff_id in self._handoffs:
            browser = self._handoffs[handoff_id][0]
        else:
            browser = self.browser_factory(
                allowed_hosts=data.allowed_hosts,
                headless=False,
            )
        receipt = decision.execute(data, browser, checkpoint_callback)
        if receipt.status == "NEEDS_MANUAL_REVIEW":
            new_handoff_id = receipt.checkpoint.get("browser_handoff_id")
            if new_handoff_id:
                self._handoffs[new_handoff_id] = (browser, decision)
            else:
                browser.close()
        else:
            browser.close()
        return RegistrationExecutionResult(receipt.status, receipt.checkpoint)
