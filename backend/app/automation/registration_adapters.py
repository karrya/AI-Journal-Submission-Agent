from app.automation.registration_contracts import (
    RegistrationAutomationError,
    RegistrationReceipt,
    registration_handoff,
)


class LabelFormRegistrationAdapter:
    def execute(self, data, browser, checkpoint):
        checkpoint({"current_step": "OPENING_PORTAL"})
        browser.open(data.portal_url)
        browser.stage = "OPENED"
        return self._continue(data, browser, checkpoint)

    def resume(self, data, browser, checkpoint):
        return self._continue(data, browser, checkpoint)

    def _continue(self, data, browser, checkpoint):
        intervention = browser.intervene_on
        if intervention:
            return self._intervene(data, browser, intervention)
        if browser.stage == "SUBMITTING_REGISTRATION":
            return self._unknown(data)
        if browser.stage == "SUBMITTED_PENDING_RESULT":
            return self._result(data, browser)

        try:
            checkpoint({"current_step": "FILLING_IDENTITY"})
            browser.fill(("First Name", "Given Name"), data.profile["given_name"])
            browser.fill(("Last Name", "Family Name"), data.profile["family_name"])
            checkpoint({"current_step": "FILLING_ACCOUNT"})
            browser.fill(("Email",), data.login_name)
            browser.fill(("Password",), data.secret)
            browser.fill(("Confirm Password", "Password Confirmation"), data.secret)
            browser.stage = "FORM_FILLED"
            checkpoint({
                "current_step": "SUBMITTING_REGISTRATION",
                "last_external_action": "SUBMITTING",
            })
            browser.stage = "SUBMITTING_REGISTRATION"
            browser.click(("Register", "Create Account"))
            browser.stage = "SUBMITTED_PENDING_RESULT"
        except RegistrationAutomationError as exc:
            if exc.retryable:
                raise
            if browser.stage in {"SUBMITTING_REGISTRATION", "SUBMITTED_PENDING_RESULT"}:
                return self._unknown(data)
            return self._intervene(data, browser, "FORM_CHANGED")
        intervention = browser.intervene_on
        if intervention:
            return self._intervene(
                data,
                browser,
                intervention,
                last_external_action="SUBMITTING",
            )
        return self._result(data, browser)

    def _result(self, data, browser):
        account_id = browser.registration_account_id()
        if not account_id:
            return self._unknown(data)
        return RegistrationReceipt(
            "REGISTERED",
            {
                "current_step": "COMPLETED",
                "external_evidence_ref": account_id,
                "last_external_action": "SUBMITTING",
            },
        )

    def _intervene(self, data, browser, kind, *, last_external_action=None):
        checkpoint = {"manual_url": data.portal_url}
        if last_external_action is not None:
            checkpoint["last_external_action"] = last_external_action
        return RegistrationReceipt(
            "NEEDS_MANUAL_REVIEW",
            browser.intervene(kind, checkpoint),
        )

    def _unknown(self, data):
        return registration_handoff(
            "HANDOFF_SUBMISSION_UNKNOWN",
            data.portal_url,
            last_external_action="SUBMISSION_UNKNOWN",
        )
