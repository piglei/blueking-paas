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

from paasng.utils.basic import re_path

from . import views

urlpatterns = [
    re_path(
        r"api/bkapps/applications/(?P<code>[^/]+)/domains/$",
        views.AppDomainsViewSet.as_view({"get": "list", "post": "create"}),
        name="api.app_domains",
    ),
    re_path(
        r"api/bkapps/applications/(?P<code>[^/]+)/domains/(?P<id>\d+)/$",
        views.AppDomainsViewSet.as_view({"put": "update", "delete": "destroy"}),
        name="api.app_domains.singular",
    ),
    re_path(
        r"api/bkapps/applications/(?P<code>[^/]+)/domains/configs/$",
        views.AppDomainsViewSet.as_view({"get": "list_configs"}),
        name="api.app_domains.configs",
    ),
    # Entrance related paths
    re_path(
        r"api/bkapps/applications/(?P<code>[^/]+)/entrances/$",
        views.AppEntranceViewSet.as_view({"get": "list_all_entrances"}),
        name="api.applications.entrances.all_entrances",
    ),
]
