# TencentBlueKing is pleased to support the open source community by making
# 蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
# Copyright (C) Tencent. All rights reserved.
# Licensed under the MIT License (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
#     http://opensource.org/licenses/MIT
#
# Unless required by applicable law or agreed to in writing, software distributed under
# the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions and
# limitations under the License.
#
# We undertake not to change the open source license (MIT license) applicable
# to the current version of the project delivered to anyone in the future.

"""Listing a Project's conversations, and ending one of them.

Deliberately no agent here, unlike ``test_conversations.py``. Both operations are about the
conversation *row*: listing reads this service's own tables, and ending one is a database write
plus a best-effort attempt to stop a Runtime that, in these tests, was never started. Spawning
a real agent would only make them slow and require the agent's virtualenv.
"""

from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from app_spark_api.agent.conversations import services
from app_spark_api.agent.conversations.models import Conversation
from app_spark_api.core.projects.models import Project
from app_spark_api.core.tenant.user import get_tenant

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.django_db(transaction=True)

PROJECT_ID = "spark-demo"
CONVERSATIONS_URL = f"/api/projects/{PROJECT_ID}/conversations/"


@pytest.fixture(autouse=True)
def runtime_provider(settings, tmp_path: Path) -> None:
    """Give the provider somewhere harmless to point at.

    Ending a conversation goes through ``terminate_runtime()``, which needs a provider to exist
    even when there is no Runtime for it to stop. The local provider only validates its
    configuration on construction and touches none of these paths unless it spawns something.
    """
    settings.AGENT_RUNTIME_PROVIDER = "local_process"
    settings.AGENT_RUNTIME_PROVIDER_CONFIG = {
        "agent_project_dir": str(tmp_path / "agent"),
        "workspace_root": str(tmp_path / "workspaces"),
        "state_root": str(tmp_path / "agent-state"),
    }


@pytest.fixture
def project(bk_user) -> Project:
    """A Project the logged-in caller can reach.

    Not the shared ``project`` fixture: that one uses the user's own random ``tenant_id``, while
    the API scopes by ``get_tenant()``, which is ``default`` unless multi-tenant mode is on.
    """
    return Project.objects.create(
        id=PROJECT_ID,
        name="Spark Demo",
        creator=bk_user,
        owner=bk_user,
        tenant_id=get_tenant(bk_user).id,
    )


@pytest.fixture
def conversation(project, bk_user) -> Conversation:
    return Conversation.objects.create_for_project(project, owner=bk_user.pk)


def close_url(number: int) -> str:
    return f"{CONVERSATIONS_URL}{number}/close/"


async def make_conversation(project: Project, owner: str) -> Conversation:
    """Add a conversation from inside an async test.

    Allocating a number takes a row lock and therefore a transaction, which the async ORM has
    none of -- so this goes through the service that already puts it on a worker thread, rather
    than reaching for the manager directly the way the sync fixtures above can.
    """
    return await services.create_conversation(project, owner=owner)


async def make_project(*, project_id: str, name: str, owner, tenant_id: str) -> Project:
    """Add a Project from inside an async test."""
    return await Project.objects.acreate(
        id=project_id,
        name=name,
        creator=owner,
        owner=owner,
        tenant_id=tenant_id,
    )


# --- listing ----------------------------------------------------------------------------


async def test_a_listed_conversation_carries_what_it_takes_to_open_it(aapi_client, conversation):
    body = (await aapi_client.get(CONVERSATIONS_URL)).json()

    assert body["count"] == 1
    (item,) = body["items"]
    assert item["number"] == conversation.number
    assert item["conversation_id"] == str(conversation.id)
    assert item["is_live"] is True
    assert item["closed_at"] is None


async def test_the_list_is_newest_first(aapi_client, project, bk_user):
    for index in range(3):
        created = await make_conversation(project, bk_user.pk)
        # `created` is auto_now_add, so conversations built back to back can share a timestamp
        # and leave the order down to the tiebreaker. Set explicitly, since the order is the
        # thing under test here.
        await Conversation.objects.filter(pk=created.pk).aupdate(created=datetime(2026, 1, index + 1, tzinfo=UTC))

    body = (await aapi_client.get(CONVERSATIONS_URL)).json()

    assert [item["number"] for item in body["items"]] == [3, 2, 1]


async def test_the_list_covers_one_project_only(aapi_client, project, conversation, bk_user):
    """Numbers restart per Project, so leaking across them would also be ambiguous."""
    elsewhere = await make_project(
        project_id="other-project",
        name="Other Project",
        owner=bk_user,
        tenant_id=get_tenant(bk_user).id,
    )
    await make_conversation(elsewhere, bk_user.pk)

    body = (await aapi_client.get(CONVERSATIONS_URL)).json()

    assert [item["conversation_id"] for item in body["items"]] == [str(conversation.id)]


async def test_the_list_is_paginated_by_page_number(aapi_client, project, bk_user):
    for _ in range(3):
        await make_conversation(project, bk_user.pk)

    body = (await aapi_client.get(f"{CONVERSATIONS_URL}?page=2&page_size=2")).json()

    assert len(body["items"]) == 1
    assert body["count"] == 3


async def test_a_project_nobody_in_this_tenant_owns_is_not_found(aapi_client, bk_user):
    await make_project(project_id="far-away", name="Far Away", owner=bk_user, tenant_id="some-other-tenant")

    response = await aapi_client.get("/api/projects/far-away/conversations/")

    assert response.status_code == HTTPStatus.NOT_FOUND


# --- telling live from closed -----------------------------------------------------------


@pytest.fixture
async def one_live_and_one_closed(aapi_client, project, bk_user) -> tuple[Conversation, Conversation]:
    live = await make_conversation(project, bk_user.pk)
    closed = await make_conversation(project, bk_user.pk)
    await aapi_client.post(close_url(closed.number))
    return live, closed


async def test_the_list_can_be_narrowed_to_live_conversations(aapi_client, one_live_and_one_closed):
    live, _ = one_live_and_one_closed

    body = (await aapi_client.get(f"{CONVERSATIONS_URL}?is_live=true")).json()

    assert [item["number"] for item in body["items"]] == [live.number]
    assert body["count"] == 1


async def test_the_list_can_be_narrowed_to_closed_conversations(aapi_client, one_live_and_one_closed):
    _, closed = one_live_and_one_closed

    body = (await aapi_client.get(f"{CONVERSATIONS_URL}?is_live=false")).json()

    assert [item["number"] for item in body["items"]] == [closed.number]


async def test_the_unfiltered_list_keeps_both_and_says_which_is_which(aapi_client, one_live_and_one_closed):
    live, closed = one_live_and_one_closed

    body = (await aapi_client.get(CONVERSATIONS_URL)).json()

    assert {item["number"]: item["is_live"] for item in body["items"]} == {
        live.number: True,
        closed.number: False,
    }


# --- ending a conversation --------------------------------------------------------------


async def test_ending_a_conversation_reports_it_as_no_longer_live(aapi_client, conversation):
    response = await aapi_client.post(close_url(conversation.number))

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["is_live"] is False
    assert body["closed_at"] is not None
    assert body["conversation_id"] == str(conversation.id)

    await conversation.arefresh_from_db()
    assert conversation.closed_at is not None


async def test_ending_a_conversation_twice_is_refused(aapi_client, conversation):
    """Closing is a terminal transition, so the second call has nothing to do."""
    await aapi_client.post(close_url(conversation.number))

    response = await aapi_client.post(close_url(conversation.number))

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {"detail": "This conversation has been closed."}


async def test_ending_a_conversation_revokes_its_runtimes_authority_to_write(aapi_client, conversation):
    """A Runtime this service lost track of must not be able to keep replicating state."""
    epoch_before = conversation.state_epoch

    await aapi_client.post(close_url(conversation.number))

    await conversation.arefresh_from_db()
    assert conversation.state_epoch == epoch_before + 1


async def test_a_closed_conversation_cannot_be_advanced(aapi_client, conversation):
    """Without this the close would be cosmetic: the next turn would respawn a Runtime."""
    await aapi_client.post(close_url(conversation.number))

    response = await aapi_client.post(
        f"{CONVERSATIONS_URL}{conversation.number}/runs/",
        data={"content": "carry on"},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json() == {"detail": "This conversation has been closed."}


async def test_a_closed_conversation_still_reports_its_state(aapi_client, conversation):
    """The history stays readable; only advancing it is refused."""
    await aapi_client.post(close_url(conversation.number))

    body = (await aapi_client.get(f"{CONVERSATIONS_URL}{conversation.number}/")).json()

    assert body["is_live"] is False
    assert body["closed_at"] is not None
    assert body["running"] is False


async def test_ending_a_conversation_that_does_not_exist_is_not_found(aapi_client, project):
    response = await aapi_client.post(close_url(404))

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_an_anonymous_caller_can_neither_list_nor_end(aanonymous_api_client, conversation):
    assert (await aanonymous_api_client.get(CONVERSATIONS_URL)).status_code == HTTPStatus.UNAUTHORIZED
    assert (await aanonymous_api_client.post(close_url(conversation.number))).status_code == (HTTPStatus.UNAUTHORIZED)
