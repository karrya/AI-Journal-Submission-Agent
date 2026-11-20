from app.models import (
    Base,
    Journal,
    JournalSubmissionPortal,
    Publisher,
    RegistrationTask,
)


EXPECTED_TABLES = {
    "users",
    "roles",
    "user_roles",
    "auth_sessions",
    "authors",
    "author_emails",
    "institutions",
    "author_institutions",
    "author_authorizations",
    "manuscripts",
    "manuscript_authors",
    "manuscript_versions",
    "file_families",
    "manuscript_files",
    "publishers",
    "journals",
    "operation_logs",
    "journal_submission_portals",
    "journal_source_snapshots",
    "journal_discovery_logs",
    "discovery_tasks",
    "registration_tasks",
    "registration_confirmations",
}


def test_domain_wide_schema_contains_only_current_tables():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_publisher_wide_row_contains_aliases_and_registration_support():
    columns = Publisher.__table__.c
    assert "aliases" in columns
    assert "registration_code" in columns
    assert "registration_support_status" in columns
    assert "registration_support_level" in columns
    assert "registration_official_domains" in columns
    assert "registration_notes" in columns
    assert "registration_updated_by" in columns


def test_journal_wide_row_contains_platform_and_aliases_without_duplicate_children():
    columns = Journal.__table__.c
    assert "platform_code" in columns
    assert "aliases" in columns
    assert "platform_id" not in columns


def test_portal_wide_row_contains_adapter_configuration():
    columns = JournalSubmissionPortal.__table__.c
    assert "adapter_code" in columns
    assert "adapter_name" in columns
    assert "adapter_version" in columns
    assert "adapter_support_status" in columns
    assert "adapter_allowed_domains" in columns
    assert "adapter_capability_config" in columns
    assert "adapter_last_verified_at" in columns
    assert "adapter_verification_notes" in columns
    assert "platform_adapter_id" not in columns


def test_registration_task_does_not_reference_removed_account_catalog():
    assert "account_id" not in RegistrationTask.__table__.c
