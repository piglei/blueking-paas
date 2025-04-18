# -*- coding: utf-8 -*-
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
from django.utils.translation import gettext_lazy as _


class SiteAction(StrStructuredEnum):
    """蓝鲸 PaaS 平台全局功能相关权限"""

    VISIT_SITE = EnumField("visit_site", label=_("平台页面查看"))
    # 注意：这里是指后台管理页面的权限，进入后台管理后，查询相关资源需要平台管理/应用模板管理/平台运营的权限
    VISIT_ADMIN42 = EnumField("visit_admin42", label=_("访问后台管理"))

    # 平台管理（增强服务，运行时，应用集群，应用资源方案，应用管理，用户管理，代码库配置管理等）
    MANAGE_PLATFORM = EnumField("manage_platform", label=_("平台管理"))
    # 应用模板管理（应用模板管理, 监控仪表盘模版管理）
    MANAGE_APP_TEMPLATES = EnumField("manage_app_templates", label=_("应用模板管理"))
    # 平台运营（查看平台运营数据）
    OPERATE_PLATFORM = EnumField("operate_platform", label=_("平台运营"))


class PlatMgtAction(StrStructuredEnum):
    """平台管理功能相关权限

    FIXME: (多租户)切换为权限中心 -> 租户管理员 / 平台管理员权限 Action
    """

    # 允许所有平台管理功能
    ALL = EnumField("all", label=_("临时权限限制"))
