from dataclasses import replace

import pytest

from app.models import (
    DiscoveryTask,
    Journal,
    JournalDiscoveryLog,
    JournalSourceSnapshot,
    JournalSubmissionPortal,
)
from app.crawlers.url_security import FetchResult
from app.schemas.identification import IdentifyRequest
from app.services.discovery_providers import CandidateSeed, ProviderError
from app.services.identification import JournalIdentificationService
from app.services.network_identification import NetworkIdentificationService
from sqlalchemy import select


def html_response(url, html):
    return FetchResult(
        final_url=url,
        status=200,
        headers={"content-type": "text/html; charset=utf-8"},
        body=html.encode(),
        text=html,
        redirects=(),
        content_sha256="hash-" + url,
    )


class FakeProvider:
    def __init__(self, seeds=None, error=None):
        self.seeds = seeds or []
        self.error = error

    def discover(self, journal_name, issn, eissn):
        if self.error:
            raise self.error
        return self.seeds


class FakeWebsite:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages[url]


def create_task(db_session, admin, name="Network Journal"):
    response = JournalIdentificationService(db_session, admin, "network-pipeline").create_network_task(
        IdentifyRequest(
            publisher_name="Publisher",
            journal_name=name,
            issn="0378-5955",
        )
    )
    return db_session.get(DiscoveryTask, str(response.task_id))


def test_pipeline_persists_verified_identity_portal_and_evidence(db_session, admin):
    seed = CandidateSeed(
        "Network Journal", "Publisher", "03785955", None,
        "https://journal.example", ("OPENALEX",),
    )
    pages = {
        "https://journal.example": html_response(
            "https://journal.example",
            """<title>Network Journal</title><body>ISSN 0378-5955
            <a href='/guide'>Guide for Authors</a>
            <a href='https://www.editorialmanager.com/network'>Submit Your Manuscript</a>
            </body>""",
        ),
        "https://journal.example/guide": html_response(
            "https://journal.example/guide",
            "<title>Guide for Authors</title><body>Network Journal instructions</body>",
        ),
        "https://www.editorialmanager.com/network": html_response(
            "https://www.editorialmanager.com/network",
            "<title>Editorial Manager</title><form><input type='password'></form>",
        ),
    }
    task = create_task(db_session, admin)
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider([seed])],
        http_client=FakeWebsite(pages),
    ).execute(task)

    assert result.journal_id is not None
    journal = db_session.get(Journal, result.journal_id)
    assert journal.identity_status == "VERIFIED"
    assert journal.name == "Network Journal"
    assert journal.author_guidelines_url == "https://journal.example/guide"
    assert journal.submission_url == "https://www.editorialmanager.com/network"
    assert journal.verified_at is not None
    portal = db_session.scalar(select(JournalSubmissionPortal).where(
        JournalSubmissionPortal.journal_id == journal.id
    ))
    assert portal.platform_code == "EDITORIAL_MANAGER"
    assert portal.verification_status == "VERIFIED"
    assert portal.access_status == "LOGIN_REQUIRED"
    snapshots = db_session.scalars(select(JournalSourceSnapshot).where(
        JournalSourceSnapshot.task_id == task.id
    )).all()
    assert len(snapshots) == 3
    assert all(snapshot.journal_id == journal.id for snapshot in snapshots)
    assert all(snapshot.storage_path for snapshot in snapshots)
    logs = db_session.scalars(select(JournalDiscoveryLog).where(
        JournalDiscoveryLog.task_id == task.id
    )).all()
    assert logs
    candidates = result.checkpoint["response"]["candidates"]
    assert candidates[0]["identity_status"] == "VERIFIED"
    assert candidates[0]["platform_code"] == "EDITORIAL_MANAGER"
    assert candidates[0]["evidence"]


def test_multiple_verified_candidates_require_selection_without_creating_journal(db_session, admin):
    seeds = [
        CandidateSeed("Network Journal", "Publisher", "03785955", None, "https://one.example", ("OPENALEX",)),
        CandidateSeed("Network Journal", "Publisher", "03785955", None, "https://two.example", ("CROSSREF",)),
    ]
    pages = {
        "https://one.example": html_response("https://one.example", "<title>Network Journal</title>0378-5955"),
        "https://two.example": html_response("https://two.example", "<title>Network Journal</title>0378-5955"),
    }
    task = create_task(db_session, admin)
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider(seeds)],
        http_client=FakeWebsite(pages),
    ).execute(task)
    assert result.journal_id is None
    assert db_session.query(Journal).count() == 0
    statuses = [item["identity_status"] for item in result.checkpoint["response"]["candidates"]]
    assert statuses == ["NEEDS_CONFIRMATION", "NEEDS_CONFIRMATION"]


def test_portal_access_status_distinguishes_public_and_captcha(db_session, admin):
    seeds = [
        CandidateSeed("Network Journal", "Publisher", "03785955", None, "https://one.example", ("OPENALEX",)),
        CandidateSeed("Network Journal", "Publisher", "03785955", None, "https://two.example", ("CROSSREF",)),
    ]
    pages = {
        "https://one.example": html_response(
            "https://one.example",
            "<title>Network Journal</title>0378-5955<a href='https://one.example/submit'>Submit Your Manuscript</a>",
        ),
        "https://two.example": html_response(
            "https://two.example",
            "<title>Network Journal</title>0378-5955<a href='https://two.example/submit'>Submit Your Manuscript</a>",
        ),
        "https://one.example/submit": html_response("https://one.example/submit", "<title>Public portal</title>"),
        "https://two.example/submit": html_response("https://two.example/submit", "<title>Blocked</title>CAPTCHA verify you are human"),
    }
    task = create_task(db_session, admin)
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider(seeds)],
        http_client=FakeWebsite(pages),
    ).execute(task)
    candidates = result.checkpoint["response"]["candidates"]
    assert candidates[0]["portal_access_status"] == "PUBLIC_ACCESS"
    assert candidates[1]["portal_access_status"] == "BLOCKED"
    assert candidates[1]["portal_verification_status"] == "NEEDS_REVIEW"


def test_name_only_search_result_is_not_automatically_verified(db_session, admin):
    response = JournalIdentificationService(db_session, admin, "name-only").create_network_task(
        IdentifyRequest(publisher_name="Publisher", journal_name="Generic Journal")
    )
    task = db_session.get(DiscoveryTask, str(response.task_id))
    seed = CandidateSeed(
        "Generic Journal", "Publisher", None, None,
        "https://lookalike.example", ("KIMI",),
    )
    pages = {
        "https://lookalike.example": html_response(
            "https://lookalike.example", "<title>Generic Journal</title>Advertising page"
        )
    }
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider([seed])],
        http_client=FakeWebsite(pages),
    ).execute(task)
    assert result.journal_id is None
    assert result.checkpoint["response"]["candidates"][0]["identity_status"] == "NEEDS_CONFIRMATION"


def test_temporary_homepage_http_failure_uses_worker_retry(db_session, admin):
    seed = CandidateSeed(
        "Network Journal", "Publisher", "03785955", None,
        "https://journal.example", ("OPENALEX",),
    )
    pages = {
        "https://journal.example": replace(
            html_response("https://journal.example", "unavailable"), status=503
        )
    }
    task = create_task(db_session, admin)
    service = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider([seed])],
        http_client=FakeWebsite(pages),
    )
    with pytest.raises(ProviderError) as caught:
        service.execute(task)
    assert caught.value.retryable is True


def test_identifier_name_conflict_does_not_overwrite_existing_journal(db_session, admin):
    existing = JournalIdentificationService(db_session, admin, "existing-journal").create_journal(
        publisher_name="Publisher", name="Existing Journal", issn="03785955", aliases=[]
    )
    seed = CandidateSeed(
        "Different Journal", "Publisher", "03785955", None,
        "https://journal.example", ("OPENALEX",),
    )
    pages = {
        "https://journal.example": html_response(
            "https://journal.example", "<title>Different Journal</title>0378-5955"
        )
    }
    task = create_task(db_session, admin, name="Different Journal")
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider([seed])],
        http_client=FakeWebsite(pages),
    ).execute(task)
    assert result.journal_id is None
    db_session.expire_all()
    assert existing.identity_status == "UNVERIFIED"
    assert db_session.query(Journal).count() == 1
    assert result.checkpoint["response"]["candidates"][0]["identity_status"] == "CONFLICT"


def test_javascript_page_uses_isolated_browser_fallback(db_session, admin):
    seed = CandidateSeed(
        "Network Journal", "Publisher", "03785955", None,
        "https://journal.example", ("OPENALEX",),
    )
    home = """<title>Network Journal</title><body>ISSN 0378-5955
        <a href='/guide'>Guide for Authors</a></body>"""
    pages = {
        "https://journal.example": html_response(
            "https://journal.example", "<html><body>Please enable JavaScript</body></html>"
        ),
        "https://journal.example/guide": html_response(
            "https://journal.example/guide", "<title>Guide</title>Network Journal"
        ),
    }
    class Browser:
        def __init__(self):
            self.calls = []
        def get(self, url):
            self.calls.append(url)
            return html_response(url, home)

    browser = Browser()
    task = create_task(db_session, admin)
    result = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider([seed])],
        http_client=FakeWebsite(pages),
        browser_client=browser,
    ).execute(task)
    assert browser.calls == ["https://journal.example"]
    assert result.journal_id is not None


def test_pipeline_retries_when_all_discovery_paths_fail_temporarily(db_session, admin):
    task = create_task(db_session, admin)
    service = NetworkIdentificationService(
        db_session,
        providers=[FakeProvider(error=ProviderError("outage", retryable=True))],
        http_client=FakeWebsite({}),
    )
    with pytest.raises(ProviderError) as caught:
        service.execute(task)
    assert caught.value.retryable is True
