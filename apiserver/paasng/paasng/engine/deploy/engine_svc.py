# -*- coding: utf-8 -*-
"""
TencentBlueKing is pleased to support the open source community by making
蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except
in compliance with the License. You may obtain a copy of the License at

    http://opensource.org/licenses/MIT

Unless required by applicable law or agreed to in writing, software distributed under
the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the specific language governing permissions and
limitations under the License.

We undertake not to change the open source license (MIT license) applicable
to the current version of the project delivered to anyone in the future.
"""
"""Engine services module
"""
import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict, Union

import cattr
from django.conf import settings

from paas_wl.platform.applications.models.app import WLEngineApp
from paas_wl.platform.applications.models.build import Build, BuildProcess
from paas_wl.platform.applications.models.managers.app_metadata import get_metadata, update_metadata
from paas_wl.platform.applications.models.misc import OutputStream
from paas_wl.release_controller.builder import tasks as builder_task
from paas_wl.resources import tasks as scheduler_tasks
from paas_wl.resources.base.exceptions import KubeException
from paas_wl.resources.tasks import release_app
from paas_wl.utils.constants import CommandStatus, CommandType
from paasng.engine.constants import JobStatus
from paasng.engine.controller.client import ControllerClient
from paasng.engine.controller.shortcuts import make_internal_client
from paasng.engine.helpers import SlugbuilderInfo

if TYPE_CHECKING:
    from paasng.dev_resources.sourcectl.models import VersionInfo


class LogLine(TypedDict):
    stream: str
    line: str
    created: datetime.datetime


class EngineDeployClient:
    """A high level client for engine"""

    def __init__(self, engine_app, controller_client: Optional[ControllerClient] = None):
        self.engine_app = engine_app
        self.wl_engine_app: WLEngineApp = self.engine_app.to_wl_obj()
        self.ctl_client = controller_client or make_internal_client()

    def start_build_process(
        self,
        version: 'VersionInfo',
        stream_channel_id: str,
        source_tar_path: str,
        procfile: dict,
        extra_envs: Dict[str, str],
    ) -> str:
        """Start a new build process"""
        # get slugbuilder and buildpacks from engine_app
        build_info = SlugbuilderInfo.from_engine_app(self.engine_app)
        # 注入构建环境所需环境变量
        extra_envs = {**extra_envs, **build_info.environments}

        # Create the Build object and start a background build task
        build_process = BuildProcess.objects.create(
            # TODO: Set the correct owner value
            # owner='',
            app=self.wl_engine_app,
            source_tar_path=source_tar_path,
            revision=version.revision,
            branch=version.version_name,
            output_stream=OutputStream.objects.create(),
            image=build_info.build_image or settings.DEFAULT_SLUGBUILDER_IMAGE,
            buildpacks=build_info.buildpacks_info or [],
        )
        builder_task.start_build_process.delay(
            build_process.uuid,
            stream_channel_id=stream_channel_id,
            metadata={
                'procfile': procfile,
                'extra_envs': extra_envs or {},
                'image': build_info.build_image,
                'buildpacks': build_process.buildpacks_as_build_env(),
            },
        )
        return str(build_process.uuid)

    def run_command(
        self, build_id: str, command: str, stream_channel_id: str, operator: str, type_: str, extra_envs: Dict
    ) -> str:
        """run a command in a built slug."""
        build = self.wl_engine_app.build_set.get(pk=build_id)
        cmd_obj = self.wl_engine_app.command_set.new(
            type_=CommandType(type_),
            command=command,
            build=build,
            operator=operator,
        )

        scheduler_tasks.run_command.delay(
            cmd_obj.uuid, stream_channel_id=stream_channel_id, extra_envs=extra_envs or {}
        )
        return str(cmd_obj.uuid)

    def get_command_status(self, command_id: str) -> JobStatus:
        """Get current status of command"""
        command = self.wl_engine_app.command_set.get(pk=command_id)

        # TODO: Write a function which turn CommandStatus into JobStatus
        if command.status == CommandStatus.SCHEDULED.value:
            return JobStatus(CommandStatus.PENDING.value)
        return JobStatus(command.status)

    def list_command_logs(self, command_id: str) -> List[LogLine]:
        """List all logs of command"""
        command = self.wl_engine_app.command_set.get(pk=command_id)
        return [{'stream': line.stream, 'line': line.line, 'created': line.created} for line in command.lines]

    def update_config(self, runtime: Dict[str, Any]):
        """Update engine-app's config"""
        # Save runtime field
        config = self.wl_engine_app.latest_config
        config.runtime = runtime  # type: ignore
        config.save(update_fields=['runtime'])

        # Refresh resource requirements
        config.refresh_res_reqs()

    def create_release(
        self, build_id: str, deployment_id: Optional[str], extra_envs: Dict[str, str], procfile: Dict[str, str]
    ) -> str:
        """Create a new release"""
        build = Build.objects.get(pk=build_id)
        release = build.app.release_set.new(
            # TODO: Set the correct owner value
            owner='',
            build=build,
            procfile=procfile,
        )

        try:
            release_app(release=release, deployment_id=deployment_id, extra_envs=extra_envs)
        except KubeException:
            # TODO: Wrap exception and re-raise
            raise
        return str(release.uuid)

    def get_release(self, release_id: str) -> dict:
        """Get the release object by id"""
        return self.ctl_client.get_app_release(
            region=self.engine_app.region, app_name=self.engine_app.name, release_id=release_id
        )

    def create_build(self, extra_envs: Dict[str, str], procfile: Dict[str, str]) -> str:
        """Create the **fake** build for Image Type App"""
        build = Build.objects.create(
            app=self.wl_engine_app,
            env_variables=extra_envs,
            procfile=procfile,
        )
        return str(build.uuid)

    def get_procfile(self, build_id: str) -> Dict:
        """Get the procfile by build id"""
        return Build.objects.get(pk=build_id).procfile

    def get_build_process(self, build_process_id: str) -> BuildProcess:
        """Get current status of build process"""
        return BuildProcess.objects.get(pk=build_process_id)

    def list_build_proc_logs(self, build_process_id: str) -> List[LogLine]:
        """Get current status of build process"""
        build_proc = BuildProcess.objects.get(pk=build_process_id)

        lines: List[LogLine] = []
        for line in build_proc.output_stream.lines.all().order_by('created'):
            lines.append({'stream': line.stream, 'line': line.line, 'created': line.created})
        return lines

    def update_domains(self, domains: List[Dict]):
        """Update an engine app's domains"""
        self.ctl_client.app_domains__update(
            region=self.engine_app.region, app_name=self.engine_app.name, domains=domains
        )

    def update_subpaths(self, subpaths: List[Dict]):
        """Update an engine app's subpaths"""
        self.ctl_client.update_app_subpaths(
            region=self.engine_app.region, app_name=self.engine_app.name, subpaths=subpaths
        )

    def get_metadata(self) -> Dict[str, Any]:
        """Get an engine app's metadata"""
        return cattr.unstructure(get_metadata(self.wl_engine_app))

    def update_metadata(self, metadata_part: Dict[str, Union[str, bool]]):
        """Update an engine app's metadata, works like python's dict.update()

        :param metadata_part: An dict object which will be merged into app's metadata
        """
        update_metadata(self.wl_engine_app, **metadata_part)

    def upsert_image_credentials(self, registry: str, username: str, password: str):
        """Update an engine app's image credentials, which will be used to pull image."""
        self.ctl_client.upsert_image_credentials(
            region=self.engine_app.region,
            app_name=self.engine_app.name,
            credentials={"registry": registry, "username": username, "password": password},
        )

    def sync_proc_ingresses(self):
        """Sync ingresses configs with engine"""
        self.ctl_client.app_proc_ingress_actions__sync(region=self.engine_app.region, app_name=self.engine_app.name)
