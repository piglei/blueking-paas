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

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from paas_wl.bk_app.applications.models import WlApp
from paas_wl.infras.cluster.models import Cluster

from .shim import RegionClusterService


def get_default_cluster_by_region(region: str) -> Cluster:
    """Get default cluster name by region"""
    try:
        return Cluster.objects.get(is_default=True, region=region)
    except Cluster.DoesNotExist:
        raise RuntimeError(f"No default cluster found in region `{region}`")


def get_cluster_by_app(app: WlApp) -> Cluster:
    """Get kubernetes cluster by given app

    :param app: WlApp object
    :raise RuntimeError: App has an invalid cluster_name defined
    """
    if app.use_dev_sandbox:
        return get_dev_sandbox_cluster(app)

    cluster_name = app.config_set.latest().cluster
    if not cluster_name:
        return get_default_cluster_by_region(app.region)

    try:
        return Cluster.objects.get(name=cluster_name)
    except Cluster.DoesNotExist:
        raise RuntimeError(f"Can not find a cluster called {cluster_name}")


def get_dev_sandbox_cluster(app: WlApp) -> Cluster:
    # 优先使用开发沙箱集群
    if cluster_name := settings.DEV_SANDBOX_CLUSTER:
        try:
            return Cluster.objects.get(name=cluster_name)
        except ObjectDoesNotExist:
            raise RuntimeError(f"dev sandbox cluster called {cluster_name} no found")

    # 否则使用 region 下的默认集群，注意：
    #   - 功能要求 k8s 版本 >= 1.20.x, 版本过低可能会导致 ingress 等资源出现版本兼容问题
    #
    # TODO：Cluster 增加新字段（配置项）来标记功能所使用的集群（以及配置整个功能开关等）
    return RegionClusterService(app.region).get_default_cluster()
