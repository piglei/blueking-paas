### 资源描述

查询蓝鲸插件的分类列表，仅供内部系统使用。

### 认证方式

使用 Bearer 方式认证，具体的 token 请向管理员申请。

### 输入参数说明

|   参数名称   |    参数类型  |  必须  |     参数说明     |
| ------------ | ------------ | ------ | ---------------- |
| private_token | string      | 否   | PaaS 平台分配的 token,当请求方的应用身份未被 PaaS 平台认证时必须提供|


### 返回结果

```javascript
[
    {
        "code_name": "tag1",
        "name": "分类1",
        "id": 1
    }
]
```