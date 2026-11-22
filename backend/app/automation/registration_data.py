import secrets
from typing import Protocol

import keyring
from sqlalchemy import select

from app.automation.registration_contracts import RegistrationAutomationError, RegistrationData
from app.models import Author, AuthorEmail, JournalSubmissionPortal

KEYCHAIN_SERVICE = "ai-journal-submission-agent"


class RegistrationCredentialStore(Protocol):
    def put(self, *, login_name: str, secret: str) -> str: ...

    def get(self, reference: str) -> str | None: ...

    def delete(self, reference: str) -> None: ...


class KeychainRegistrationCredentialStore:
    def put(self, *, login_name: str, secret: str) -> str:
        keyring.set_password(KEYCHAIN_SERVICE, login_name, secret)
        return login_name

    def get(self, reference: str) -> str | None:
        return keyring.get_password(KEYCHAIN_SERVICE, reference)

    def delete(self, reference: str) -> None:
        keyring.delete_password(KEYCHAIN_SERVICE, reference)


class RegistrationDataProvider:
    def __init__(self, *, store: RegistrationCredentialStore | None = None):
        self.store = store or KeychainRegistrationCredentialStore()

    def load(self, task, session) -> RegistrationData:
        author = session.get(Author, task.author_id)
        portal = session.get(JournalSubmissionPortal, task.portal_id)
        if author is None or portal is None:
            raise RegistrationAutomationError(
                "REGISTRATION_DATA_INCOMPLETE", "注册所需的作者或入口资料不完整"
            )
        registration_email = session.scalar(
            select(AuthorEmail)
            .where(
                AuthorEmail.author_id == task.author_id,
                AuthorEmail.purpose == "registration",
                AuthorEmail.authorization_status == "authorized",
                AuthorEmail.verification_status == "verified",
                AuthorEmail.deleted_at.is_(None),
            )
            .order_by(AuthorEmail.is_primary.desc(), AuthorEmail.created_at.asc())
            .limit(1)
        )
        if (
            registration_email is None
            or not author.given_name
            or not author.family_name
        ):
            raise RegistrationAutomationError(
                "REGISTRATION_DATA_INCOMPLETE", "注册所需的姓名或已授权注册邮箱不完整"
            )

        credential_reference = f"registration:{task.id}"
        secret = self.store.get(credential_reference)
        if secret is None:
            secret = secrets.token_urlsafe(24)
            self.store.put(login_name=credential_reference, secret=secret)
        return RegistrationData(
            task_id=task.id,
            login_name=registration_email.email,
            secret=secret,
            profile={
                "given_name": author.given_name,
                "middle_name": author.middle_name or "",
                "family_name": author.family_name,
                "display_name": author.display_name,
                "orcid": author.orcid or "",
            },
            portal_url=portal.final_url,
            allowed_hosts=tuple(portal.adapter_allowed_domains or []),
            adapter_code=portal.adapter_code,
            adapter_version=portal.adapter_version,
        )
