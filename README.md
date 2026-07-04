# 🌸 花卉研究 Agent

[![Test](https://github.com/Zeke-777/hua-agent/actions/workflows/test.yml/badge.svg)](https://github.com/Zeke-777/hua-agent/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/badge/coverage-85%25-brightgreen)](https://github.com/Zeke-777/hua-agent)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)

两阶段 LangGraph + FastAPI 多用户花卉研究系统。输入花名或上传图片 → AI 搜索资料 → 提取 9 字段结构化报告 → 多轮追问。纵深防御安全体系、85% 测试覆盖率、CI 质量门禁。

```
用户输入 → Stage 1: 搜索(Tavily) → 提取(LLM) → 结构化报告(9字段)
         → Stage 2: ReAct Agent 带搜索工具 → 多轮追问
```

## 架构

```
┌─────────────────────────────────────────────────────┐
│                    FastAPI App                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ /auth/*  │  │/research │  │ /chat  /sessions  │  │
│  │ 注册/登录│  │ /upload  │  │                  │  │
│  │ 登出     │  │          │  │                  │  │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│       │              │                 │             │
│  ┌────┴──────────────┴─────────────────┴──────────┐ │
│  │              app.state（依赖注入）               │ │
│  │  model · checkpointer · stage1 · stage2         │ │
│  │  meta_conn · active_sessions · executor         │ │
│  └────────────────────┬───────────────────────────┘ │
│                       │                              │
│  ┌────────────────────┴───────────────────────────┐ │
│  │  Stage 1（LangGraph 编译图）                     │ │
│  │  search ──→ extract ──→ report ──→ END          │ │
│  │     ↓           ↓                                │ │
│  │  Tavily    function_calling                      │ │
│  │            → Pydantic FlowerInfo                 │ │
│  └──────────────┬──────────────────────────────────┘ │
│                 │ SqliteSaver（共享会话记忆）         │
│  ┌──────────────┴──────────────────────────────────┐ │
│  │  Stage 2（ReAct Agent + 搜索工具）               │ │
│  │  LLM ←→ Tavily Search ←→ SummarizationMiddleware │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**核心设计决策：**

- **应用工厂模式** — `create_app(settings)` 可注入配置，便于测试和部署
- **`app.state` 依赖注入** — 零模块级全局变量，路由通过 `Request.app.state` 获取资源
- **两阶段共享记忆** — Stage1 产出结构化数据，Stage2 继承同一 `thread_id` 进行多轮追问
- **全链路降级** — 每个外部调用（Tavily、LLM 结构化输出）均有 try/except 回退，上游故障不中断流程

## 快速开始

```bash
# 1. 克隆并配置
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 2. 安装依赖
uv sync

# 3. 启动
uv run hua-server
# → http://localhost:5000
# → Swagger 文档: http://localhost:5000/docs
```

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `TAVILY_API_KEY` | 是 | Tavily 搜索 API 密钥 |
| `AK` | 否¹ | 华为云 OBS 访问密钥 |
| `SK` | 否¹ | 华为云 OBS 秘密密钥 |
| `ENDPOINT` | 否¹ | OBS 端点地址 |
| `BUCKET_NAME` | 否¹ | OBS 桶名称 |
| `HOST` | 否 | 服务监听地址（默认 `0.0.0.0`） |
| `PORT` | 否 | 服务端口（默认 `5000`） |
| `CORS_ORIGINS` | 否 | 允许的跨域来源 JSON 数组（默认 `["http://localhost:5173"]`） |

¹ 仅图片上传功能需要。

## 项目结构

```
hua_agent/
├── main.py              # uvicorn 入口
├── app.py               # create_app() 工厂 + lifespan
├── config.py            # pydantic-settings（9 个环境变量）
├── schemas.py           # 全部 Pydantic 模型
├── auth.py              # get_current_user() 鉴权依赖
├── db.py                # SQLite 数据访问层（用户/会话/Token）
├── models.py            # 向后兼容的再导出
├── obs_client.py        # OBS 客户端单例（启动时初始化）
├── spa.py               # SPA 静态文件回退
├── middleware.py         # 请求日志 + CSP 头部
├── image_utils.py       # 上传校验 + 魔术字节检测
├── routes/
│   ├── auth.py          # POST /api/auth/{register,login,logout}
│   ├── chat.py          # POST /api/chat · GET /api/sessions
│   └── research.py      # POST /api/research · POST /api/upload
├── services/
│   ├── research.py      # run_stage1(), run_stage2()
│   └── flower_id.py     # identify_flower_from_url()
├── workflows/
│   ├── stage1.py        # search → extract → report 编译图
│   └── stage2.py        # ReAct Agent + Tavily 搜索工具
tests/
├── test_db.py           # 36 条 · 92% 覆盖
├── test_api.py          # 21 条（3 组参数化）
├── test_auth.py         # 10 条（bcrypt + 登录）
├── test_security.py     # 11 条（路径穿越 + 会话隔离）
├── test_workflows.py    # 5 条（图拓扑 + 降级路径）
├── test_models.py       # 6 条（截断边界值）
├── test_main.py         # 2 条（app + config）
└── test_imports.py      # 2 条（全模块可导入）
```

## API

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `POST` | `/api/auth/register` | — | 注册新用户 |
| `POST` | `/api/auth/login` | — | 登录，返回 64 字符 hex token |
| `POST` | `/api/auth/logout` | Bearer | 登出，销毁 token |
| `GET` | `/api/sessions` | Bearer | 获取用户的会话列表 |
| `POST` | `/api/research` | Bearer | 开始/加载花卉研究 |
| `POST` | `/api/chat` | Bearer | 多轮追问 |
| `POST` | `/api/upload` | Bearer | 上传图片识别花卉 |

### 典型流程

```
POST /api/auth/register → POST /api/auth/login → 获取 token

文字输入：
  POST /api/research  {"flower_name": "牡丹"}  → stage: 1, flower_info（9 字段）
  POST /api/chat      {"message": "花期是几月？"} → stage: 2, reply

图片输入：
  POST /api/upload    file=<图片> flower_name="牡丹" → stage: 1, flower_info + image_url
  POST /api/chat      {"message": "有什么文化寓意？"}  → stage: 2, reply
```

**说明：**
- Token 默认 7 天过期，启动时自动清理过期 token
- `/api/chat` 可选传 `session_id`；不传则使用内存中的活跃会话或最近一次 DB 会话
- `/api/research` 已研究过的花卉直接返回缓存，避免重复搜索
- 图片上传支持 jpg / png / gif / webp，最大 10MB；校验扩展名、MIME 类型、魔术字节

## 安全

| 层级 | 措施 |
|------|------|
| **认证** | bcrypt 密码哈希、`secrets.token_hex(32)` Bearer token、7 天过期、NULL expiry 拒绝 |
| **授权** | SQL 级会话所有权校验（`WHERE username=? AND session_id=?`），杜绝字符串前缀绕过 |
| **传输** | CORS 白名单从环境变量注入、`Content-Security-Policy` 响应头 |
| **输入** | SQLite 表名白名单防注入、路径穿越三重防护（`../`、`%5C`、盘符注入） |

## 测试

```bash
uv run pytest tests/ --cov=hua_agent --cov-report=term
```

**93 条测试 · 85% 覆盖率 · ≤9 秒**

- **数据库层** — `:memory:` SQLite 隔离，零外部依赖
- **API 层** — `TestClient` + mock 工作流（无需 LLM/OBS）
- **工作流** — mock LLM + Tavily，验证图拓扑和降级路径
- **安全** — 路径穿越 6 种向量 + 会话隔离 3 类场景

CI 通过 GitHub Actions 在每次 push/PR 自动运行 `uv sync → pytest --cov --cov-fail-under=70`，覆盖率不达标阻断合并。

## 技术栈

**Python ≥3.10** · LangChain + LangGraph · FastAPI · DeepSeek · Tavily · SQLite · 华为云 OBS · bcrypt · pydantic-settings · cachetools · pytest · GitHub Actions · uv
