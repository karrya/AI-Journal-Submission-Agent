import pytest
from datetime import UTC, datetime
from threading import Thread
from time import sleep
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import DiscoveryTask, Journal, PublisherAlias
from app.schemas.identification import ConfirmIdentityRequest, IdentifyRequest
from app.services.identification import (
    JournalIdentificationService,
    PublisherIdentificationService,
)


def test_publisher_search_matches_alias_and_domain(db_session, admin):
    service = PublisherIdentificationService(db_session, admin, "request-publisher")
    publisher = service.create_publisher(
        name="Elsevier", website_url="https://www.elsevier.com/", aliases=["RELX"]
    )
    by_alias = service.search(name="relx", website_url=None, page=1, page_size=20)
    by_domain = service.search(
        name=None, website_url="HTTPS://ELSEVIER.COM", page=1, page_size=20
    )
    assert [str(item.id) for item in by_alias.items] == [publisher.id]
    assert by_alias.items[0].match_reasons == ["别名精确匹配"]
    assert [str(item.id) for item in by_domain.items] == [publisher.id]
    assert by_domain.items[0].match_reasons == ["官方域名匹配"]


def test_create_publisher_deduplicates_aliases(db_session, admin):
    service = PublisherIdentificationService(db_session, admin, "request-aliases")
    publisher = service.create_publisher(
        name="Publisher Aliases", website_url=None, aliases=["One", "One", " ", "Two"]
    )
    rows = db_session.scalars(
        select(PublisherAlias).where(PublisherAlias.publisher_id == publisher.id)
    ).all()
    assert {row.normalized_alias for row in rows} == {"one", "two"}


def test_publisher_search_rejects_unauthorized_role(db_session, operator):
    service = PublisherIdentificationService(db_session, operator, "request-denied")
    with pytest.raises(AppError) as caught:
        service.create_publisher(name="Denied", website_url=None, aliases=[])
    assert caught.value.status_code == 403


def test_identify_uses_exact_issn_without_creating_duplicates(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-identify")
    journal = service.create_journal(
        publisher_name="Elsevier", name="Journal One", issn="03785955", aliases=["J1"]
    )
    result = service.identify(
        IdentifyRequest(journal_name="J1", issn="0378-5955", idempotency_key=None)
    )
    assert result.status == "SUCCEEDED"
    assert len(result.candidates) == 1
    assert result.candidates[0].identity_status == "VERIFIED"
    assert str(result.candidates[0].id) == journal.id

    repeated = service.identify(
        IdentifyRequest(journal_name="J1", issn="0378-5955", idempotency_key=None)
    )
    assert str(repeated.task_id) == str(result.task_id)
    assert db_session.scalar(select(func.count(DiscoveryTask.id))) == 1
    assert db_session.scalar(select(func.count(Journal.id))) == 1


def test_identify_rejects_invalid_issn_without_writes(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-invalid")
    with pytest.raises(AppError) as caught:
        service.identify(IdentifyRequest(journal_name="Bad ISSN", issn="00000000"))
    assert caught.value.status_code == 422
    assert db_session.scalar(select(func.count(DiscoveryTask.id))) == 0


def test_identify_requires_publisher_when_creating_candidate(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-no-publisher")
    with pytest.raises(AppError) as caught:
        service.identify(IdentifyRequest(journal_name="Unknown Journal"))
    assert caught.value.status_code == 422
    assert db_session.scalar(select(func.count(Journal.id))) == 0
    assert db_session.scalar(select(func.count(DiscoveryTask.id))) == 0


def test_identify_returns_all_similar_candidates_without_default_selection(
    db_session, admin
):
    service = JournalIdentificationService(db_session, admin, "request-similar")
    service.create_journal(publisher_name="P1", name="Journal of Science", aliases=[])
    service.create_journal(publisher_name="P2", name="Journal of Science", aliases=[])
    result = service.identify(IdentifyRequest(journal_name="Journal of Science"))
    assert result.candidates[0].identity_status == "NEEDS_CONFIRMATION"
    assert len(result.candidates) == 2


def test_confirm_identity_requires_current_timestamp(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-confirm")
    journal = service.create_journal(
        publisher_name="Publisher", name="Candidate", aliases=[]
    )
    response = service.confirm_identity(
        journal.id,
        ConfirmIdentityRequest(
            expected_updated_at=journal.updated_at.replace(tzinfo=UTC),
            confirmation_note="confirmed by test",
        ),
    )
    assert response.identity_status == "VERIFIED"
    assert response.verified_at is not None
    with pytest.raises(AppError) as caught:
        service.confirm_identity(
            journal.id,
            ConfirmIdentityRequest(
                expected_updated_at=journal.updated_at.replace(tzinfo=UTC),
                confirmation_note=None,
            ),
        )
    assert caught.value.status_code == 409


def test_non_admin_cannot_confirm_identity(db_session, operator):
    service = JournalIdentificationService(db_session, operator, "request-denied")
    with pytest.raises(AppError) as caught:
        service.confirm_identity(
            "00000000-0000-4000-8000-000000000000",
            ConfirmIdentityRequest(expected_updated_at=datetime.now(UTC)),
        )
    assert caught.value.status_code == 403


def test_identify_matches_both_identifiers_and_persists_verified_state(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-both-identifiers")
    journal = service.create_journal(
        publisher_name="Publisher",
        name="Both Identifiers",
        issn="03785955",
        eissn="18781128",
        aliases=[],
    )
    response = service.identify(
        IdentifyRequest(
            journal_name="Both Identifiers", issn="03785955", eissn="18781128"
        )
    )
    assert response.candidates[0].identity_status == "VERIFIED"
    db_session.expire_all()
    assert journal.identity_status == "VERIFIED"
    assert journal.verified_at is not None


def test_identifier_name_conflict_is_persisted_and_cannot_be_confirmed(
    db_session, admin
):
    service = JournalIdentificationService(db_session, admin, "request-conflict")
    journal = service.create_journal(
        publisher_name="Publisher", name="Actual Journal", issn="03785955", aliases=[]
    )
    response = service.identify(
        IdentifyRequest(journal_name="Different Journal", issn="03785955")
    )
    assert response.candidates[0].identity_status == "CONFLICT"
    db_session.expire_all()
    assert journal.identity_status == "CONFLICT"
    with pytest.raises(AppError) as caught:
        service.confirm_identity(
            journal.id,
            ConfirmIdentityRequest(expected_updated_at=journal.updated_at.replace(tzinfo=UTC),
        ))
    assert caught.value.status_code == 409


def test_domain_match_requires_exact_normalized_host(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-domain")
    service.create_journal(
        publisher_name="Publisher",
        name="Legitimate",
        website_url="https://example.com",
        aliases=[],
    )
    service.create_journal(
        publisher_name="Publisher",
        name="Malicious Suffix",
        website_url="https://example.com.evil.example/?next=example.com",
        aliases=[],
    )
    response = service.search(
        name=None,
        issn=None,
        eissn=None,
        publisher_id=None,
        website_url="https://example.com",
        page=1,
        page_size=20,
    )
    assert [candidate.name for candidate in response.items] == ["Legitimate"]


def test_new_candidate_preserves_website_and_source(db_session, admin):
    service = JournalIdentificationService(db_session, admin, "request-website")
    response = service.identify(
        IdentifyRequest(
            publisher_name="Publisher",
            journal_name="Website Candidate",
            website_url="https://example.org/authors",
        )
    )
    assert response.candidates[0].website_url == "https://example.org/authors"
    journal = db_session.get(Journal, str(response.candidates[0].id))
    assert journal.website_url == "https://example.org/authors"
    assert journal.source_url == "https://example.org/authors"


def test_invalid_search_url_is_validation_error(db_session, admin):
    publisher_service = PublisherIdentificationService(db_session, admin, "request-url")
    journal_service = JournalIdentificationService(db_session, admin, "request-url")
    with pytest.raises(AppError) as caught:
        publisher_service.search(
            name=None, website_url="http://user:pass@example.com", page=1, page_size=20
        )
    assert caught.value.status_code == 422
    with pytest.raises(AppError) as caught:
        journal_service.search(
            name=None,
            issn=None,
            eissn=None,
            publisher_id=None,
            website_url="http://user:pass@example.com",
            page=1,
            page_size=20,
        )
    assert caught.value.status_code == 422


def test_concurrent_identify_returns_same_task(db_engine, admin):
    class SynchronizedService(JournalIdentificationService):
        def _create_journal(self, **kwargs):
            journal = super()._create_journal(**kwargs)
            sleep(0.1)
            return journal

    outcomes = []
    errors = []

    def identify(session):
        try:
            service = SynchronizedService(session, admin, "request-race")
            result = service.identify(
                IdentifyRequest(
                    publisher_name="Race Publisher",
                    journal_name="Race Journal",
                    issn="03785955",
                )
            )
            outcomes.append(str(result.task_id))
        except Exception as exc:
            errors.append(exc)

    first = Session(bind=db_engine.connect())
    second = Session(bind=db_engine.connect())
    threads = [Thread(target=identify, args=(first,)), Thread(target=identify, args=(second,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert all(not thread.is_alive() for thread in threads)
    assert not errors, errors
    assert len(set(outcomes)) == 1
    assert db_session_scalar_count(db_engine, DiscoveryTask) == 1
    assert db_session_scalar_count(db_engine, Journal) == 1
    first.close()
    second.close()


def db_session_scalar_count(db_engine, model):
    with db_engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(model))
