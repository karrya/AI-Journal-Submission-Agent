import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Author, Manuscript, ManuscriptVersion
from app.schemas.manuscripts import ManuscriptVersionCreate
from app.services.manuscripts import ManuscriptService


def active_grant(grant_factory, *, user, author, permissions):
    now = datetime.now(UTC)
    return grant_factory(
        user=user,
        author=author,
        permissions=permissions,
        valid_from=now - timedelta(minutes=5),
        valid_to=now + timedelta(hours=1),
    )


@pytest.fixture
def committed_manuscript(client, db_session, operator_context, operator, grant_factory):
    owner = Author(display_name="Concurrent Owner", alternate_names=[])
    db_session.add(owner)
    db_session.commit()
    active_grant(
        grant_factory,
        user=operator,
        author=owner,
        permissions=["manuscript:create", "manuscript:read", "manuscript:update"],
    )
    response = client.post(
        "/api/v1/manuscripts",
        json={
            "owner_author_id": owner.id,
            "title": "Before concurrent patch",
            "abstract": "Before abstract",
            "keywords": ["before"],
            "article_type": "research",
            "language": "en",
        },
    )
    assert response.status_code == 201
    db_session.expire_all()
    manuscript = db_session.get(Manuscript, response.json()["id"])
    assert manuscript.current_version_id is not None
    db_session.commit()
    return manuscript


def run_concurrently(first, second):
    barrier = threading.Barrier(2)

    def synchronized(call):
        barrier.wait(timeout=10)
        return call()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(synchronized, call) for call in (first, second)]
        return [future.result(timeout=20) for future in futures]


def test_concurrent_version_posts_allocate_two_and_three(
    client,
    second_client,
    db_session,
    committed_manuscript,
    operator,
    auth_context_factory,
):
    auth_context_factory(operator, target_client=client)
    auth_context_factory(operator, target_client=second_client)
    path = f"/api/v1/manuscripts/{committed_manuscript.id}/versions"

    first, second = run_concurrently(
        lambda: client.post(path, json={"label": "Concurrent A"}),
        lambda: second_client.post(path, json={"label": "Concurrent B"}),
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert {first.json()["version_number"], second.json()["version_number"]} == {2, 3}
    db_session.expire_all()
    versions = list(
        db_session.scalars(
            select(ManuscriptVersion).where(
                ManuscriptVersion.manuscript_id == committed_manuscript.id
            )
        )
    )
    assert sorted(item.version_number for item in versions) == [1, 2, 3]
    manuscript = db_session.get(Manuscript, committed_manuscript.id)
    assert manuscript.current_version_id in {first.json()["id"], second.json()["id"]}
    current = db_session.get(ManuscriptVersion, manuscript.current_version_id)
    assert current.version_number == 3


def test_concurrent_patch_and_version_snapshot_are_entirely_before_or_after(
    client,
    second_client,
    db_session,
    committed_manuscript,
    operator,
    auth_context_factory,
):
    auth_context_factory(operator, target_client=client)
    auth_context_factory(operator, target_client=second_client)
    manuscript_path = f"/api/v1/manuscripts/{committed_manuscript.id}"
    before = {
        "title": "Before concurrent patch",
        "abstract": "Before abstract",
        "keywords": ["before"],
    }
    after = {
        "title": "After concurrent patch",
        "abstract": "After abstract",
        "keywords": ["after", "committed"],
    }

    patched, versioned = run_concurrently(
        lambda: client.patch(manuscript_path, json=after),
        lambda: second_client.post(f"{manuscript_path}/versions", json={}),
    )

    assert patched.status_code == 200, patched.text
    assert versioned.status_code == 201, versioned.text
    assert versioned.json()["version_number"] == 2
    snapshot = versioned.json()["metadata_snapshot"]
    actual = {field: snapshot[field] for field in before}
    assert actual in (before, after)
    assert patched.json()["title"] == after["title"]
    db_session.expire_all()
    manuscript = db_session.get(Manuscript, committed_manuscript.id)
    assert manuscript.current_version_id == versioned.json()["id"]
    assert manuscript.title == after["title"]
    initial = db_session.scalar(
        select(ManuscriptVersion).where(
            ManuscriptVersion.manuscript_id == manuscript.id,
            ManuscriptVersion.version_number == 1,
        )
    )
    assert {field: initial.metadata_snapshot[field] for field in before} == before


def test_version_allocation_reads_committed_v2_after_lock_wait_with_old_snapshot(
    db_engine, committed_manuscript, operator
):
    connection_a = db_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    )
    connection_b = db_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    )
    session_a = Session(bind=connection_a, expire_on_commit=False)
    session_b = Session(bind=connection_b, expire_on_commit=False)
    service_a = ManuscriptService(session_a, operator, str(uuid4()))
    service_b = ManuscriptService(session_b, operator, str(uuid4()))
    version_flushed = threading.Event()
    allow_first_commit = threading.Event()
    second_lock_requested = threading.Event()

    try:
        assert (
            session_b.execute(text("SELECT @@transaction_isolation")).scalar()
            == "REPEATABLE-READ"
        )
        # Establish B's consistent read view at v1 before A creates and commits v2.
        assert session_b.scalars(
            select(ManuscriptVersion.version_number).where(
                ManuscriptVersion.manuscript_id == committed_manuscript.id
            )
        ).all() == [1]

        original_commit = service_a._commit

        def blocked_commit():
            version_flushed.set()
            assert allow_first_commit.wait(timeout=10)
            original_commit()

        service_a._commit = blocked_commit
        original_get = service_b.repository.get

        def signaling_get(manuscript_id, *, lock=False):
            if lock:
                second_lock_requested.set()
            return original_get(manuscript_id, lock=lock)

        service_b.repository.get = signaling_get
        with ThreadPoolExecutor(max_workers=2) as executor:
            try:
                first_future = executor.submit(
                    service_a.create_version,
                    committed_manuscript.id,
                    ManuscriptVersionCreate(label="Committed first"),
                )
                assert version_flushed.wait(timeout=10)
                second_future = executor.submit(
                    service_b.create_version,
                    committed_manuscript.id,
                    ManuscriptVersionCreate(label="Waiting second"),
                )
                # B requests the manuscript lock while A still holds it with v2 uncommitted.
                assert second_lock_requested.wait(timeout=10)
            finally:
                allow_first_commit.set()
            first = first_future.result(timeout=20)
            second = second_future.result(timeout=20)

        assert first.version_number == 2
        assert second.version_number == 3
        with Session(bind=db_engine) as verification_session:
            assert verification_session.scalars(
                select(ManuscriptVersion.version_number)
                .where(ManuscriptVersion.manuscript_id == committed_manuscript.id)
                .order_by(ManuscriptVersion.version_number)
            ).all() == [1, 2, 3]
    finally:
        allow_first_commit.set()
        session_a.rollback()
        session_b.rollback()
        session_a.close()
        session_b.close()
        connection_a.close()
        connection_b.close()
