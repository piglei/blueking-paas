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

from typing import Any
from uuid import UUID

from ninja import Field, Schema


class RuntimeStateResponse(Schema):
    """A conversation and the state of the Runtime serving it."""

    number: int = Field(description="会话在所属 Project 内的序号，URL 中使用")
    # Kept alongside the number because AG-UI stamps every event with it: without it a client
    # has no way to tell which conversation an event belongs to.
    conversation_id: UUID = Field(description="会话全局唯一 ID，也是 AG-UI 事件里的 threadId")
    model: str
    context_version: int = Field(description="下一轮 run 要提交的上下文版本")
    log_seq: int = Field(description="原始对话记录的最后一个游标")
    ui_event_seq: int = Field(description="AG-UI 事件历史的最后一个游标")
    running: bool = Field(description="Runtime 上是否有 run 正在执行")


class StartRunRequest(Schema):
    """One turn of a conversation.

    Only the new message: the Runtime owns the history, and resending it would give the two
    sides two versions of the same conversation to disagree about.
    """

    content: str = Field(min_length=1, description="用户这一轮说的话")


class UiEventPageResponse(Schema):
    """A page of the AG-UI events a Runtime has already emitted.

    This is how a client that lost its SSE connection catches up: the stream itself cannot be
    replayed, so anything missed has to be read back from the Runtime's own history.
    """

    since: int = Field(description="本页请求时使用的游标")
    last_seq: int = Field(description="频道当前的最后一个游标")
    exhausted: bool = Field(description="本页是否已经读到频道末尾")
    records: list[dict[str, Any]] = Field(description="AG-UI 事件记录，原样透传")


class ErrorResponse(Schema):
    detail: str
