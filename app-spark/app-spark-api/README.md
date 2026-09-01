# app-spark-api

## 开发指南

在 `manage.py` 文件同目录下创建 `settings_local.yaml`，添加必要的配置内容：

```yaml
# 必选：统一登录页面地址
LOGIN_FULL: ...

# 必选：BKAUTH 用户认证相关配置（具体值请参考当前开发环境）
BKAUTH_BACKEND_TYPE: ...
BKAUTH_TOKEN_APP_CODE: ...
BKAUTH_TOKEN_SECRET_KEY: ...
BKAUTH_TOKEN_USER_INFO_ENDPOINT: ...
BKAUTH_USER_COOKIE_VERIFY_URL: ...

# 必选：数据库配置，必须使用 MySQL 8.X 版本以上数据库
DATABASE_NAME: ...
DATABASE_USER: ...
DATABASE_PASSWORD: ...
DATABASE_HOST: ...
DATABASE_PORT: ...
```

### 启动服务

使用 uvicorn 启动 ASGI 开发服务：

```bash
uv run uvicorn app_spark_api.asgi:application --reload
```

必须用 ASGI 服务器（uvicorn）启动。会话接口要把 Agent 的 SSE 事件流边收边转发，
在 WSGI 下这个流会被缓冲到结束才吐出来，等于失去流式的意义。

### 运行测试

```bash
uv run pytest --reuse-db tests/
```

会话相关的测试不 mock agent，而是真的 spawn agent 进程、走真实 HTTP。

## 驱动 Agent

一个会话（conversation）对应一个 Agent Runtime 进程。API 负责建会话、按需拉起 Runtime、
把用户消息发过去，并把 Runtime 返回的 AG-UI 事件流原样透传给前端。

### 配置

```yaml
## Agent Runtime 的驱动方式，目前只有 local_process（在本机 spawn 进程）
AGENT_RUNTIME_PROVIDER: local_process
AGENT_RUNTIME_PROVIDER_CONFIG:
  ## agent 项目目录，`uv run --project` 指向它
  agent_project_dir: ../agent
  ## 每个 Project 的 workspace 建在这下面
  workspace_root: /tmp/app-spark/workspaces
  ## 每个会话的持久化状态（log.jsonl / ui_events.jsonl / context.json）建在这下面。
  ## 必须在 workspace_root 之外，否则 agent 自己的文件工具能改掉自己的历史。
  state_root: /tmp/app-spark/agent-state
  ## 可选，留空则用 agent 自己的默认值
  # model: deepseek:deepseek-v4-flash
  # api_key: ...
  ## 可选，追加传给 agent 进程的 APP_SPARK_AGENT_* 环境变量
  # extra_env:
  #   APP_SPARK_AGENT_FAKE_DELAY_SECONDS: "3"
```

**前置条件**：local_process 用 `uv run --project <agent_project_dir> --no-sync` 拉起 Runtime，
`--no-sync` 意味着它不会在请求路径上解析依赖，所以 agent 的虚拟环境必须提前备好：

```bash
cd ../agent && uv sync
```

本地想不花钱跑通整条链路时，把 `model` 设成 `fake:write-file`——
这是 agent 内置的确定性假模型，不发起任何网络请求，
细节见 [agent/README.md](../agent/README.md) 的「假模型」一节。
