# App-Spark Agent Runtime

这是一个独立的、有状态的编码 Agent 服务。一个进程绑定一个 Chat 会话和一个 workspace，
通过 AG-UI HTTP/SSE 接收新消息，并在 workspace 外持久化会话状态。

## TODO

- 冷启动只恢复上下文、不恢复 workspace 源码（见「远程持久化」一节）
- 改造为可以基于独立容器启动
- 支持在沙箱环境中启动
- 增加开发蓝鲸 SaaS 相关 SKILL
- `RunGuard` 目前基于 asyncio 锁，只能保护单进程，后续应替换为文件锁

## 安装与启动

需要 Python 3.14 与 uv。本地运行只需三个配置：workspace、状态目录和模型 API Key，然后启动：

```bash
uv sync
export APP_SPARK_AGENT_WORKSPACE=/tmp/app-spark-workspace
export APP_SPARK_AGENT_STATE_DIR=/tmp/app-spark-state
export APP_SPARK_AGENT_API_KEY="..."

uv run uvicorn app_spark_agent.server.asgi:app --port 8765
```

接口没有鉴权，请保持 uvicorn 默认的回环地址，不要监听 `0.0.0.0`；需要对外暴露时由外层
基础设施负责鉴权和网络隔离。

## 配置

全部配置项集中在 `app_spark_agent/settings.py`，由 environs 在导入时从 `APP_SPARK_AGENT_*`
环境变量解析并校验（`.env` 文件也会自动读取），完整清单以该文件为准。其中 `WORKSPACE` 与
`STATE_DIR` 没有默认值、真正建应用时才检查；其余项（模型、压缩策略、游标 limit 等）都有
合理默认值。

## 假模型

`MODEL` 除了 `<provider>:<model>`，还接受 `fake:<scenario>`——一个不发起任何网络请求的确定性
模型。它存在的理由是：外部控制面（app-spark-api）要做的是
把 Runtime 当成真进程来集成，与其在控制面那边把整个 Agent mock 掉，不如让 Runtime 本身能被
零成本地真正启动——这样跑的就是真进程、真 HTTP、真 SSE、真文件写入。

```bash
APP_SPARK_AGENT_MODEL=fake:write-file uv run uvicorn app_spark_agent.server.asgi:app --port 8765
```

目前支持的假模型场景详情可查看 `fake_model.py`。

## 会话状态

会话状态按「怎么变」分成三类，都由 `app_spark_agent/state/` 下的类型实现：

| 数据 | 文件 | 形态 | 实现类型 | 单测 |
| --- | --- | --- | --- | --- |
| 原始对话记录 | `log.jsonl` | append-only，`seq` 连续递增 | `AppendLog` / `LogRecord`（`state/log.py`） | `tests/state/test_log.py` |
| AG-UI 事件历史 | `ui_events.jsonl` | append-only，`seq` 连续递增 | `AppendLog`（同上） | `tests/state/test_log.py` |
| 会话上下文 | `context.json` | 可变 blob，原子整体替换，带 `context_version` | `ContextStore` / `ConversationContext`（`state/context.py`） | `tests/state/test_context.py` |

关键点：

- 压缩发生在每轮 run 的中间（每次模型请求之前）并把结果写回历史，因此原始记录必须在消息
  产生的瞬间抄走、不能等 run 结束再导出——由最外层的 `TranscriptRecorder` capability 负责
  （`recorder.py`）。
- `context_version` 不等于轮次：一轮里压缩触发几次就提交几次，控制面不要假设两者同步。
- `SummarizingCompaction` 是一次不可重放的真实 LLM 调用，冷启动重建上下文的唯一来源是
  `context.json`，绝不能从 `log.jsonl` 拼出来。

## 远程持久化

配置了控制面地址之后，上面这三份文件不再是唯一副本：`app_spark_agent/replication/` 下的后台
任务会把它们复制到控制面，状态目录退化成一个可以丢弃的本地缓冲。

| 配置项 | 作用 |
| --- | --- |
| `CONTROL_PLANE_URL` | 已经带上会话前缀的完整地址。Runtime 因此不需要认识「会话」这个概念 |
| `CONTROL_PLANE_TOKEN` | spawn 时注入的 token，只授权这一个会话 |
| `PUSH_BATCH_SIZE` | 单次 ingest 调用最多带几条 |
| `PUSH_RETRY_BACKOFF_SECONDS` | 一轮推送失败后等多久重试 |
| `PUSH_FLUSH_TIMEOUT_SECONDS` | run 收尾时等控制面追上的上限 |

两条规则值得单独记住：

- **run 结束时有一道屏障，但它只是屏障、不是保证**。`finish_response` 里先 `flush`、再释放
  `run_guard`。flush 超时**不会让 run 失败**——数据还在本地文件里、后台任务会继续重试——而
  `run_guard` 照样会释放（控制面挂了不该把会话锁死在下一轮之外）。所以「Runtime 空闲」并不等于
  「这一轮已经在控制面上」，两个信号要一起看：`/health` 的 `replication_pending` 说的是「还有没
  推完的东西」，落后多少看 `pushed_*`。真正的残余风险是容器在落后期间被回收。
- **`flush` 的返回值是「控制面是否真的追平了」**，不是「这一趟有没有报错」。它在 drain 之后比对
  游标得出结论：一趟干净跑完但仍然落后（比如中途有新 append，或者某个频道的缺口没补上）会返回
  `False` 并重新举旗，让后台任务接着做。频道缺口在同一趟里就重发补齐，不留给「下一趟」——空闲
  会话根本没有下一次 append 来触发它。
- **冷启动要播种 seq，否则会撞号**。全新 Runtime 的 `log.jsonl` 默认从 seq 1 开始，会撞上控制面
  里已有的 1..N。所以 `PUT /context` 带 `?log_seq=40&ui_event_seq=55`，`AppendLog` 以此为
  `base_seq`，第一条 append 变成 41。游标走 query 参数而不是 body，是因为 body 必须原样保持
  `GET /context` 吐出来的那份文档。

已知缺口，按严重程度排：

- **workspace 源码不恢复**。冷启动后上下文里会引用一堆不存在的文件——Agent「记得」自己写过
  `index.html`，但目录是空的。所以冷启动目前只在「继续讨论」层面成立，不在「继续编码」层面
  成立。衔接点在控制面的 `ProjectSourceStorage`：注入 context 之前先把源码还原回去。
- `AppendLog.has_run()` 的重放检测只覆盖当代文件，冷启动后旧的 run_id 不再会被拒绝。控制面每轮
  都生成新 UUID，所以现实中碰不到。

## 发起会话

`POST /runs` 接收 AG-UI 请求体，返回一段 SSE 事件流，里面全部是可以直接转发给前端的 AG-UI
事件：

```bash
curl -N http://127.0.0.1:8765/runs \
  -H 'Accept: text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{
    "threadId": "demo-conversation",
    "runId": "4c1889a5-0500-4c7d-877a-d933a5a28e51",
    "state": {},
    "messages": [{
      "id": "cb39dbbf-a3db-46ff-bb1d-e15a9003c658",
      "role": "user",
      "content": "Create only index.html containing Hello World."
    }],
    "tools": [],
    "context": [],
    "forwardedProps": {"contextVersion": 0}
  }'
```

请求只需携带最新一条用户消息，展示历史会被丢弃，只使用 Runtime 自己的可信上下文；第一次
运行的 `contextVersion` 是 `0`。流结束即本轮完成，之后访问 `/health` 确认会话成功：
`running` 回到 `false`，且 `context_version`、`log_seq`、`ui_event_seq` 都已经前进。

## 游标接口

以下接口是提供给外部访问会话状态的通道：`/health` 报三份状态的当前游标、运行标志，以及
`pushed_*` 复制游标与 `replication_pending`（都只在配了控制面时才有意义），`/log` 与
`/ui-events` 按游标增量读取两条日志，`/context` 导出当前上下文（也可向空 Runtime 注入冷会话
上下文并播种 seq）。

> 具体参数与返回结构以代码实现为准。

## 开发指南

### 单元测试

默认的测试命令不请求真实模型、不需要 API Key：

```bash
uv run pytest
```

`tests/api/` 跑在进程内注入的假模型上，完整覆盖 HTTP 接口的正确与错误分支；状态原语、Agent
组装、压缩、事件合并在 `tests/` 其余模块。`tests/replication/` 用 `httpx.MockTransport` 在进程
内伪造控制面，但状态文件、游标、字节偏移全是真的——整套设计就架在「文件即 outbox」上。

`tests/live/` 用 uvicorn 拉起**真实进程**，但模型是 `fake:` 场景，所以默认就跑。它覆盖
的是进程内测试结构上够不到的那一段：Runtime 由 `create_app_from_settings()` 只凭环境变量装配
起来——这正是任何外部控制面启动它的方式，而一个只能进程内注入的假模型对它们毫无用处。
`test_replication.py` 是同一个道理：它在环回端口上跑一个假控制面，验证「跑完一轮 → 换一个状态
目录全空的新进程 → 对话接着上一轮继续」，并且两代 Runtime 的 seq 拼成一条不重号的平坦序列。

### E2E 测试

`tests/e2e/` 会用 uvicorn 拉起真实 Runtime 去基于真实 DeepSeek 执行 Agent 任务，和部署方式完全一致，所有断言
都走 HTTP。设置好有效配置后：

```bash
echo 'APP_SPARK_AGENT_API_KEY=sk-...' > .env   # 已在 .gitignore 中
uv run pytest tests/e2e -s
```

`-s` 作用：每次模型调用都会实时打到控制台——请求与响应、工具调用与结果、逐 token 出现
的回答。挑一个 `tests/e2e/test_coding_session.py` 跑起来，看 Agent 读文件、写文件、执行命令、
流式输出，再配合回读 `/log`、`/ui-events`、`/context`，是掌握这套 Runtime 工作过程最快的方式。
