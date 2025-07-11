/*
 * TencentBlueKing is pleased to support the open source community by making
 * 蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
 * Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
 * Licensed under the MIT License (the "License"); you may not use this file except
 * in compliance with the License. You may obtain a copy of the License at
 *
 *     http://opensource.org/licenses/MIT
 *
 * Unless required by applicable law or agreed to in writing, software distributed under
 * the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
 * either express or implied. See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * We undertake not to change the open source license (MIT license) applicable
 * to the current version of the project delivered to anyone in the future.
 */

/*
* 工具
*/
import http from '@/api';
import { json2Query } from '@/common/tools';

export default {
  namespaced: true,
  actions: {
    /**
     * 获取应用描述文件转换内容
     */
    getDescriptionFileConversion({}, { data, config }) {
      const url = `${BACKEND_URL}/api/tools/app_desc/transform/`;
      return http.post(url, data, config);
    },
    /**
     * tool-获取当前已启用服务的应用列表
     */
    getEnabledServiceAppList({}, { name, params }) {
      const url = `${BACKEND_URL}/api/services/name/${name}/application-attachments/?${json2Query(params)}`;
      return http.get(url);
    },
  },
};
