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

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from ninja import NinjaAPI, Router

from app_spark_api.agent.conversations.api import router as conversations_router
from app_spark_api.agent.runtime import (
    AgentBusyError,
    AgentRuntimeError,
    AgentWorkspaceBusyError,
)
from app_spark_api.infras.accounts.api import router as accounts_router

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

root_router = Router()
root_router.add_router("/accounts/", accounts_router)
root_router.add_router("/projects/{project_id}/conversations/", conversations_router)

api = NinjaAPI(title="App Spark API", urls_namespace="api")
api.add_router("", root_router)


@api.exception_handler(AgentRuntimeError)
def handle_agent_runtime_error(request: HttpRequest, exc: AgentRuntimeError) -> HttpResponse:
    """Translate a failure of the Agent Runtime integration into a status the caller can act on.

    Handled centrally rather than per view because every conversation endpoint can raise the
    same set, and because the distinction that matters -- "try again in a moment" versus "this
    service is broken" -- belongs to the exception type, not to the operation that hit it.

    Note that this only covers failures raised before a response has begun. Once an event stream
    is under way its status code is already sent, and a break there is reported as an AG-UI
    ``RUN_ERROR`` event instead.
    """
    # Both mean the Agent is occupied right now and the same request may well succeed later.
    if isinstance(exc, AgentBusyError | AgentWorkspaceBusyError):
        return api.create_response(request, {"detail": str(exc)}, status=HTTPStatus.CONFLICT)

    logger.error("The Agent Runtime integration failed", exc_info=exc)
    return api.create_response(
        request,
        {"detail": f"The Agent Runtime is unavailable: {exc}"},
        status=HTTPStatus.BAD_GATEWAY,
    )
