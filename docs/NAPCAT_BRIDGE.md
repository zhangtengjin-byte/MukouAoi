# Mukou Aoi QQ 群聊桥接（NapCat Bridge）

## 1. 概述

NapCat Bridge 是葵接入 QQ 群聊的桥梁。它通过 **NapCat**（一个基于 OneBot 协议的 QQ 机器人框架）监听群消息，经 **Hermes Webhook** 注入网关，最终由 Agent 处理并回复。

```
NapCat WebSocket/HTTP → Hermes Webhook → Hermes Gateway → pre_llm_call → Agent → LLM → 回复 → NapCat HTTP API 发回群
```

## 2. 系统架构

NapCat Bridge 由**两条完全独立的通路**组成：一条负责**消息接收（Inbound）**，一条负责**消息发送（Outbound）**。两条通路使用不同的协议、不同的端口、不同的组件，互不依赖。

- **Inbound（接收）**：QQ 群消息 → NapCat WebSocket/Webhook 推送 → Hermes Webhook Plugin → Gateway → Agent → LLM
- **Outbound（发送）**：Agent 决定回复 → Gateway → NapCat Platform Adapter → NapCat HTTP API → QQ 群

---

### 2.1 入方向通路（Inbound — 消息接收）

NapCat 通过 WebSocket 反向连接（ws_reverse）或 HTTP WebHook 将 QQ 群消息推送到 Hermes。Hermes 的 Webhook Plugin 接收后注入 Gateway 管道。

```
┌─────────────────────────────────────────────────────────────────────┐
│  Inbound Path: QQ → NapCat → Webhook → Hermes Gateway → Agent      │
└─────────────────────────────────────────────────────────────────────┘

   QQ 群消息
       │
       ▼
┌──────────────────┐
│   NapCat QQ       │  监听群聊事件，产生 message 事件
│   (QQ 客户端)     │
└─────────┬────────┘
          │
          ├── (方式 A) WebSocket 反向连接 ──→ ws://127.0.0.1:8766/
          │    NapCat onebot11.json 中配置 ws_reverse[]
          │
          └── (方式 B) HTTP WebHook ──→ http://127.0.0.1:8644/webhook/napcat
               NapCat onebot11.json 中配置 http_webhook[]
          │
          ▼
┌──────────────────────┐
│  Bridge 决策层        │  消息评分（value_scorer）
│  (bridge_debug)       │  过滤噪音、管理会话
└──────────┬───────────┘
           │  打分通过的消息，打上 [群=XXX QQ=YYY] 标记
           ▼
┌──────────────────────┐
│  Hermes Webhook       │  监听 :8644
│  Plugin               │  route: /webhook/napcat
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Hermes Gateway       │  pre_gateway_dispatch
│                       │  pre_llm_call
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Agent Core           │  LLM 调用 → 生成回复
└──────────────────────┘
```

---

### 2.2 出方向通路（Outbound — 消息发送）

Agent 生成回复后，Gateway 将回复交给 NapCat Platform Adapter。适配器通过 NapCat 的 HTTP API（端口 3000）直接调用 `send_group_msg` 或 `send_private_msg`，将消息发回 QQ 群。

```
┌─────────────────────────────────────────────────────────────────────┐
│  Outbound Path: Agent → Gateway → NapCat Adapter → HTTP API → QQ   │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  Agent Core           │  决定回复内容
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Hermes Gateway       │  平台分发，选择 napcat 平台
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────┐
│  NapCat Platform Adapter  │  plugins/napcat/adapter.py
│  (NapcatAdapter)          │  消息清洗、emoji 剥离、长度截断
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────────┐
│  HTTP POST                    │
│  http://127.0.0.1:3000/       │  Authorization: Bearer <token>
│  ├─ /send_group_msg           │  → body: { group_id, message }
│  └─ /send_private_msg         │  → body: { user_id, message }
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────┐
│   NapCat QQ       │   NapCat 收到 API 请求后发送到 QQ
│   (QQ 客户端)     │
└─────────┬────────┘
          │
          ▼
      QQ 群聊 / 私聊
```

---

### 2.3 全架构总览

两条通路在同一架构中的完整关系：

```
┌─────────────────────────────────────────────────────────────────────────┐
│  全系统架构 ── 两条独立通路                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────┐                           ┌──────────────────────┐        │
│  │ QQ 群聊   │    ──消息事件──→          │   NapCat QQ 客户端    │        │
│  │ (用户)    │    ←──回复消息──          │   (NapCat 服务)       │        │
│  └──────────┘                           └────────┬───────┬─────┘        │
│                                                  │       │              │
│                  INBOUND ─────────────────────────┘       │              │
│                  (接收)     WebSocket :8766 / HTTP :8765   │              │
│                            ws_reverse / http_webhook       │              │
│                                  │                        │              │
│                                  ▼                        │              │
│                  ┌──────────────────────┐                 │              │
│                  │  Hermes Webhook       │                 │              │
│                  │  Plugin (:8644)       │                 │              │
│                  └──────────┬───────────┘                 │              │
│                             │                             │              │
│                             ▼                             │              │
│                  ┌──────────────────────┐                 │              │
│                  │  Hermes Gateway      │                 │              │
│                  │  (pre_gateway_dispatch│                 │              │
│                  │   → pre_llm_call)    │                 │              │
│                  └──────────┬───────────┘                 │              │
│                             │                             │              │
│                             ▼                             │              │
│                  ┌──────────────────────┐                 │              │
│                  │  Agent Core          │                 │              │
│                  │  (LLM 调用)          │                 │              │
│                  └──────────┬───────────┘                 │              │
│                             │                             │              │
│                             │  OUTBOUND ─────────────────┘              │
│                             │  (发送)                                    │
│                             ▼                                           │
│                  ┌──────────────────────┐                               │
│                  │  NapCat Platform     │                               │
│                  │  Adapter             │                               │
│                  │  (消息清洗/格式转换)   │                               │
│                  └──────────┬───────────┘                               │
│                             │  HTTP POST :3000                          │
│                             ▼                                           │
│                  ┌──────────────────────┐                               │
│                  │  NapCat HTTP API     │  send_group_msg               │
│                  │  (:3000)             │  send_private_msg             │
│                  └──────────┬───────────┘                               │
│                             │                                           │
│                             ▼                                           │
│                  ┌──────────────────────┐                               │
│                  │  QQ 群聊 / 私聊      │                               │
│                  └──────────────────────┘                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 2.4 关键端口与协议

| 通路 | 服务 | 端口 | 协议 | 方向 | 说明 |
|------|------|------|------|------|------|
| **Inbound** | NapCat WebSocket Server | `8766` | WebSocket (ws_reverse) | NapCat → Hermes | NapCat 推送 QQ 事件到 Hermes Bridge |
| **Inbound** | NapCat HTTP Webhook | `8765` | HTTP POST | NapCat → Hermes | 备选方式发送事件到 Hermes Webhook |
| **Inbound** | Hermes Webhook Plugin | `8644` | HTTP POST (接收) | NapCat → Hermes | Hermes 接收外部消息的入口 |
| **Outbound** | NapCat HTTP API | `3000` | HTTP POST (调用) | Hermes → NapCat | Hermes 通过此接口发消息回 QQ |
| 内部 | Hermes Gateway | `—` | 内部管道 | Agent 内部 | 消息分发、插件调度 |

> **注意**：Inbound 和 Outbound 使用不同的 NapCat 端口。Inbound 经由 `8766`(WS) 或 `8765`(HTTP) 推送事件到 Hermes；Outbound 经由 `3000`(HTTP API) 从 Hermes 调用 NapCat 发消息。两条通路在 NapCat 侧通过 `onebot11.json` 配置中的不同配置块分别启用。

### 2.5 NapCat 双端口配置（onebot11.json）

NapCat 的 `config/onebot11.json` 中同时配置了**接收端的反向连接**和**发送端的 HTTP API**，形成完整的双向通道：

```json
{
  "ws_reverse": [
    {
      "name": "hermes",
      "url": "ws://127.0.0.1:8766/",
      "access_token": ""
    }
  ],
  "http_webhook": [
    {
      "name": "hermes-gateway",
      "url": "http://127.0.0.1:8644/webhook/napcat",
      "secret": "your-napcat-secret"
    }
  ],
  "http": [
    {
      "host": "0.0.0.0",
      "port": 3000,
      "enable": true
    }
  ]
}
```

| 配置块 | 所属通路 | 作用 |
|--------|----------|------|
| `ws_reverse[]` | **Inbound** | NapCat 连接到 Hermes WebSocket Server（:8766）推送事件 |
| `http_webhook[]` | **Inbound**（备选） | NapCat 通过 HTTP POST 推送到 Hermes Webhook（:8644） |
| `http[]` | **Outbound** | NapCat 开启 HTTP API 服务（:3000），供 Hermes 调用发消息 |

## 3. 配置方法

### 3.1 config.yaml 配置

```yaml
# ~/.hermes/config.yaml

# 1. NapCat 平台配置（用于发送消息）
platforms:
  napcat:
    enabled: true
    extra:
      api_url: http://127.0.0.1:3000    # NapCat HTTP API 地址
      api_token: your-napcat-secret        # NapCat API 认证 token

# 2. Webhook 配置（用于接收消息）
  webhook:
    enabled: true
    host: 0.0.0.0
    port: 8644
    extra:
      routes:
        napcat:
          secret: your-napcat-secret      # 与 NapCat WebHook 配置一致
          prompt: "{message}\n[群={group_id} QQ={user_id}]"
          deliver: napcat                 # 消息来源标记
          deliver_only: false

# 3. 插件启用
plugins:
  enabled:
    - napcat-platform
    - emotion-governor
    - mode-switch
    - memory-rag
```

### 3.2 NapCat 配置

NapCat 需要配置 WebSocket 反向连接（ws_reverse）或 HTTP WebHook，将 QQ 消息推送到 Hermes。

**NapCat WebSocket 反向连接配置**：

在 NapCat 的 `config/onebot11.json` 或 NapCat WebUI 中配置：

```json
{
  "ws_reverse": [
    {
      "name": "hermes",
      "url": "ws://127.0.0.1:8766/",
      "access_token": ""
    }
  ],
  "http": [
    {
      "host": "0.0.0.0",
      "port": 3000,
      "enable": true
    }
  ],
  "http_webhook": [
    {
      "name": "hermes-gateway",
      "url": "http://127.0.0.1:8644/webhook/napcat",
      "secret": "your-napcat-secret"
    }
  ]
}
```

或者配置 `config.ini`（若 NapCat 使用 ini 配置）：

```ini
[websocket_reverse]
enable=true
url=ws://127.0.0.1:8766/

[http]
enable=true
host=0.0.0.0
port=3000

[http_webhook]
enable=true
url=http://127.0.0.1:8644/webhook/napcat
secret=your-napcat-secret
```

### 3.3 关键配置说明

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| `napcat.extra.api_url` | NapCat HTTP API 地址 | `http://192.168.8.2:3000` |
| `napcat.extra.api_token` | NapCat 的 access_token | `eP7jxnMkOuvHVH2t` |
| `webhook.port` | Hermes Webhook 监听端口 | `8644` |
| `webhook.routes.napcat.secret` | 认证密钥 | 与 NapCat 中的 secret 一致 |
| `webhook.routes.napcat.prompt` | 消息注入格式 | `{message}\n[群={group_id} QQ={user_id}]` |

## 4. 消息评分与过滤（bridge 层）

### 4.1 消息决策流程

NapCat 的 WebSocket 收到每条消息后，`bridge_decision_logic` 执行以下判断：

```
WS 收到消息
  ├─ 不是 message 事件？→ x-skip
  ├─ 自己发的消息（self_message）？→ x-skip
  ├─ 消息评分（value_scorer）：
  │   ├─ 分数高 → forward=True，转发到 Hermes
  │   └─ 分数低 → x-skip
  └─ 转发 → process_message() → 打标记 → Webhook → Gateway
```

### 4.2 消息评分（value_scorer）

消息进入 Hermes 前，bridge 层会对每条消息进行**价值评分**，判断是否值得回应：

```python
# 简化的评分逻辑
score = 0
# @提及葵 → 加分
if "@葵" in msg or at_bot:
    score += 40
# 针对性的问题 → 加分
if "葵" in msg and "?" in msg:
    score += 30
# 关键词触发 → 加分
if any(kw in msg for kw in ["葵", "向日葵", "aoi"]):
    score += 20
# 新手/简短消息 → 降分
if len(msg) < 5:
    score -= 20
# 无意义消息 → 降分
if msg in seen_recently:
    score -= 30

# 决策
if score >= 50:
    forward = True, verdict = "high_value"
elif score >= 30:
    forward = True, verdict = "medium_value"
else:
    forward = False, verdict = "low_value"
```

### 4.3 会话管理（session_manager）

每条转发的消息都会绑定到唯一会话 ID：

```python
# 会话 ID 格式
session_id = f"gc_{group_id}_{user_id}"

# 群 + 用户 → 独立会话
# 同一群的不同用户 → 不同会话
# 同一用户在不同群 → 不同会话
```

会话管理器维护每个会话的状态（最近消息历史、情绪上下文等），确保持续对话的上下文连贯性。

### 4.4 拒绝词列表

以下类型的消息会被直接拒绝（不转发到 Agent）：

| 类别 | 示例 |
|------|------|
| 系统心跳 | `heartbeat_ok` |
| 技术调试 | `emotion.json`, `decay`, `gateway` |
| 纯表情/无意义 | 纯 emoji, 纯标点 |
| 重复消息 | 短时间内完全相同的消息 |
| 内部噪音 | Hermes 内部消息（如 `Rate limited`） |

## 5. NapCat Platform Adapter（发送端）

### 5.1 适配器模式

Hermes 通过 `NapcatAdapter`（`plugins/napcat/adapter.py`）发送回复，支持 **群聊** 和 **私聊** 两种模式：

```python
class NapcatAdapter(BasePlatformAdapter):
    async def send(self, chat_id, content, reply_to=None, metadata=None):
        # chat_id 格式：
        #   - 纯数字 = group_id（发群消息）
        #   - "u:" 前缀 + 数字 = user_id（发私聊消息）
        
        # 1. 噪音检测（过滤 Hermes 内部消息）
        if _is_noise(content):
            return SendResult(success=False, error="filtered_noise")
        
        # 2. 剥离内部独白和 emoji
        clean = _strip_internal_monologue(strip_emoji(content))
        
        # 3. 发送文字（切片到 2000 字以内）
        # 4. 如果有表情包 → 单独发图
```

### 5.2 消息后处理

发送前执行以下清洗：

1. **去除 Hermes 内部独白**：`Self.improvement review:*` 等行
2. **去除 Unicde emoji**（QQ 不支持所有 emoji，仅保留特定 Unicode 块）
3. **噪音过滤**：屏蔽 `Rate limited`、`Compression model` 等内部消息
4. **长度截断**：QQ 消息上限 2000 字

### 5.3 表情包附加

如果启用了 Sticker System，适配器会自动为回复追加一张情绪匹配的表情包：

```python
# 先发文字
# 再单独发表情包（单独气泡）
img_body = {
    "group_id": int(group_id),
    "message": [{"type": "image", "data": {"file": base64_data_uri}}]
}
await self._post("send_group_msg", img_body)  # fire-and-forget
```

## 6. NapCat 部署指南

### 6.1 安装 NapCat

**方式一：Docker 部署（推荐）**

```bash
docker run -d \
  --name napcat \
  -p 3000:3000 \
  -p 8766:8766 \
  -p 8765:8765 \
  -v ./napcat/config:/app/napcat/config \
  -v ./napcat/qq:/app/.config/QQ \
  --restart unless-stopped \
  mlikiowa/napcat-docker:latest
```

**方式二：直接安装**

```bash
# 参考 NapCat 官方文档
# https://napcat.napneko.icu/
curl -o napcat.sh https://nclatest.znin.net/
bash napcat.sh
```

### 6.2 配置 NapCat

登录 QQ 后，通过 NapCat WebUI（默认 `http://localhost:6099`）配置：

1. 设置 **HTTP 服务**（端口 3000）
2. 设置 **WebSocket 反向连接**（地址 `ws://你的HermesIP:8766/`）
3. 设置 **HTTP WebHook**（地址 `http://你的HermesIP:8644/webhook/napcat`，secret 与 Hermes 配置一致）
4. 设置 **access_token**（确保与 Hermes config.yaml 中的 `api_token` 一致）

### 6.3 Hermes 插件安装

```yaml
# config.yaml — 启用 napcat-platform 插件
plugins:
  enabled:
    - napcat-platform
```

安装依赖：

```bash
pip install aiohttp
```

### 6.4 启动顺序

```
1. 启动 NapCat → 确认 QQ 在线
2. 启动 Hermes Gateway
3. 检查 bridge_debug.log 确认连接
   [INIT] Bridge ready!
   [INIT] WS: ws://0.0.0.0:8766/
   [INIT] BOT_QQ: 1234567890 | ALL group messages forwarded
```

### 6.5 验证

在 QQ 群中 @葵 发送消息，观察日志：

```
[07:37:58] WS-DECIDE: forward=True reason=ok
[07:37:58] WS: ->Hermes
[07:37:58] WS-SESSION: calling process_message
```

确认回复通过 NapCat API 发送回群：

```
[07:38:09] WS-DECIDE: forward=False reason=self_message
```

## 7. 调试与排障

### 7.1 日志文件

```bash
# 桥接日志（消息流、评分、会话）
tail -f ~/.hermes/bridge_debug.log

# Hermes 网关日志（Webhook 请求）
tail -f ~/.hermes/logs/gateway.log

# Agent 日志（LLM 调用、插件执行）
tail -f ~/.hermes/logs/agent.log
```

### 7.2 常见问题

| 问题 | 可能原因 | 解决方法 |
|------|----------|----------|
| NapCat 收不到消息 | QQ 掉线/WebSocket 未连接 | 重启 NapCat，检查 `bridge_debug.log` |
| 消息转发了但无回复 | 消息评分太低被过滤 | 检查 `WS-DECIDE` 日志中的 `forward=False` 原因 |
| Hermes 回复了但没发到群 | NapCat API token 不匹配 | 检查 config.yaml 中的 `api_token` |
| 重复消息 | 心跳包未正确过滤 | 检查 `TECH_MARKERS` 和 `SKIP_MARKERS` |
| 表情包不显示 | 文件路径错误/格式不支持 | 检查 sticker 文件是否可读，格式是否为 jpg/png/gif |

### 7.3 手动测试

```bash
# 手动测试 NapCat HTTP API 是否正常工作
curl -X POST http://127.0.0.1:3000/send_group_msg \
  -H "Authorization: Bearer your-napcat-secret" \
  -H "Content-Type: application/json" \
  -d '{"group_id": 123456789, "message": [{"type": "text", "data": {"text": "测试消息"}}]}'
```

## 8. 自定义

### 8.1 调整消息评分规则

修改 bridge 层代码（`~/.hermes/plugins/napcat/` 相关文件）中的评分逻辑：

```python
# 增加特定关键词的权重
HIGH_VALUE_KEYWORDS = ["葵", "向日葵", "aoi", "帮我"]
if any(kw in msg for kw in HIGH_VALUE_KEYWORDS):
    score += 40
```

### 8.2 修改拒绝词列表

```python
# adapter.py 中的 _HERMES_NOISE_PATTERNS
_HERMES_NOISE_PATTERNS = [
    "Interrupting current task",
    "Rate limited",
    "Compression model",
    # 添加自定义过滤词
]
```

### 8.3 配置群/私聊过滤

在 bridge 代码中可以配置只监听特定群或特定用户的消息，减少无关干扰。
