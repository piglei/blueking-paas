# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making
蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
Copyright (C) 2017-2022THL A29 Limited,
a Tencent company. All rights reserved.
Licensed under the MIT License (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
either express or implied. See the License for the
specific language governing permissions and limitations under the License.

We undertake not to change the open source license (MIT license) applicable

to the current version of the project delivered to anyone in the future.
"""
import time

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from paasng.accessories.iam.permissions.resources.application import AppAction, ApplicationPermission, AppPermCtx
from paasng.accounts.permissions.constants import PERM_EXEMPT_TIME_FOR_OWNER_AFTER_CREATE_APP
from paasng.platform.applications.models import Application
from paasng.utils.basic import get_username_by_bkpaas_user_id


def application_perm_class(action: AppAction):
    """
    构建 DRF 可用的应用权限类

    注意：该权限类使用装饰器附加到 viewset 方法时，需要使用 paasng.utils.views.permission_classes 并指定 policy='merge'
    原因是 self.get_application() 时, check_object_permissions 用的是 self.get_permissions，会使用类的权限类
    而 drf 的装饰器只是修改 func.permission_classes，会导致鉴权失效
    """

    class Permission(BasePermission):
        def has_object_permission(self, request, view, obj):
            return user_has_app_action_perm(request.user, obj, action)

    return Permission


def check_application_perm(user, application: Application, action: AppAction):
    """检查指定用户是否对应用的某个操作具有权限"""
    if not user_has_app_action_perm(user, application, action):
        raise PermissionDenied('You are not allowed to do this operation.')


def user_has_app_action_perm(user, application: Application, action: AppAction) -> bool:
    """
    检查指定用户是否对应用的某个操作具有权限

    # TODO 如果后续需要支持 无权限跳转权限中心申请，可以设置 raise_exception = True，PermissionDeniedError 会包含 apply_url 信息
    """
    # 由于权限中心的用户组授权为异步行为，即创建用户组，添加用户，对组授权后需要等待一段时间（10-20秒左右）才能鉴权
    # 因此需要在应用创建后的一定的时间内，对创建者（拥有应用最高权限）的操作进行权限豁免以保证功能可正常使用
    if (
        user.pk == application.owner
        and time.time() - application.created.timestamp() < PERM_EXEMPT_TIME_FOR_OWNER_AFTER_CREATE_APP
    ):
        return True

    perm_ctx = AppPermCtx(
        code=application.code,
        username=get_username_by_bkpaas_user_id(user.pk),
    )
    return ApplicationPermission().get_method_by_action(action)(perm_ctx, raise_exception=False)
