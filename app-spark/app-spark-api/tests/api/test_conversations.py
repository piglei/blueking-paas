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

"""Driving conversations end to end against a real Agent Runtime process.

Nothing is mocked here. Every test spawns the actual agent, configured with the agent's own
``fake:`` model so the run costs nothing and always does the same thing, and drives it over
real HTTP. That is worth the seconds it takes: a fake provider would prove that this service
talks to a fake provider, whereas these prove the whole chain -- provisioning, the HTTP client,
the AG-UI passthrough, and the agent really writing to a workspace.

Prerequisite: ``cd agent && uv sync``. Without the agent's virtualenv these tests skip with a
reason rather than failing in a way nobody can read.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from app_spark_api.agent.conversations.models import Conversation
from app_spark_api.agent.runtime import get_agent_runtime_provider
from app_spark_api.core.projects.models import Project
from app_spark_api.core.tenant.user import get_tenant

if TYPE_CHECKING:
    from django.http import StreamingHttpResponse
    from django.test import AsyncClient

pytestmark = pytest.mark.django_db(transaction=True)

AGENT_PROJECT_DIR = Path(__file__).resolve().parents[3] / "agent"

PROJECT_ID = "spark-demo"

# What the agent's `fake:write-file` scenario writes, one per turn.
FIRST_NOTE = "fake-agent-note-1.md"
SECOND_NOTE = "fake-agent-note-2.md"


@pytest.fixture
def project(bk_user) -> Project:
    """A Project the logged-in user's tenant can reach.

    Deliberately not the shared ``project`` fixture: that one is created under the user's own
    random ``tenant_id``, while the API scopes by ``get_tenant()``, which is ``default`` unless
    multi-tenant mode is on.
    """
    return Project.objects.create(
        id=PROJECT_ID,
        name="Spark Demo",
        creator=bk_user,
        owner=bk_user,
        tenant_id=get_tenant(bk_user).id,
    )


@pytest.fixture
def workspace_root(tmp_path) -> Path:
    return tmp_path / "workspaces"


@pytest.fixture
async def agent(settings, tmp_path, workspace_root) -> AsyncIterator[None]:
    """Point the service at the real agent, scripted with the free `write-file` scenario."""
    async for _ in _configured_agent(settings, tmp_path, workspace_root, "fake:write-file"):
        yield None


@pytest.fixture
async def slow_agent(settings, tmp_path, workspace_root) -> AsyncIterator[None]:
    """Point the service at an agent that keeps a run open long enough to collide with."""
    async for _ in _configured_agent(settings, tmp_path, workspace_root, "fake:slow"):
        yield None


async def _configured_agent(
    settings: Any,
    tmp_path: Path,
    workspace_root: Path,
    model: str,
) -> AsyncIterator[None]:
    """Configure the local provider, and make sure it leaves no process behind."""
    if not (AGENT_PROJECT_DIR / ".venv").exists():
        pytest.skip(f"The agent has no virtualenv yet; run `cd {AGENT_PROJECT_DIR} && uv sync`")

    settings.AGENT_RUNTIME_PROVIDER = "local_process"
    settings.AGENT_RUNTIME_PROVIDER_CONFIG = {
        "agent_project_dir": str(AGENT_PROJECT_DIR),
        "workspace_root": str(workspace_root),
        "state_root": str(tmp_path / "agent-state"),
        "model": model,
        # Long enough that a second request lands while the run is still open, short enough
        # that a test which forgets to release it still finishes.
        "extra_env": {"APP_SPARK_AGENT_FAKE_DELAY_SECONDS": "5"},
    }
    try:
        yield None
    finally:
        # Before the `settings` fixture restores the old values: that would reset the cached
        # provider and leave the processes it started with nobody to stop them.
        await get_agent_runtime_provider().shutdown()


# --- Driving the API ---------------------------------------------------------------------


async def create_conversation(client: AsyncClient) -> dict[str, Any]:
    """Create a conversation and return the Runtime state it reports."""
    response = await client.post(f"/api/projects/{PROJECT_ID}/conversations/")
    assert response.status_code == HTTPStatus.CREATED, response.content
    return json.loads(response.content)


async def post_run(client: AsyncClient, number: int, prompt: str) -> Any:
    """Submit one turn without judging how it was answered."""
    return await client.post(
        f"/api/projects/{PROJECT_ID}/conversations/{number}/runs/",
        data={"content": prompt},
        content_type="application/json",
    )


async def run_turn(client: AsyncClient, number: int, prompt: str) -> list[dict[str, Any]]:
    """Submit one turn and read its event stream to the end."""
    response = await post_run(client, number, prompt)
    assert response.status_code == HTTPStatus.OK, response.content
    assert response.headers["content-type"] == "text/event-stream"
    return await collect_events(response)


async def collect_events(response: StreamingHttpResponse) -> list[dict[str, Any]]:
    """Parse a whole SSE body into the AG-UI events it carried."""
    # Django's async test client wraps the response in an async iterator; the sync half of the
    # declared union only happens under the sync client, which cannot reach these views at all.
    stream = response.streaming_content
    assert isinstance(stream, AsyncIterator)
    body = b"".join([chunk async for chunk in stream]).decode()
    return [
        json.loads(line.removeprefix("data:").strip())
        for line in body.replace("\r\n", "\n").splitlines()
        if line.startswith("data:")
    ]


def event_types(events: list[dict[str, Any]]) -> list[str]:
    return [str(event["type"]) for event in events]


def assistant_reply(events: list[dict[str, Any]]) -> str:
    """Reassemble the assistant's message from the deltas the client received."""
    return "".join(str(event["delta"]) for event in events if event.get("type") == "TEXT_MESSAGE_CONTENT")


# --- The tests ---------------------------------------------------------------------------


async def test_a_new_conversation_comes_with_a_live_runtime(aapi_client, project, agent):
    state = await create_conversation(aapi_client)

    assert state["model"] == "fake:write-file"
    assert state["running"] is False
    assert state["context_version"] == 0
    # The number is what the caller will put in URLs; the UUID is what AG-UI events carry, so
    # both have to come back or the client cannot join the two together.
    assert state["number"] == 1
    assert await Conversation.objects.filter(id=state["conversation_id"], number=1).aexists()


async def test_a_turn_streams_agui_events_and_changes_the_workspace(
    aapi_client,
    project,
    agent,
    workspace_root,
):
    state = await create_conversation(aapi_client)

    events = await run_turn(aapi_client, state["number"], "write my first note")

    types = event_types(events)
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"
    # The agent reached for a real tool and the client saw it happen, delta by delta.
    assert "TOOL_CALL_START" in types
    assert "TOOL_CALL_RESULT" in types
    assert "TEXT_MESSAGE_CONTENT" in types
    assert FIRST_NOTE in assistant_reply(events)

    # And the workspace really changed, which is the whole point of driving an agent.
    note = workspace_root / PROJECT_ID / FIRST_NOTE
    assert note.exists()
    assert "write my first note" in note.read_text()


async def test_a_second_turn_continues_the_same_conversation(
    aapi_client,
    project,
    agent,
    workspace_root,
):
    state = await create_conversation(aapi_client)
    number = state["number"]

    await run_turn(aapi_client, number, "write my first note")
    await run_turn(aapi_client, number, "write my second note")

    # A second note rather than a rewritten first one: the history the Runtime kept is what
    # told the agent this was turn two. Nothing about it was resent by this service.
    assert (workspace_root / PROJECT_ID / SECOND_NOTE).exists()

    response = await aapi_client.get(f"/api/projects/{PROJECT_ID}/conversations/{number}/")
    assert response.status_code == HTTPStatus.OK
    after = json.loads(response.content)
    assert after["context_version"] >= 2
    assert after["log_seq"] > 0
    assert after["ui_event_seq"] > 0
    assert after["running"] is False


async def test_missed_events_can_be_read_back_after_the_stream_is_gone(
    aapi_client,
    project,
    agent,
):
    state = await create_conversation(aapi_client)
    number = state["number"]
    streamed = await run_turn(aapi_client, number, "write my first note")

    response = await aapi_client.get(f"/api/projects/{PROJECT_ID}/conversations/{number}/ui-events/")

    assert response.status_code == HTTPStatus.OK
    page = json.loads(response.content)
    assert page["exhausted"] is True
    assert page["last_seq"] == len(page["records"]) > 0
    replayed = [record["event"]["type"] for record in page["records"]]
    assert replayed[0] == "RUN_STARTED"
    assert replayed[-1] == "RUN_FINISHED"
    # The history is the same run, with the per-token deltas already coalesced -- so it is
    # shorter than the live stream but tells the same story.
    assert len(replayed) <= len(streamed)


async def test_a_turn_is_refused_while_another_is_still_running(
    aapi_client,
    project,
    slow_agent,
):
    state = await create_conversation(aapi_client)
    number = state["number"]

    # `fake:slow` emits a chunk and then stalls, so reading one chunk proves the run is under
    # way rather than merely submitted -- no sleeping and hoping.
    first = await post_run(aapi_client, number, "take your time")
    assert first.status_code == HTTPStatus.OK
    assert await anext(aiter(first.streaming_content))

    second = await post_run(aapi_client, number, "and me too")

    assert second.status_code == HTTPStatus.CONFLICT
    assert "run" in json.loads(second.content)["detail"].lower()


async def test_a_second_conversation_on_one_project_is_refused(aapi_client, project, agent):
    """Two agents in one workspace would edit the same files, so the second is turned away."""
    await create_conversation(aapi_client)

    response = await aapi_client.post(f"/api/projects/{PROJECT_ID}/conversations/")

    assert response.status_code == HTTPStatus.CONFLICT
    assert "already has a running Agent" in json.loads(response.content)["detail"]


async def test_anonymous_callers_are_refused(aanonymous_api_client, project):
    response = await aanonymous_api_client.post(f"/api/projects/{PROJECT_ID}/conversations/")

    assert response.status_code == HTTPStatus.UNAUTHORIZED


async def test_a_project_of_another_tenant_is_not_found(aapi_client, project, settings):
    settings.ENABLE_MULTI_TENANT_MODE = True

    response = await aapi_client.post(f"/api/projects/{PROJECT_ID}/conversations/")

    assert response.status_code == HTTPStatus.NOT_FOUND
