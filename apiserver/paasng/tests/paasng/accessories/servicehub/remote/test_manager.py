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

import datetime
import uuid
from dataclasses import asdict
from typing import Dict
from unittest import mock

import pytest
from django_dynamic_fixture import G

from paasng.accessories.servicehub.binding_policy.manager import ServiceBindingPolicyManager
from paasng.accessories.servicehub.exceptions import (
    BindServicePlanError,
    CanNotModifyPlan,
    ServiceObjNotFound,
)
from paasng.accessories.servicehub.manager import mixed_service_mgr
from paasng.accessories.servicehub.models import RemoteServiceEngineAppAttachment
from paasng.accessories.servicehub.remote import RemoteServiceMgr, collector
from paasng.accessories.servicehub.remote.manager import MetaInfo, RemoteEngineAppInstanceRel, RemotePlanObj
from paasng.accessories.servicehub.remote.store import get_remote_store
from tests.paasng.accessories.servicehub import data_mocks
from tests.utils.api import mock_json_response

from .utils import gen_plan

pytestmark = [
    pytest.mark.django_db(databases=["default", "workloads"]),
    pytest.mark.xdist_group(name="remote-services"),
]


class TestRemotePlanObj:
    def test_from_data(self):
        raw = {
            "description": "通用集群",
            "name": "default",
            "properties": {"is_eager": True, "region": "test"},
            "uuid": "123",
            "specifications": {},
        }

        plan = RemotePlanObj.from_data(raw)
        assert plan.is_eager == raw["properties"]["is_eager"]  # type: ignore
        assert plan.uuid == raw["uuid"]
        assert plan.is_active is True
        assert plan.description == raw["description"]
        assert plan.name == raw["name"]


class TestRemoteEngineAppInstanceRel:
    @pytest.fixture(autouse=True)
    def _setup_data(self, config, store, bk_app, bk_module):
        bk_app.region = "r1"
        bk_module.region = "r1"
        bk_app.save()
        bk_module.save()

    @pytest.mark.parametrize(("is_eager", "env"), [(True, "stag"), (False, "stag"), (True, "prod"), (False, "prod")])
    def test_get_plan(self, bk_module, is_eager, env):
        env = bk_module.get_envs(env)
        plan_id = uuid.uuid4()
        service_id = uuid.uuid4().hex
        attachment: RemoteServiceEngineAppAttachment = G(
            RemoteServiceEngineAppAttachment,
            engine_app=env.engine_app,
            service_id=service_id,
            plan_id=plan_id,
        )
        plan_data = {
            "uuid": str(plan_id),
            "name": "",
            "description": "",
            "properties": {
                "region": bk_module.region,
                "is_eager": is_eager,
            },
            "specifications": {},
        }
        store = mock.MagicMock(
            get=mock.MagicMock(
                return_value={
                    "plans": [plan_data],
                }
            )
        )

        rel = RemoteEngineAppInstanceRel(attachment, mock.MagicMock(plan_id=plan_id), store)
        plan = rel.get_plan()
        assert plan.uuid == plan_data["uuid"]
        assert plan.name == plan_data["name"]
        assert plan.description == plan_data["description"]
        assert plan.is_eager is plan_data["properties"]["is_eager"]  # type: ignore
        assert plan.properties == plan_data["properties"]

    @mock.patch("paas_wl.workloads.networking.egress.shim.get_cluster_egress_info")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_provision(self, mocked_provision, get_cluster_egress_info, store, bk_module, bk_service_ver):
        """Test service instance provision"""
        get_cluster_egress_info.return_value = {"egress_ips": ["1.1.1.1"], "digest_version": "foo"}
        plans = [gen_plan("r1", {}, {})]
        mgr = RemoteServiceMgr(store=store)
        bk_service_ver.plans = plans

        # Set the binding policy and bind
        ServiceBindingPolicyManager(bk_service_ver).set_static([plans[0]])
        mgr.bind_service(bk_service_ver, bk_module)

        with mock.patch.object(mgr, "get") as get_service:
            get_service.return_value = bk_service_ver

            for env in bk_module.envs.all():
                expected_plan = plans[0]
                for rel in mgr.list_unprovisioned_rels(env.engine_app):
                    assert rel.is_provisioned() is False
                    rel.provision()

                    assert rel.is_provisioned() is True
                    assert str(rel.db_obj.service_id) == bk_service_ver.uuid
                    assert str(rel.db_obj.plan_id) == expected_plan.uuid

                    assert mocked_provision.called
                    assert len(mocked_provision.call_args[0]) == 3
                    assert bool(all(mocked_provision.call_args[0]))
                    assert mocked_provision.call_args[1]["params"]["username"] == rel.db_engine_app.name

    @mock.patch("paasng.accessories.servicehub.remote.manager.EnvClusterInfo.get_egress_info")
    def test_render_params(self, mock_get_egress_info, store, bk_app, bk_module, bk_service_ver):
        mock_get_egress_info.return_value = {}
        mgr = RemoteServiceMgr(store=store)
        bk_service_ver.plans = [gen_plan("r1", {}, {})]

        # Set the binding policy and bind
        ServiceBindingPolicyManager(bk_service_ver).set_static([bk_service_ver.plans[0]])
        mgr.bind_service(bk_service_ver, bk_module)

        env = bk_module.get_envs("stag")
        engine_app = env.engine_app
        for rel in mgr.list_unprovisioned_rels(env.engine_app):
            result = rel.render_params(
                {
                    "engine_app_name": "{engine_app.name}",
                    "application_code": "{application.code}",
                    "module_name": "{module.name}",
                    "environment": "{env.environment}",
                    "egress_info": "{cluster_info.egress_info_json}",
                }
            )
            assert result["engine_app_name"] == engine_app.name
            assert result["application_code"] == bk_app.code
            assert result["module_name"] == bk_module.name
            assert result["environment"] == env.environment
            assert result["egress_info"] == "{}"


class TestRemoteMgrWithRealStore:
    """与 remote store 相关的集成测试(即不 mock store 的行为)"""

    @pytest.fixture(autouse=True)
    def _setup_data(
        self, config, store, bk_app, bk_module, bk_service_ver, bk_plan_r1_v1, bk_plan_r1_v2, bk_plan_r2_v1
    ):
        bk_app.region = "r1"
        bk_module.region = "r1"
        bk_app.save()
        bk_module.save()

        meta_info = {"version": None}
        with mock.patch("requests.get") as mocked_get:
            # Mock requests response
            bk_service_ver.plans = [bk_plan_r1_v1, bk_plan_r1_v2, bk_plan_r2_v1]
            mocked_get.return_value = mock_json_response(
                [
                    dict(category=1, **asdict(bk_service_ver)),
                ]
            )
            fetcher = collector.RemoteSvcFetcher(config)
            store.bulk_upsert(fetcher.fetch(), meta_info=meta_info, source_config=config)
            yield
            store.empty()

    @pytest.fixture()
    def bk_service(self, request):
        return request.getfixturevalue(request.param)

    @pytest.mark.parametrize(
        ("bk_service", "name", "found"),
        [
            ("bk_service_ver", ..., True),
            ("bk_service_ver", "sth-wrong", False),
            ("bk_service_ver_zone", "sth-wrong", False),
            ("bk_service_ver_zone", ..., False),
        ],
        indirect=["bk_service"],
    )
    def test_find_by_name(self, store, bk_module, bk_service, name, found):
        mgr = RemoteServiceMgr(store=store)
        name = name if name is not ... else bk_service.name
        if found:
            assert mgr.find_by_name(name, region=bk_module.region) == bk_service
        else:
            with pytest.raises(ServiceObjNotFound):
                mgr.find_by_name(name=name, region=bk_module.region)

    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_module_rebind_failed_after_provision(self, mock_provision_instance, store, bk_module, bk_service_ver):
        mgr = RemoteServiceMgr(store=store)

        plans = bk_service_ver.plans
        ServiceBindingPolicyManager(bk_service_ver).set_static([plans[0]])
        mgr.bind_service(bk_service_ver, bk_module)
        env = bk_module.get_envs("stag")

        for rel in mgr.list_unprovisioned_rels(env.engine_app, bk_service_ver):
            rel.provision()
            assert rel.is_provisioned() is True

        # Change the binding policy
        ServiceBindingPolicyManager(bk_service_ver).set_static([plans[1]])
        with pytest.raises(CanNotModifyPlan):
            mgr.bind_service(bk_service_ver, bk_module)

        for rel in mgr.list_unprovisioned_rels(env.engine_app, bk_service_ver):
            plan = rel.get_plan()
            assert plan.name == plans[0].name


class TestRemoteMgrWithMockedStore:
    @pytest.fixture(autouse=True)
    def _setup_data(self, config, store, bk_app, bk_module, bk_service_ver):
        bk_app.region = "r1"
        bk_module.region = "r1"
        bk_app.save()
        bk_module.save()

        plans = [gen_plan("r1", {}, {})]
        bk_service_ver.plans = plans

    def test_bind_service(self, store, bk_module, bk_service_ver):
        mgr = RemoteServiceMgr(store=store)
        ServiceBindingPolicyManager(bk_service_ver).set_static([bk_service_ver.plans[0]])
        mgr.bind_service(bk_service_ver, bk_module)

    def test_bind_service_no_plans(self, store, bk_module, bk_service_ver):
        mgr = RemoteServiceMgr(store=store)
        with pytest.raises(BindServicePlanError):
            mgr.bind_service(bk_service_ver, bk_module)


id_of_first_service: str = data_mocks.OBJ_STORE_REMOTE_SERVICES_JSON[0]["uuid"]


class TestRemoteMgr:
    app_region = "r1"

    @pytest.fixture(autouse=True)
    def _setup_data(self, _faked_remote_services, store, bk_app, bk_module):
        # Update app and module fixture's region
        bk_app.region = self.app_region
        bk_app.save(update_fields=["region"])
        bk_module.region = self.app_region
        bk_module.save(update_fields=["region"])

        # Initialize with a static binding policy
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(id_of_first_service, region=bk_module.region)
        ServiceBindingPolicyManager(svc).set_static([svc.get_plans()[0]])

    @pytest.fixture()
    def store(self):
        return get_remote_store()

    def test_list_binded(self, store, bk_app, bk_module):
        mgr = RemoteServiceMgr(store=store)
        assert list(mgr.list_binded(bk_module)) == []
        for env in bk_app.envs.all():
            assert list(mgr.list_unprovisioned_rels(env.engine_app)) == []

        svc = mgr.get(id_of_first_service, region=bk_module.region)
        rel_pk = mgr.bind_service(svc, bk_module)
        assert rel_pk is not None
        assert list(mgr.list_binded(bk_module)) == [svc]
        for env in bk_app.envs.all():
            assert len(list(mgr.list_unprovisioned_rels(env.engine_app))) == 1

    @mock.patch("paasng.accessories.servicehub.remote.manager.get_cluster_egress_info")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.retrieve_instance")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_get_instance_has_create_time_attr(
        self, mocked_provision, mocked_retrieve, get_cluster_egress_info, store, bk_app, bk_module
    ):
        get_cluster_egress_info.return_value = {"egress_ips": ["1.1.1.1"], "digest_version": "foo"}
        mgr = RemoteServiceMgr(store=store)

        svc = mgr.get(id_of_first_service, region=bk_module.region)
        mgr.bind_service(svc, bk_module)
        env = bk_app.envs.first()
        for rel in mgr.list_unprovisioned_rels(env.engine_app):
            rel.provision()

            # Mock retrieve response
            data = data_mocks.REMOTE_INSTANCE_JSON.copy()
            data["uuid"] = rel.db_obj.service_instance_id
            mocked_retrieve.return_value = data

            instance = rel.get_instance()
            assert isinstance(instance.create_time, datetime.datetime)

    @mock.patch("paasng.accessories.servicehub.remote.manager.get_cluster_egress_info")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.retrieve_instance")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_get_instance(self, mocked_provision, mocked_retrieve, get_cluster_egress_info, store, bk_app, bk_module):
        """Test service instance provision"""
        get_cluster_egress_info.return_value = {"egress_ips": ["1.1.1.1"], "digest_version": "foo"}
        mgr = RemoteServiceMgr(store=store)

        svc = mgr.get(id_of_first_service, region=bk_module.region)
        mgr.bind_service(svc, bk_module)
        for env in bk_app.envs.all():
            for rel in mgr.list_unprovisioned_rels(env.engine_app):
                assert rel.is_provisioned() is False
                rel.provision()

                # Mock retrieve response
                data = data_mocks.REMOTE_INSTANCE_JSON.copy()
                data["uuid"] = rel.db_obj.service_instance_id
                mocked_retrieve.return_value = data

                instance = rel.get_instance()

                assert len(instance.credentials) == 5
                assert instance.credentials["CEPH_BUCKET"] == "pig-bucket-2"

                assert mixed_service_mgr.get_env_vars(env.engine_app) != {}

    @mock.patch("paasng.accessories.servicehub.remote.manager.get_cluster_egress_info")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.retrieve_instance")
    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_get_env_vars_with_exclude_disabled(
        self,
        mocked_provision,
        mocked_retrieve,
        get_cluster_egress_info,
        store,
        bk_app,
        bk_module,
    ):
        get_cluster_egress_info.return_value = {"egress_ips": ["1.1.1.1"], "digest_version": "foo"}
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(id_of_first_service, region=bk_module.region)
        mgr.bind_service(svc, bk_module)
        for env in bk_app.envs.all():
            for rel in mgr.list_unprovisioned_rels(env.engine_app):
                assert rel.is_provisioned() is False
                rel.provision()

                # Mock retrieve response
                data = data_mocks.REMOTE_INSTANCE_JSON.copy()
                data["uuid"] = rel.db_obj.service_instance_id
                mocked_retrieve.return_value = data

                assert (
                    mixed_service_mgr.get_env_vars(env.engine_app, filter_enabled=True)["CEPH_BUCKET"]
                    == data["credentials"]["bucket"]  # type: ignore
                )

                # 测试配置 credentials_enabled 后， 不导入环境变量
                attachment = mixed_service_mgr.get_attachment_by_engine_app(svc, env.engine_app)
                attachment.credentials_enabled = False
                attachment.save(update_fields=["credentials_enabled"])

                assert mixed_service_mgr.get_env_vars(env.engine_app, filter_enabled=True) == {}

    def test_get_attachment_by_instance_id(self, store, bk_module):
        expect_obj: Dict[uuid.UUID, RemoteServiceEngineAppAttachment] = {}

        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(id_of_first_service, region=bk_module.region)

        # 绑定服务并创建服务实例
        mgr.bind_service(svc, bk_module)
        for env in bk_module.envs.all():
            for rel in mixed_service_mgr.list_unprovisioned_rels(env.engine_app, svc):
                plan = rel.get_plan()
                if plan.is_eager:
                    with mock.patch(
                        "paasng.accessories.servicehub.remote.client.RemoteServiceClient"
                    ) as mocked_client:
                        mocked_client().provision_instance = mock.MagicMock()
                        rel.provision()
                        expect_obj[rel.db_obj.service_instance_id] = rel.db_obj

        for _id, expected_val in expect_obj.items():
            assert mgr.get_attachment_by_instance_id(svc, _id) == expected_val


class TestLegacyRemoteMgr:
    app_region = "rr1"
    uuid = data_mocks.OBJ_STORE_REMOTE_SERVICES_JSON[2]["uuid"]

    @pytest.fixture(autouse=True)
    def _setup_data(self, _faked_remote_services, store, bk_app, bk_module):
        # Update app and module fixture's region
        bk_app.region = self.app_region
        bk_app.save(update_fields=["region"])
        bk_module.region = self.app_region
        bk_module.save(update_fields=["region"])

        # Initialize with a static binding policy
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(self.uuid, region=bk_module.region)
        ServiceBindingPolicyManager(svc).set_static([svc.get_plans()[0]])

    @pytest.fixture()
    def store(self):
        return get_remote_store()

    def test_bind_service(self, store, bk_module):
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(self.uuid, region=bk_module.region)
        mgr.bind_service(svc, bk_module)
        assert mgr.module_is_bound_with(svc, bk_module) is True

    def test_list_binded(self, store, bk_app, bk_module):
        mgr = RemoteServiceMgr(store=store)
        assert list(mgr.list_binded(bk_module)) == []
        for env in bk_app.envs.all():
            assert list(mgr.list_unprovisioned_rels(env.engine_app)) == []

        svc = mgr.get(self.uuid, region=bk_module.region)
        assert mgr.bind_service(svc, bk_module) is not None
        assert list(mgr.list_binded(bk_module)) == [svc]
        for env in bk_app.envs.all():
            assert len(list(mgr.list_unprovisioned_rels(env.engine_app))) == 1

    def test_module_rebind(self, store, bk_module):
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(self.uuid, region=bk_module.region)

        assert mgr.module_is_bound_with(svc, bk_module) is False

        mgr.bind_service(svc, bk_module)
        assert mgr.module_is_bound_with(svc, bk_module) is True

        mgr.bind_service(svc, bk_module)
        assert mgr.module_is_bound_with(svc, bk_module) is True

    @mock.patch("paasng.accessories.servicehub.remote.client.RemoteServiceClient.provision_instance")
    def test_module_rebind_failed_after_provision(self, mock_provision_instance, store, bk_module):
        mgr = RemoteServiceMgr(store=store)
        svc = mgr.get(self.uuid, region=bk_module.region)

        mgr.bind_service(svc, bk_module)
        assert bk_module.envs.count() > 1
        env = bk_module.envs.last()  # 只申请一个,测试事务性
        for rel in mixed_service_mgr.list_unprovisioned_rels(env.engine_app, svc):
            rel.provision()
            assert rel.is_provisioned() is True

        with pytest.raises(CanNotModifyPlan):
            mgr.bind_service(svc, bk_module)


class TestMetaInfo:
    def test_semantic_version_gte_none_version(self):
        assert MetaInfo(version=None).semantic_version_gte("0.0.1") is False

    @pytest.mark.parametrize(
        ("one", "other", "expected"),
        [
            ("0.13.3", "0.4.1", True),
            ("0.13.3", "0.0.1", True),
            ("0.13.3", "0.20.1", False),
            ("0.13.3", "1.0.1", False),
            ("0.4.1", "0.13.3", False),
            ("0.0.1", "0.13.3", False),
            ("0.20.1", "0.13.3", True),
            ("1.0.1", "0.13.3", True),
            ("1.1.1", "1.1.1", True),
        ],
    )
    def test_semantic_version_gte_normal(self, one, other, expected):
        assert MetaInfo(version=one).semantic_version_gte(other) is expected
