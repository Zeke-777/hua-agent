# 花卉研究 Agent

两阶段 LangGraph + FastAPI 智能花卉研究系统。输入花卉名称或上传图片，AI 自动搜索资料并生成结构化研究报告，支持多轮追问对话。

## 架构

```
用户输入花名 / 上传图片
  → Stage 1: 搜索(Tavily) → 提取(LLM) → 结构化报告(9字段)
  → Stage 2: Agent 多轮追问对话(带搜索工具)

前端: 单文件 SPA (HTML + 内嵌 CSS/JS)
后端: FastAPI + LangGraph + SQLite
图片存储: 华为云 OBS
```

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填写 API 密钥

# 2. 安装依赖
uv sync

# 3. 启动服务
uv run hua-server

# 4. 浏览器打开
# http://localhost:5000
```

## 项目结构

```
hua_agent/              # Python 后端
  models.py             # 数据模型 (FlowerInfo, ResearchResponse, ChatRequest)
  db.py                 # 数据库层 (用户/会话/token, 线程安全)
  stage1_workflow.py    # Stage 1 搜索→提取→报告 LangGraph 工作流
  stage2_agent.py       # Stage 2 追问 Agent
  obs_client.py         # 华为云 OBS 图片上传
  server.py             # FastAPI HTTP 服务

static/dist/
  index.html            # 前端页面 (单文件 SPA)

usersdata/              # SQLite 数据 (运行时自动生成)
  agent_memory.db       # LangGraph 记忆
  meta.db               # 用户/会话/token
```

## API 接口

| 方法     | 路径                   | 认证     | 说明                  |
| ------ | -------------------- | ------ | ------------------- |
| `POST` | `/api/auth/register` | 无      | 用户注册                |
| `POST` | `/api/auth/login`    | 无      | 用户登录，返回 token       |
| `POST` | `/api/auth/logout`   | Bearer | 用户登出，token 失效       |
| `GET`  | `/api/sessions`      | Bearer | 获取当前用户会话列表          |
| `POST` | `/api/research`      | Bearer | 开始/加载花卉研究 (Stage 1) |
| `POST` | `/api/chat`          | Bearer | 追问对话 (Stage 2)      |
| `POST` | `/api/upload`        | Bearer | 上传图片识别花卉            |

- token 默认 7 天过期
- chat 接口支持可选 `session_id` 字段指定会话
- 服务器重启后活跃会话自动从数据库恢复

## 环境变量

| 变量                 | 说明                                          |
| ------------------ | ------------------------------------------- |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥                             |
| `TAVILY_API_KEY`   | Tavily 搜索 API 密钥                            |
| `AK`               | 华为云 OBS Access Key                          |
| `SK`               | 华为云 OBS Secret Key                          |
| `ENDPOINT`         | OBS 端点 (如 obs.cn-north-4.myhuaweicloud.com) |
| `BUCKET_NAME`      | OBS 桶名称                                     |

## 文档

- [API 接口文档](API.md)
- [项目总结](PROJECT_SUMMARY.md)
- Swagger: 启动后访问 http://localhost:5000/docs
