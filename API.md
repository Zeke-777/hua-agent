# 花卉研究 Agent — API 接口文档

Base URL: `http://localhost:5000`

---

## 1. GET /api/sessions

获取当前用户的全部花卉研究会话列表。

| 项        | 内容                                    |
| -------- | ------------------------------------- |
| **请求头**  | `Authorization: Bearer <token>`       |
| **请求体**  | 无                                     |
| **成功响应** | `200 {"ok": true, "sessions": [...]}` |
| **失败响应** | `401 {"detail": "token 无效或已过期"}`      |

```
// sessions 数组元素
{
  "session_id": "alice:牡丹",     // 会话 ID，格式 username:flower_name
  "name": "牡丹",                 // 花卉名称
  "created_at": "2026-05-22T10:30:00+00:00",
  "last_active": "2026-05-22T11:00:00+00:00",
  "image_url": "https://...png",  // 花卉图片 URL（若有上传图片）
  "flower_info": {                // 结构化花卉信息（若已研究过）
    "名称": "牡丹",
    "形态结构": "落叶灌木...",
    ...
  }
}
```

排序规则：`last_active DESC`（最近活跃的在前）。

---

## 2. POST /api/research

启动新的花卉研究，或加载已有的花卉会话。

| 项       | 内容                              |
| ------- | ------------------------------- |
| **请求头** | `Authorization: Bearer <token>` |
| **请求体** | `{"flower_name": "牡丹"}`         |

### 场景 A：首次研究该花卉（新建会话）

```
// 响应 200 — Stage 1 结构化报告
{
  "ok": true,
  "stage": 1,
  "session_id": "alice:牡丹",
  "flower_name": "牡丹",
  "flower_info": {
    "名称": "牡丹",
    "形态结构": "落叶灌木，高可达2米...",
    "植物分类": "芍药科芍药属...",
    "生长习性": "喜阳光充足...",
    "花期规律": "花期4-5月...",
    "气味与特征": "花朵大而芳香...",
    "繁殖方式": "分株、扦插...",
    "使用价值": "观赏花卉，根可药用...",
    "文化寓意": "象征富贵吉祥...",
    "参考来源": "1. https://... — 百科\n2. https://... — 百度百科"
  },
  "image_url": null
}
```

后端执行：

1. 创建会话记录 `session_id = username:flower_name`
2. 更新 `active_sessions[username] = session_id`
3. 运行 Stage 1 工作流：搜索 → 提取 → 报告
4. 缓存 `flower_info` 到 sessions 表

### 场景 B：该花卉已有会话

```
// 响应 200 — 返回缓存的结构化数据
{
  "ok": true,
  "stage": 2,
  "session_id": "alice:牡丹",
  "flower_name": "牡丹",
  "flower_info": {
    "名称": "牡丹",
    "形态结构": "落叶灌木，高可达2米...",
    ...
  },
  "image_url": "https://...png"
}
```

后端执行：

1. 更新 `last_active` 时间
2. 更新 `active_sessions[username] = session_id`
3. 从数据库读取缓存的 `flower_info` 直接返回

**注意**：两种场景返回格式完全一致，前端无需区分处理。

### 错误

| 状态码 | detail             |
| --- | ------------------ |
| 400 | `flower_name 不能为空` |
| 401 | `token 无效或已过期`     |

---

## 3. POST /api/chat

在当前活跃会话中发送追问。

| 项       | 内容                                                   |
| ------- | ---------------------------------------------------- |
| **请求头** | `Authorization: Bearer <token>`                      |
| **请求体** | `{"message": "牡丹的花期是几月？", "session_id": "alice:牡丹"}` |

> `session_id` 为可选字段。不传则使用内存中的活跃会话；若内存中也没有，则从数据库查询用户最近活跃的会话。

```
// 成功响应 200 — Stage 2 回复
{
  "ok": true,
  "stage": 2,
  "reply": "牡丹的花期通常在4-5月，具体因品种和气候而异..."
}
```

后端执行：

1. 优先使用请求体中的 `session_id`，其次内存中的 `active_sessions[username]`，最后从数据库查询最近活跃会话
2. 校验会话归属（`session_id` 必须以 `{username}:` 开头），否则 403
3. 若三者都无结果，返回 400
4. 运行 Stage 2 Agent（基于该 thread 的 LangGraph 检查点恢复对话历史）
5. 更新 `last_active` 时间

### 错误

| 状态码 | detail                |
| --- | --------------------- |
| 400 | `message 不能为空`        |
| 400 | `没有活跃会话，请先输入花卉名称开始研究` |
| 403 | `无权访问该会话`             |
| 401 | `token 无效或已过期`        |

---

## 4. POST /api/upload

上传图片到华为云 OBS，自动识别花卉并返回结构化研究报告。

| 项                | 内容                                             |
| ---------------- | ---------------------------------------------- |
| **请求头**          | `Authorization: Bearer <token>`                |
| **Content-Type** | `multipart/form-data`                          |
| **表单字段**         | `file`: 图片文件（必填）                               |
|                  | `flower_name`: 花卉名称（选填。不填则调用外部识别 API——**待实现**） |
| **支持格式**         | jpg / jpeg / png / gif / webp                  |
| **大小限制**         | 最大 10MB                                        |

```
// 成功响应 200 — 返回格式同 POST /api/research
{
  "ok": true,
  "stage": 1,
  "session_id": "alice:牡丹",
  "flower_name": "牡丹",
  "flower_info": {
    "名称": "牡丹",
    "形态结构": "落叶灌木，高可达2米...",
    ...
  },
  "image_url": "https://user-flower-img.obs.cn-north-4.myhuaweicloud.com/alice/a1b2c3d4.png"
}
```

后端执行：

1. 校验文件名、扩展名、文件大小
2. 上传到 OBS，生成 object_key = `{username}/{uuid}.{ext}`
3. 识别花卉名称：优先使用表单传入的 `flower_name`，否则调用外部识别 API（`_identify_flower_from_url` — **待实现**）
4. 创建/加载花卉会话（关联 image_url）
5. 若是新会话：运行 Stage 1 研究，缓存 flower_info 到 sessions 表
6. 返回 `ResearchResponse`

### 错误

| 状态码 | detail                                      |
| --- | ------------------------------------------- |
| 400 | `文件名为空`                                     |
| 400 | `不支持的文件类型: .xxx`                            |
| 400 | `文件大小超过 10MB 限制`                            |
| 401 | `token 无效或已过期`                              |
| 501 | `外部花卉识别接口暂不可用`（未传 flower_name 且外部 API 不可用时） |

---

## 5. POST /api/auth/register

注册新用户。

| 项       | 内容                                            |
| ------- | --------------------------------------------- |
| **请求体** | `{"username": "alice", "password": "123456"}` |

```
// 成功响应 200
{"ok": true, "message": "注册成功"}
```

### 错误

| 状态码 | detail   |
| --- | -------- |
| 409 | `用户名已存在` |

---

## 6. POST /api/auth/login

用户登录，获取 Bearer token（默认 7 天有效）。

| 项       | 内容                                            |
| ------- | --------------------------------------------- |
| **请求体** | `{"username": "alice", "password": "123456"}` |

```
// 成功响应 200
{
  "ok": true,
  "token": "a1b2c3d4e5f6...",
  "username": "alice"
}
```

### 错误

| 状态码 | detail  |
| --- | ------- |
| 401 | `用户不存在` |
| 401 | `密码错误`  |

---

## 7. POST /api/auth/logout

登出，使当前 token 失效。

| 项       | 内容                              |
| ------- | ------------------------------- |
| **请求头** | `Authorization: Bearer <token>` |

```
// 响应 200
{"ok": true, "message": "已登出"}
```

---

## 典型调用流程

```
1. POST /api/auth/register    → 注册
2. POST /api/auth/login       → 获取 token
   （后续所有请求带 Authorization: Bearer <token>）
3. GET  /api/sessions         → 获取已有会话列表（初始为空）

--- 方式一：文字输入 ---
4. POST /api/research         → 输入"牡丹"，启动研究
   ← stage: 1, flower_info 结构化数据
5. POST /api/chat             → "花期是几月？"
   ← stage: 2, 对话回复

--- 方式二：图片上传 ---
4. POST /api/upload           → 上传花卉图片 + flower_name="牡丹"
   ← stage: 1, flower_info + image_url
5. POST /api/chat             → "有什么文化寓意？"
   ← stage: 2, 对话回复

6. POST /api/auth/logout      → 登出
```
