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

"""How an Agent Runtime proves which conversation it is allowed to write state for.

A signed value rather than a stored one: the only fact that needs carrying is the conversation
id, this service's ``SECRET_KEY`` is enough to make it unforgeable, and a table would add a row
to write on every spawn and clean up on every teardown for no gain.

Deliberately without an expiry. A Runtime is a long-lived process that may sit idle between
turns for as long as its user keeps the tab open, and a token that expired underneath it would
turn a paused conversation into lost conversation state. Revocation therefore is not per token:
rotating ``SECRET_KEY`` invalidates every one of them at once, and a Runtime that must be cut
off is one the provider can terminate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core import signing

if TYPE_CHECKING:
    from uuid import UUID

# Namespaces the signature, so a token minted here cannot be replayed against any other signed
# value this service happens to produce.
TOKEN_SALT = "app_spark_api.agent.conversations.state"


class InvalidStateToken(Exception):
    """Raised when a state-ingest token is missing, malformed, or not correctly signed."""


def mint_state_token(conversation_id: UUID) -> str:
    """Return the token a Runtime serving ``conversation_id`` writes state with.

    :param conversation_id: Conversation the token authorizes writes to, and only that one.
    :return: An opaque token safe to hand to the Runtime process.
    """
    return signing.Signer(salt=TOKEN_SALT).sign(str(conversation_id))


def read_state_token(token: str) -> str:
    """Return the conversation id ``token`` was minted for.

    :param token: Token as the Runtime presented it.
    :return: The conversation id, as a string; callers compare it with the one they were asked
        about rather than trusting the request's own path.
    :raises InvalidStateToken: If the token is empty or its signature does not check out.
    """
    if not token:
        raise InvalidStateToken("no state token was presented")
    try:
        return signing.Signer(salt=TOKEN_SALT).unsign(token)
    except signing.BadSignature as exc:
        raise InvalidStateToken("the state token is not correctly signed") from exc
