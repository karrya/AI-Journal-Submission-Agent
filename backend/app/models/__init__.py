from app.models.audit import OperationLog
from app.models.auth import AuthSession, Role, User, UserRole
from app.models.authors import (
    Author,
    AuthorAuthorization,
    AuthorEmail,
    AuthorInstitution,
    Institution,
)
from app.models.base import Base, new_uuid, utc_now
from app.models.discovery import (
    DiscoveryTask,
    JournalDiscoveryLog,
    JournalSourceSnapshot,
    JournalSubmissionPortal,
)
from app.models.files import FileFamily, ManuscriptFile
from app.models.journals import (
    Journal,
    JournalAlias,
    JournalIdentifier,
    JournalPlatform,
    Publisher,
    PublisherAlias,
)
from app.models.manuscripts import Manuscript, ManuscriptAuthor, ManuscriptVersion
from app.models.registration import (
    EmailVerificationRecord,
    PlatformAdapter,
    PublisherAccount,
    PublisherRegistrationSupport,
    RegistrationConfirmation,
    RegistrationTask,
)

__all__ = [
    "Author",
    "AuthorAuthorization",
    "AuthorEmail",
    "AuthorInstitution",
    "AuthSession",
    "Base",
    "DiscoveryTask",
    "EmailVerificationRecord",
    "FileFamily",
    "Institution",
    "Journal",
    "JournalAlias",
    "JournalDiscoveryLog",
    "JournalIdentifier",
    "JournalSourceSnapshot",
    "JournalSubmissionPortal",
    "JournalPlatform",
    "Manuscript",
    "ManuscriptAuthor",
    "ManuscriptFile",
    "ManuscriptVersion",
    "OperationLog",
    "PlatformAdapter",
    "Publisher",
    "PublisherAccount",
    "PublisherAlias",
    "PublisherRegistrationSupport",
    "RegistrationConfirmation",
    "RegistrationTask",
    "Role",
    "User",
    "UserRole",
    "new_uuid",
    "utc_now",
]
