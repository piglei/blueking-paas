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

"""Orchestrating a conversation: the row, its Runtime, and one turn at a time."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async

from app_spark_api.agent.conversations.models import Conversation
from app_spark_api.agent.runtime import AgentRuntimeClient, get_agent_runtime_provider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app_spark_api.agent.runtime import AgentRun, EventPage, RuntimeHealth
    from app_spark_api.core.projects.models import Project

logger = logging.getLogger(__name__)


async def create_conversation(project: Project, *, owner: str | None) -> Conversation:
    """Create a conversation row, numbered within its Project.

    Runs in a worker thread because allocating the number takes a row lock, and Django's async
    ORM has no transactions of its own to hold one in.

    :param project: Project the conversation belongs to.
    :param owner: pk of the user starting it.
    :return: The stored conversation.
    """
    return await sync_to_async(Conversation.objects.create_for_project)(project, owner=owner)


async def open_client(conversation: Conversation) -> AgentRuntimeClient:
    """Bring up the conversation's Agent Runtime if needed and return a client for it.

    :param conversation: Conversation to be served.
    :return: A client pointed at a Runtime that has answered ``/health``.
    :raises AgentProvisionError: If no Runtime could be brought up.
    :raises AgentWorkspaceBusyError: If another conversation of the same Project holds one.
    """
    provider = get_agent_runtime_provider()
    # `project_id` rather than `project`, so this never lazily loads the related row -- an
    # implicit query here would be a synchronous one in an async view.
    handle = await provider.ensure(
        project_id=conversation.project_id,
        conversation_id=str(conversation.id),
    )
    return AgentRuntimeClient(handle)


async def get_health(conversation: Conversation) -> RuntimeHealth:
    """Return the Runtime's current cursors, starting it if it is not up yet."""
    client = await open_client(conversation)
    return await client.health()


async def read_ui_events(
    conversation: Conversation,
    *,
    since: int = 0,
    limit: int | None = None,
) -> EventPage:
    """Read one page of the AG-UI events the Runtime has recorded so far."""
    client = await open_client(conversation)
    return await client.read_ui_events(since=since, limit=limit)


async def start_run(conversation: Conversation, *, content: str) -> AgentRun:
    """Submit one turn and return its open event stream.

    The context version is read from ``/health`` immediately before the run rather than
    remembered between turns. Compaction can move it in the middle of a run, so a version
    carried over from the previous turn is not merely stale, it is wrong often enough to matter.

    :param conversation: Conversation the turn belongs to.
    :param content: The user's message.
    :return: The accepted run, whose bytes are still to come.
    :raises AgentBusyError: If a run is already occupying the Runtime.
    :raises AgentProvisionError: If no Runtime could be brought up.
    :raises AgentUnavailableError: If the Runtime cannot be reached or refuses the turn.
    """
    client = await open_client(conversation)
    health = await client.health()
    return await client.start_run(content=content, context_version=health.context_version)


async def stream_run(run: AgentRun, conversation_id: UUID) -> AsyncIterator[bytes]:
    """Forward a run's AG-UI events, turning a mid-stream failure into a final event.

    Once the first byte is out the status code is spent, so a connection that breaks here cannot
    be reported as an HTTP error. AG-UI has its own way to say a run ended badly, and a client
    that receives it can show something better than a stream that simply stopped.
    """
    try:
        async for chunk in run.aiter_bytes():
            yield chunk
    except Exception as exc:
        logger.exception("The event stream of conversation %s broke mid-run", conversation_id)
        yield _sse_frame(
            {
                "type": "RUN_ERROR",
                "timestamp": int(time.time() * 1000),
                "runId": run.run_id,
                "message": f"The Agent Runtime stopped responding: {exc}",
            }
        )


def _sse_frame(event: dict[str, Any]) -> bytes:
    """Encode one event the way the Agent Runtime encodes its own."""
    return f"data: {json.dumps(event)}\n\n".encode()
