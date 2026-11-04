import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Author, Manuscript, ManuscriptVersion


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
