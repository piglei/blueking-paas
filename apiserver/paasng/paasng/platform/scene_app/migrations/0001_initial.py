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

# Generated by Django 3.2.12 on 2022-06-22 03:12

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='SceneTmpl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=64, unique=True, verbose_name='名称')),
                ('display_name_zh_cn', models.CharField(blank=True, max_length=64, verbose_name='展示名称')),
                ('display_name_en', models.CharField(blank=True, max_length=64, verbose_name='展示名称')),
                ('description_zh_cn', models.CharField(blank=True, max_length=1024, verbose_name='描述')),
                ('description_en', models.CharField(blank=True, max_length=1024, verbose_name='描述')),
                ('enabled', models.BooleanField(default=True, verbose_name='是否启用')),
                ('tags', models.JSONField(blank=True, default=list, max_length=256, verbose_name='标签')),
                ('region', models.CharField(max_length=32, verbose_name='应用版本')),
                ('repo_url', models.CharField(blank=True, max_length=512, verbose_name='代码仓库地址')),
                ('blob_url', models.CharField(max_length=512, verbose_name='源码包地址（对象存储）')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
