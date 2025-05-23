# TencentBlueKing is pleased to support the open source community by making
# 蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
# Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
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
from blue_krill.data_types.enum import EnumField, StrStructuredEnum


class AppTenantMode(StrStructuredEnum):
    """The tenant mode of the application. The mode controls the accessibility of
    the application to different tenants. For example, an application is available
    for all tenants when the mode is GLOBAL.
    """

    GLOBAL = EnumField("global", "全租户可用")
    SINGLE = EnumField("single", "单租户")


class TenantStatus(StrStructuredEnum):
    """租户状态"""

    ENABLED = EnumField("enabled", "启用")
    DISABLED = EnumField("disabled", "禁用")


# API 请求头中用于指定租户 ID 的字段
API_HERDER_TENANT_ID = "X-Bk-Tenant-Id"
