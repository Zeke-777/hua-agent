# 花卉研究 Agent - 项目总结

> 两阶段 LangGraph + FastAPI 花卉研究系统，支持图片上传识别与结构化报告生成，具备多用户认证与会话记忆。

---

## 架构概览

```
用户输入花卉名 / 上传图片
      │
      ▼
┌─────────────────────────────────┐
│         Stage 1（硬编码工作流）     │
│  search → extract → report      │
│  确定性执行，强制结构化输出         │
│  输出 FlowerInfo（9字段）          │
└──────────┬──────────────────────┘
           │ 结构化报告存入共享记忆
           ▼
┌─────────────────────────────────┐
│         Stage 2（自由问答 Agent）  │
│  Tavily 搜索 + 对话记忆          │
│  基于 Stage 1 报告回答追问        │
└─────────────────────────────────┘
```

- **Stage 1**: LangGraph `StateGraph` 硬编码三节点工作流：Tavily 搜索 → LLM 结构化提取 (`FlowerInfo`) → 格式化报告。保证一定输出结构化数据。
- **Stage 2**: LangChain `create_agent`，带 TavilySearch 工具和对话记忆，可基于已有报告回答追问或搜索新信息。
- **记忆共享**: 两端共用 `SqliteSaver` checkpointer，同一 `thread_id` 实现记忆连续。

---

## 技术栈

| 类别       | 技术                                     |
| -------- | -------------------------------------- |
| LLM      | DeepSeek V4 Flash (OpenAI 兼容 API)      |
| Agent 框架 | LangChain + LangGraph                  |
| 搜索工具     | TavilySearch                           |
| 结构化输出    | Pydantic v2 + `with_structured_output` |
| 后端       | FastAPI (异步) + uvicorn                 |
| 数据库      | SQLite (用户/会话/token + Agent 记忆)        |
| 对象存储     | 华为云 OBS (`esdk-obs-python`)            |
| 前端       | 单文件 SPA (HTML + 内嵌 CSS/JS)             |
| 包管理      | uv                                     |
| Python   | >=3.10                                 |

---

## 目录结构

```
hua-agent/
├── hua_agent/                  # Python 包
│   ├── __init__.py
│   ├── models.py               # FlowerInfo + ResearchResponse + ChatRequest Pydantic 模型
│   ├── db.py                   # 数据库层（用户/会话/token，线程安全）
│   ├── stage1_workflow.py      # Stage 1: 硬编码 LangGraph 工作流
│   ├── stage2_agent.py         # Stage 2: Q&A agent 工厂
│   ├── obs_client.py           # 华为云 OBS 图片上传
│   └── server.py               # FastAPI HTTP 服务入口
├── static/
│   └── dist/
│       └── index.html           # 验证前端 SPA（单文件，内嵌 CSS + JS）
├── usersdata/                  # SQLite 运行时数据（自动创建）
│   ├── agent_memory.db         # LangGraph checkpointer
│   └── meta.db                 # 用户/会话/token
├── pyproject.toml
├── CLAUDE.md
└── .env                        # API Keys
```

---

## 模块说明

### `models.py` — 数据模型

`FlowerInfo` Pydantic 模型，9 个字段：

| 字段    | 约束          | 说明        |
| ----- | ----------- | --------- |
| 名称    | -           | 花卉中文名     |
| 形态结构  | ≤100 字，自动截断 | 植株形态      |
| 植物分类  | ≤100 字，自动截断 | 分类学信息     |
| 生长习性  | ≤100 字，自动截断 | 环境偏好      |
| 花期规律  | ≤100 字，自动截断 | 开花时间      |
| 气味与特征 | ≤100 字，自动截断 | 香气与外观     |
| 繁殖方式  | ≤100 字，自动截断 | 繁殖方法      |
| 使用价值  | ≤100 字，自动截断 | 观赏/药用等    |
| 文化寓意  | ≤100 字，自动截断 | 象征意义      |
| 参考来源  | 格式验证        | 编号 URL 列表 |

`ResearchResponse` — `/api/research` 和 `/api/upload` 的统一响应模型：

```python
class ResearchResponse(BaseModel):
    ok: bool
    stage: int
    session_id: str
    flower_name: str
    flower_info: dict | None = None
    image_url: str | None = None
```

### `db.py` — 数据库层

三张表：

- **users**: `username, password_hash, salt, created_at` — SHA256 哈希密码
- **sessions**: `session_id, username, name, created_at, last_active, image_url, flower_info` — 花卉会话，含图片 URL 和结构化数据缓存
- **tokens**: `token, username, created_at, expires_at` — API 登录 token，默认 7 天过期

所有数据库函数通过 `threading.Lock` 装饰器保护，确保多线程并发安全。

核心函数：`register_user`, `login_user`, `get_or_create_flower_session`, `list_sessions`（JSON 容错）, `update_session_flower_info`, `create_token`, `verify_token`（含过期检查）, `get_latest_session`, `get_session_data`（线程安全查询）

### `stage1_workflow.py` — Stage 1 工作流

```
[search] → [extract] → [report] → END
```

- **search**: 手动调用 `TavilySearch` 搜索花卉信息（含异常保护，搜索失败时回退到 LLM 知识）
- **extract**: 使用 `model.with_structured_output(FlowerInfo, method="function_calling")` 强制 LLM 输出结构化数据（含异常保护，LLM 失败时返回基础 report）
- **report**: 格式化 `FlowerInfo` 为 Markdown 报告，字段缺失时安全回退

### `stage2_agent.py` — Stage 2 Agent

`create_agent` + TavilySearch 工具 + `SummarizationMiddleware`（51200 tokens 触发摘要，保留最后 20 条消息）。

### `obs_client.py` — OBS 图片上传

`upload_image(file_bytes, filename, username)` → 上传到华为云 OBS，返回公开访问 URL。object_key 格式：`{username}/{uuid}.{ext}`。

### `server.py` — HTTP API 入口

FastAPI 异步服务，7 个端点 + SPA 前端托管。

活跃会话解析策略：内存缓存 → `ChatRequest.session_id` → 数据库最近会话，同时校验会话归属（`{username}:` 前缀）。服务器重启后不会丢失会话状态。外部服务（DeepSeek/Tavily/OBS）异常均有保护，不会因依赖故障导致 500。

运行：`uv run hua-server`

---

## API 文档

### 认证

```http
POST /api/auth/register
Body:   {"username": "str", "password": "str"}
Return: {"ok": true, "message": "注册成功"}

POST /api/auth/login
Body:   {"username": "str", "password": "str"}
Return: {"ok": true, "token": "hex...", "username": "str"}

POST /api/auth/logout
Header: Authorization: Bearer <token>
Return: {"ok": true, "message": "已登出"}
```

### 花卉研究

```http
GET /api/sessions
Header: Authorization: Bearer <token>
Return: {"ok": true, "sessions": [{"session_id": "alice:牡丹", "name": "牡丹", "image_url": "https://...", "flower_info": {...}}]}

POST /api/research
Header: Authorization: Bearer <token>
Body:   {"flower_name": "牡丹"}
Return (新): {"ok": true, "stage": 1, "session_id": "alice:牡丹", "flower_name": "牡丹", "flower_info": {...}, "image_url": null}
Return (已有): {"ok": true, "stage": 2, "session_id": "alice:牡丹", "flower_name": "牡丹", "flower_info": {...}, "image_url": "https://..."}

POST /api/chat
Header: Authorization: Bearer <token>
Body:   {"message": "花期多长？"}
Return: {"ok": true, "stage": 2, "reply": "牡丹的花期..."}

POST /api/upload
Header: Authorization: Bearer <token>
Content-Type: multipart/form-data
Body: file=<image> [flower_name="牡丹"]
Return: {"ok": true, "stage": 1, "session_id": "alice:牡丹", "flower_name": "牡丹", "flower_info": {...}, "image_url": "https://..."}
```

### Swagger

启动后访问 `http://localhost:5000/docs` 查看交互式 API 文档。

---

## 运行方式

```bash
# 安装依赖
uv sync

# 配置 .env
echo 'TAVILY_API_KEY=xxx' >> .env
echo 'DEEPSEEK_API_KEY=xxx' >> .env
echo 'AK=xxx' >> .env
echo 'SK=xxx' >> .env
echo 'ENDPOINT=obs.cn-north-4.myhuaweicloud.com' >> .env
echo 'BUCKET_NAME=user-flower-img' >> .env

# HTTP 服务模式
uv run hua-server

# 浏览器打开
# http://localhost:5000
```

---

## 关键设计决策

1. **两阶段分离**: Stage 1 硬编码保证结构化输出，Stage 2 自由 agent 支持灵活追问。避免单一 agent 跳过结构化输出。

2. **统一响应格式**: `/api/research` 和 `/api/upload` 返回一致的 `ResearchResponse`，新会话和已有会话格式相同，前端无需区分处理。

3. **图片识别占位**: `/api/upload` 内置 `_identify_flower_from_url()` 占位函数。当前可通过 `flower_name` 表单字段手动指定花名完成完整流程，外部 API 实现后直接替换即可。

4. **结构化数据缓存**: `sessions` 表新增 `flower_info` 和 `image_url` 字段，Stage 1 完成后立即缓存，后续访问直接返回无需重新搜索。

5. **`asyncio.to_thread()`**: FastAPI 异步路由将同步 LangGraph 调用抛到线程池，避免阻塞事件循环。

6. **`BeforeValidator` 截断**: Pydantic 模型用 BeforeValidator 自动截断超长字段，防止 LLM 输出超出限制导致校验失败。

7. **会话名 = 花卉名**: `session_id = username:flower_name`，同一花卉的研究自动归入同一会话。

8. **SQLite 双库**: `agent_memory.db`（LangGraph checkpointer）+ `meta.db`（用户/会话/token），职责分离。

9. **`threading.Lock` 保护 SQLite**: 数据库函数内部持锁，确保多线程并发写入安全。

10. **令牌过期**: token 默认 7 天过期，`verify_token` 惰性检查并拒绝过期令牌。

11. **会话持久化**: 活跃会话不在内存中时，自动从数据库查询用户最近会话，服务器重启不丢失状态。

---

## 待扩展

- [ ] 实现外部花卉识别 API（`_identify_flower_from_url`）
- [ ] 生产级数据库（PostgreSQL）
- [ ] JWT 认证替代简单 token
- [ ] WebSocket 流式输出
- [ ] 多花卉对比研究
- [ ] Docker 部署
