from dataclasses import dataclass


@dataclass(frozen=True)
class RouteContract:
    method: str
    path: str
    response_schema: str


CONTRACTS: tuple[RouteContract, ...] = (
    RouteContract("GET", "/health", "HealthResponse"),
    RouteContract("GET", "/health/ready", "HealthResponse"),
    RouteContract("POST", "/auth/login", "LoginResponse"),
    RouteContract("POST", "/auth/logout", "None"),
    RouteContract("GET", "/auth/me", "UserResponse"),
    RouteContract("GET", "/auth/csrf", "CsrfResponse"),
    RouteContract("POST", "/auth/change-password", "None"),
    RouteContract("GET", "/authors", "AuthorPage"),
    RouteContract("POST", "/authors", "AuthorResponse"),
    RouteContract("GET", "/authors/{author_id}", "AuthorResponse"),
    RouteContract("PATCH", "/authors/{author_id}", "AuthorResponse"),
    RouteContract("DELETE", "/authors/{author_id}", "None"),
    RouteContract("GET", "/authors/{author_id}/emails", "EmailPage"),
    RouteContract("POST", "/authors/{author_id}/emails", "EmailResponse"),
    RouteContract("PATCH", "/authors/{author_id}/emails/{email_id}", "EmailResponse"),
    RouteContract("DELETE", "/authors/{author_id}/emails/{email_id}", "None"),
    RouteContract("GET", "/institutions", "InstitutionPage"),
    RouteContract("POST", "/institutions", "InstitutionResponse"),
    RouteContract("GET", "/institutions/{institution_id}", "InstitutionResponse"),
    RouteContract("PATCH", "/institutions/{institution_id}", "InstitutionResponse"),
    RouteContract("DELETE", "/institutions/{institution_id}", "None"),
    RouteContract("GET", "/authors/{author_id}/institutions", "AuthorInstitutionPage"),
    RouteContract("POST", "/authors/{author_id}/institutions", "AuthorInstitutionResponse"),
    RouteContract(
        "PATCH",
        "/authors/{author_id}/institutions/{link_id}",
        "AuthorInstitutionResponse",
    ),
    RouteContract("DELETE", "/authors/{author_id}/institutions/{link_id}", "None"),
    RouteContract("GET", "/author-authorizations/options", "AuthorizationOptionsResponse"),
    RouteContract("GET", "/author-authorizations", "AuthorizationPage"),
    RouteContract("POST", "/author-authorizations", "AuthorizationResponse"),
    RouteContract(
        "GET", "/author-authorizations/{authorization_id}", "AuthorizationResponse"
    ),
    RouteContract(
        "PATCH", "/author-authorizations/{authorization_id}", "AuthorizationResponse"
    ),
    RouteContract(
        "POST",
        "/author-authorizations/{authorization_id}/revoke",
        "AuthorizationResponse",
    ),
    RouteContract("GET", "/manuscripts", "ManuscriptPage"),
    RouteContract("POST", "/manuscripts", "ManuscriptResponse"),
    RouteContract("GET", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    RouteContract("PATCH", "/manuscripts/{manuscript_id}", "ManuscriptResponse"),
    RouteContract("DELETE", "/manuscripts/{manuscript_id}", "None"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    RouteContract("PUT", "/manuscripts/{manuscript_id}/authors", "ManuscriptAuthorList"),
    RouteContract("GET", "/manuscripts/{manuscript_id}/versions", "ManuscriptVersionPage"),
    RouteContract(
        "POST", "/manuscripts/{manuscript_id}/versions", "ManuscriptVersionResponse"
    ),
    RouteContract(
        "GET",
        "/manuscripts/{manuscript_id}/versions/{version_id}",
        "ManuscriptVersionResponse",
    ),
    RouteContract(
        "GET", "/manuscripts/{manuscript_id}/versions/{version_id}/files", "FilePage"
    ),
    RouteContract(
        "POST",
        "/manuscripts/{manuscript_id}/versions/{version_id}/files",
        "FileResponse",
    ),
    RouteContract("GET", "/files/{file_id}", "FileResponse"),
    RouteContract("GET", "/files/{file_id}/download", "FileContent"),
    RouteContract("DELETE", "/files/{file_id}", "None"),
    RouteContract("GET", "/publishers", "PublisherPage"),
    RouteContract("POST", "/publishers", "PublisherResponse"),
    RouteContract("GET", "/publishers/{publisher_id}", "PublisherResponse"),
    RouteContract("PATCH", "/publishers/{publisher_id}", "PublisherResponse"),
    RouteContract("DELETE", "/publishers/{publisher_id}", "None"),
    RouteContract("GET", "/journal-platforms", "JournalPlatformPage"),
    RouteContract("POST", "/journal-platforms", "JournalPlatformResponse"),
    RouteContract("GET", "/journal-platforms/{platform_id}", "JournalPlatformResponse"),
    RouteContract(
        "PATCH", "/journal-platforms/{platform_id}", "JournalPlatformResponse"
    ),
    RouteContract("DELETE", "/journal-platforms/{platform_id}", "None"),
    RouteContract("GET", "/journals", "JournalPage"),
    RouteContract("POST", "/journals", "JournalResponse"),
    RouteContract("GET", "/journals/{journal_id}", "JournalResponse"),
    RouteContract("PATCH", "/journals/{journal_id}", "JournalResponse"),
    RouteContract("DELETE", "/journals/{journal_id}", "None"),
    RouteContract("GET", "/dashboard/summary", "DashboardSummary"),
    RouteContract("GET", "/audit-logs", "AuditLogPage"),
    RouteContract("GET", "/audit-logs/{log_id}", "AuditLogResponse"),
)
