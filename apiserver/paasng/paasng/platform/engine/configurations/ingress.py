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

"""Utilities related with ingress"""

from typing import Dict, List

from django.conf import settings

from paas_wl.workloads.networking.entrance.allocator.domains import Domain, ModuleEnvDomains
from paas_wl.workloads.networking.entrance.allocator.subpaths import ModuleEnvSubpaths, Subpath
from paas_wl.workloads.networking.ingress.shim import sync_subdomains, sync_subpaths
from paasng.platform.applications.models import ModuleEnvironment
from paasng.platform.modules.constants import ExposedURLType


class AppDefaultDomains:
    """A helper class for dealing with app's default subdomains during building and releasing"""

    def __init__(self, env: ModuleEnvironment):
        self.env = env
        self.engine_app = env.get_engine_app()

        self.domains: List[Domain] = []
        self.initialize_domains()

    def initialize_domains(self):
        """calculate and store app's default subdomains"""
        # get domains only if the module was configured to use "SUBDOMAIN" type entrance
        if self.env.module.exposed_url_type == ExposedURLType.SUBDOMAIN:
            # calculate default subdomains
            self.domains = ModuleEnvDomains(self.env).all()

    def sync(self):
        """Sync app's default subdomains to engine"""
        sync_subdomains(self.env)

    def as_env_vars(self) -> Dict:
        """Return current subdomains as env vars"""
        domains_str = ";".join(d.host for d in self.domains)

        if not domains_str:
            # only if domain exist, would add ENGINE_APP_DEFAULT_SUBDOMAINS key
            return {}

        return {settings.CONFIGVAR_SYSTEM_PREFIX + "ENGINE_APP_DEFAULT_SUBDOMAINS": domains_str}


class AppDefaultSubpaths:
    """A helper class for dealing with app's default subpaths during building and releasing"""

    def __init__(self, env: ModuleEnvironment):
        self.env = env
        self.subpaths_service = ModuleEnvSubpaths(self.env)
        self.subpaths = self.subpaths_service.all()

    def sync(self):
        """Sync app's default subpaths to engine"""
        sync_subpaths(self.env)

    def as_env_vars(self) -> Dict:
        """Return current subpath as env vars"""
        obj = self.subpaths_service.get_shortest()
        if not obj:
            return {}

        return {
            settings.CONFIGVAR_SYSTEM_PREFIX + "SUB_PATH": self._build_sub_path_env(obj),
            settings.CONFIGVAR_SYSTEM_PREFIX + "DEFAULT_SUBPATH_ADDRESS": obj.as_url().as_address(),
        }

    def _build_sub_path_env(self, obj: Subpath):
        # TODO: remove FORCE_USING_LEGACY_SUB_PATH_VAR_VALUE in settings
        if self.env.module.exposed_url_type is None or settings.FORCE_USING_LEGACY_SUB_PATH_VAR_VALUE:
            # reserved for applications with legacy sub-path implementations
            engine_app = self.env.get_engine_app()
            return f"/{engine_app.region}-{engine_app.name}/"
        return obj.subpath
