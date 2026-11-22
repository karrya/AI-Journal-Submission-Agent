from app.automation.registration_contracts import RegistrationAutomationError, RegistrationReceipt


class LabelFormRegistrationAdapter:
    def execute(self, data, browser, checkpoint):
        checkpoint({"current_step": "OPENING_PORTAL"})
        browser.open(data.portal_url)
        intervention = browser.intervene_on
        if intervention:
            return RegistrationReceipt(
                "NEEDS_MANUAL_REVIEW",
                browser.intervene(intervention, {"manual_url": data.portal_url}),
            )
        try:
            checkpoint({"current_step": "FILLING_IDENTITY"})
            browser.fill(("First Name", "Given Name"), data.profile["given_name"])
            browser.fill(("Last Name", "Family Name"), data.profile["family_name"])
            checkpoint({"current_step": "FILLING_ACCOUNT"})
            browser.fill(("Email",), data.login_name)
            browser.fill(("Password",), data.secret)
            browser.fill(("Confirm Password", "Password Confirmation"), data.secret)
            checkpoint({"current_step": "SUBMITTING_REGISTRATION"})
            browser.click(("Register", "Create Account"))
        except RegistrationAutomationError:
            return RegistrationReceipt(
                "NEEDS_MANUAL_REVIEW",
                browser.intervene("FORM_CHANGED", {"manual_url": data.portal_url}),
            )

        account_id = browser.registration_account_id()
        if not account_id:
            return RegistrationReceipt(
                "NEEDS_MANUAL_REVIEW",
                {"current_step": "SUBMISSION_UNKNOWN", "manual_url": data.portal_url},
            )
        return RegistrationReceipt(
            "REGISTERED",
            {"current_step": "COMPLETED", "external_evidence_ref": account_id},
        )
