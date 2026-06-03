# Mukou Aoi（向日葵）架构文档

## 1. 项目概述

**Mukou Aoi（向日葵）** 是一个基于 [Hermes Agent](https://hermes-agent.nousresearch.com/) 框架构建的**人格引擎套件**（Personality Engine Suite）。它通过一系列可插拔的插件与钩子系统，为 Hermes Agent 赋予**自适应情感表达、多模式切换、长期记忆与反思、以及社交平台桥接**等高级能力。

简单来说，Mukou Aoi 让一个通用 LLM Agent 能够：

- **带情绪说话** — 根据对话内容和时间自然产生喜怒哀乐，并影响回复风格
- **切换工作/生活模式** — 在不同场景下自动调整语气、长度和行为边界
- **记住你是谁** — 通过 RAG 和反思系统构建长期记忆档案
- **接入 QQ 群聊** — 通过 NapCat 桥接，在真实聊天环境中持续运行

项目命名取自日语"向日葵"的罗马音，寓意像向日葵一样面向用户、感知环境并动态回应。

---

## 2. 系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                        用户 / QQ 群聊                         │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  ████████   Gateway（网关层）                                │
│  ┌─ 请求路由   ┌─ 消息过滤   ┌─ 会话管理                    │
│  └─ pre_gateway_dispatch 钩子入口                            │
├──────────────────────────────────────────────────────────────┤
│  ████████   Agent Core（代理核心层）                          │
│  ┌─ 会话上下文维护  ┌─ LLM 调用管理                          │
│  └─ pre_llm_call / post_llm_call 钩子系统                    │
├──────────────────────────────────────────────────────────────┤
│  ████████   Plugins（插件层）                                │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │   emotion-governor │  │   mode-switch     │                 │
│  │   (情绪控制)       │  │   (模式切换)       │                 │
│  ├──────────────────┤  ├──────────────────┤                 │
│  │   Memory RAG      │  │   Reflection      │                 │
│  │   (记忆检索)       │  │   (反思系统)       │                 │
│  ├──────────────────┤  ├──────────────────┤                 │
│  │   NapCat Bridge   │  │   Sticker System  │                 │
│  │   (QQ 桥接)       │  │   (贴纸系统)       │                 │
│  └──────────────────┘  └──────────────────┘                 │
├──────────────────────────────────────────────────────────────┤
│  ████████   Skills（技能层）                                 │
│  ┌─ hermes-agent（基础技能）                                 │
│  ┌─ 自定义技能（按需加载）                                    │
├──────────────────────────────────────────────────────────────┤
│  ████████   Data（数据层）                                   │
│  ┌─ ChromaDB（向量数据库）   ┌─ BGE Embedding 模型           │
│  ┌─ 配置文件（JSON/YAML）    ┌─ 贴纸资源库                   │
│  ┌─ 日志 / 会话存档                                          │
└──────────────────────────────────────────────────────────────┘
```

**分层说明：**

| 层级 | 职责 |
|------|------|
| **Gateway** | 对外通信入口，接收用户消息并分发。NapCat 桥接器的 Webhook 在此层注入。 |
| **Agent Core** | Hermes Agent 核心引擎，管理会话生命周期与 LLM（大语言模型）调用。三个钩子点（`pre_gateway_dispatch`、`pre_llm_call`、`post_llm_call`）供插件注入逻辑。 |
| **Plugins** | Mukou Aoi 的核心价值所在。每个插件通过注册钩子函数，在 Agent 生命周期的关键节点修改行为。 |
| **Skills** | Hermes Agent 原生技能系统，提供工具调用、代码执行等能力。 |
| **Data** | 持久化层，包括向量数据库（ChromaDB）、嵌入模型（BGE）、配置文件和媒体资源。 |

---

## 3. 核心组件说明

### 3.1 emotion-governor 插件（情绪控制引擎）

**挂载钩子：** `pre_llm_call`

**设计原理：** 基于 **Plutchik 情绪轮盘**（Plutchik's Wheel of Emotions）的 8 维度情绪向量模型。

**核心特性：**

| 特性 | 说明 |
|------|------|
| **8 维度向量** | 喜悦、信任、恐惧、惊讶、悲伤、厌恶、愤怒、期待各维度独立值（0-1） |
| **关键词触发** | 通过 `emotion_map.json` 配置触发词->情绪向量映射。用户消息中出现"开心"→喜悦+0.3，"失误"→悲伤+0.2 |
| **16 种复合情绪** | 两种基本情绪组合产生复合情绪（如喜悦+信任=爱、恐惧+惊讶=敬畏） |
| **自然衰减** | 情绪向量随时间自然波动回归基线，模拟真实情绪变化 |
| **语气注入** | 根据当前情绪向量，从 `tone_map.json` 匹配最近风格模板，注入 system prompt |

**工作流程：**

```
用户消息 → 关键词扫描 → 情绪向量更新 → 自然衰减 → 
选择情绪风格（highest pair）→ 从 tone_map 获取模板 → 
注入 system prompt（风格说明、语气词、禁用词、emoji）
```

**配置文件：**

- `emotion_map.json` — 关键词到情绪向量的映射规则
- `tone_map.json` — 情绪风格到回复模板的映射

### 3.2 mode-switch 插件（模式切换引擎）

**挂载钩子：** `pre_gateway_dispatch`

**设计原理：** 根据消息中显式提到的 `@work` 或 `@life` 标签切换 Agent 运行模式。

**核心特性：**

| 特性 | 说明 |
|------|------|
| **工作模式** | 回复精炼、克制、信息密度高，包含字数上限注入 |
| **生活模式** | 回复自由、口语化、允许随意表达 |
| **模式持久化** | 当前模式记录在会话上下文中，持续生效直到主动切换 |
| **字数限制** | 工作模式下通过 system prompt 注入字数上限约束 |

**工作流程：**

```
用户消息 → 检测 @work/@life → 更新模式状态 → 
注入对应 system prompt（含字数限制）→ 转发至后续处理
```

### 3.3 Memory RAG 系统（记忆检索与存储）

**技术栈：** ChromaDB + BGE（BAAI General Embedding）向量模型

**核心特性：**

| 特性 | 说明 |
|------|------|
| **向量检索** | 用户消息编码为向量后，在 ChromaDB 中检索最相似的历史会话片段 |
| **会话索引** | 按 session_id 索引，支持跨会话检索和单会话聚焦 |
| **BGE 模型** | 使用 BAAI 的 bge-small-zh-v1.5 或类似模型，针对中文优化 |
| **相似度评分** | 返回 Top-K 结果及相似度分数，供下游筛选 |

**工作流程：**

```
用户消息 → BGE Embedding 编码 → ChromaDB 向量检索 → 
排序结果 → 注入上下文（格式化为记忆片段）→ LLM 可见
```

### 3.4 Reflection 系统（反思与档案进化）

**设计原理：** 在每次会话结束后，分析对话摘要，更新 Agent 关于用户的「个人档案」。

**核心特性：**

| 特性 | 说明 |
|------|------|
| **档案构建** | 从对话中提取用户特征、偏好、关系状态等 |
| **评分引擎** | 对每个记忆片段进行重要性评分（基于情感强度、交互频率等） |
| **增量更新** | 不覆盖已有档案，而是增量补充或修正 |
| **个人图书馆** | 每个用户维护独立的"图书馆"，包含所有历史反思输出 |

**工作流程：**

```
会话结束 → LLM 总结对话 → 提取新增信息 → 
评分引擎打分 → 更新用户档案 → 存入个人图书馆
```

### 3.5 NapCat QQ 群聊桥接

**设计原理：** 通过 NapCat 的 Webhook 订阅 QQ 群消息，实现 Hermes Agent 与 QQ 群聊的双向通信。

**核心特性：**

| 特性 | 说明 |
|------|------|
| **Webhook 订阅** | NapCat 作为 HTTP/WebSocket 服务端，Hermes 作为客户端订阅消息 |
| **消息过滤** | 根据关键词、@提及、消息长度等规则过滤无关消息 |
| **消息评分** | 对候选回复进行评分（相关性、时效性、安全性），高分才发送 |
| **群适配器** | 处理 QQ 特有的消息格式（At、表情、图片等） |

**工作流程：**

```
QQ 群消息 → NapCat Webhook → Hermes Gateway（过滤/评分）→ 
Agent 处理 → 生成回复 → 评分审核 → NapCat API 发送回群
```

### 3.6 Sticker 自动附加系统（贴纸系统）

**设计原理：** 在 Agent 生成回复时，根据回复情绪和内容自动匹配一张贴纸/表情图片附加到消息中。

**核心特性：**

| 特性 | 说明 |
|------|------|
| **情绪匹配** | 根据当前情绪向量选择对应情绪类型的贴纸 |
| **贴纸库** | 本地存储贴纸文件及标签索引 |
| **自动附加** | 回复生成后自动在末尾附加贴纸（标记格式：`MEDIA:/path/to/sticker`） |
| **去重保护** | 同一贴纸在短时间内不重复使用 |

---

## 4. 数据流

### 完整请求链路

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────┐
│  Gateway（网关层）                           │
│  ┌─ 消息解析、来源判断                       │
│  └─ 调用 pre_gateway_dispatch 钩子           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  pre_gateway_dispatch（模式切换）            │
│  ┌─ mode-switch 插件                        │
│  │  ├─ 检测 @work/@life                    │
│  │  ├─ 更新当前模式                        │
│  │  └─ 注入模式相关提示词                   │
│  └─ 返回修改后的消息及上下文                 │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Agent Core（核心处理）                      │
│  ┌─ 构建消息上下文                           │
│  ├─ Memory RAG 检索历史记忆                 │
│  ├─ Reflection 加载用户档案                 │
│  └─ 调用 pre_llm_call 钩子                 │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  pre_llm_call（情绪注入）                    │
│  ┌─ emotion-governor 插件                  │
│  │  ├─ 扫描关键词更新情绪向量              │
│  │  ├─ 自然衰减计算                        │
│  │  ├─ 匹配 tone_map 风格模板              │
│  │  └─ 注入 system prompt（风格、禁用词）   │
│  └─ 返回修改后的 system prompt              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  LLM（大语言模型）                           │
│  ┌─ 接收完整 prompt（上下文+记忆+情绪）     │
│  ├─ 生成回复文本                            │
│  └─ 返回原始回复                            │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  post_llm_call（后处理）                     │
│  ┌─ emotion-governor 情绪衰减更新           │
│  ├─ Sticker System 匹配贴纸                │
│  ├─ Reflection 系统触发（异步）             │
│  └─ Memory 存储本次对话                     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Gateway（回复输出）                         │
│  ┌─ 格式化回复（含贴纸 MEDIA 标记）         │
│  ├─ NapCat 桥接发送至 QQ 群                 │
│  └─ 或直接返回用户                          │
└─────────────────────────────────────────────┘
                   │
                   ▼
               用户收到回复
```

### 钩子调用时序

| 钩子点 | 调用时机 | 主要插件 | 修改内容 |
|--------|---------|---------|---------|
| `on_session_start` | 新会话创建时 | all plugins | 初始化情绪状态、加载用户档案 |
| `pre_gateway_dispatch` | 消息分发前 | mode-switch | 消息内容、模式状态 |
| `pre_llm_call` | LLM 调用前 | emotion-governor | system prompt（情绪注入） |
| `post_llm_call` | LLM 调用后 | emotion-governor, Sticker, Reflection | 情绪衰减、贴纸附加、反思触发 |

---

## 5. 安装与配置

### 前提条件

- Python 3.10+
- Hermes Agent（已安装并初始化）
- NapCat（仅 QQ 桥接场景需要）
- ChromaDB（仅 Memory RAG 场景需要）

### 安装步骤

#### 1. 克隆仓库

```bash
git clone https://github.com/your-org/MukouAoi.git
cd MukouAoi
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

核心依赖包括：

| 包 | 用途 |
|----|------|
| `chromadb` | 向量数据库 |
| `sentence-transformers` | BGE 嵌入模型 |
| `aiohttp` | NapCat Webhook |

#### 3. 配置 Hermes Agent 加载插件

在 Hermes Agent 的 profiles 配置中，添加插件声明：

```yaml
# ~/.hermes/profiles/default.yaml 或对应 profile
plugins:
  emotion-governor:
    enabled: true
    config:
      emotion_map: "plugins/emotion-governor/emotion_map.json"
      tone_map: "plugins/emotion-governor/tone_map.json"
  mode-switch:
    enabled: true
  memory-rag:
    enabled: true
    config:
      collection_name: "mukou_aoi_memories"
      embedding_model: "BAAI/bge-small-zh-v1.5"
      top_k: 5
  reflection:
    enabled: true
  napcat-bridge:
    enabled: false  # 默认为关闭，QQ 场景打开
    config:
      webhook_url: "http://localhost:3000/webhook"
      group_ids: ["123456789"]
  sticker-system:
    enabled: true
    config:
      sticker_dir: "data/stickers"
```

#### 4. （可选）配置 NapCat

参考 NapCat 官方文档搭建 Webhook 服务，并在配置中指定推送地址为 Hermes Agent 的网关入口。

#### 5. 启动 Hermes Agent

```bash
hermes start
```

### 目录结构

```
MukouAoi/
├── plugins/
│   ├── emotion-governor/       # 情绪控制插件
│   │   ├── __init__.py
│   │   ├── emotion_map.json    # 关键词->情绪映射
│   │   └── tone_map.json       # 情绪->语气模板映射
│   ├── mode-switch/            # 模式切换插件
│   ├── memory-rag/             # 记忆 RAG 插件
│   ├── reflection/             # 反思系统插件
│   ├── napcat-bridge/          # QQ 群聊桥接插件
│   └── sticker-system/         # 贴纸自动附加插件
├── data/
│   ├── stickers/               # 贴纸文件
│   └── chroma_db/              # ChromaDB 持久化数据
├── docs/
│   └── ARCHITECTURE.md         # 本文档
└── config/
    └── AGENT_PRONOUNS          # Agent 名称与代称配置
```

---

## 6. 自定义指南

### 6.1 tone_map.json — 情绪表达风格定制

`tone_map.json` 定义了不同情绪状态下 Agent 的回复风格。每条记录包含：

```json
{
  "emotions": {
    "joy": 0.8,
    "trust": 0.6
  },
  "style": "温暖亲切",
  "description": "很开心，很信任对方",
  "template": {
    "greeting": "诶嘿嘿～",
    "prefix": "葵会开开心心地",
    "tone_words": ["呢", "呀", "~"],
    "forbidden_words": ["滚", "闭嘴"],
    "emoji": ["😊", "🌸"]
  }
}
```

**自定义方法：**

- 修改 `emotions` 中的维度阈值，控制何时触发该风格
- 修改 `template` 中的语气词、禁用词和 emoji
- 新增条目以扩展情绪表达多样性

### 6.2 emotion_map.json — 关键词触发集定制

`emotion_map.json` 定义了对话中哪些关键词会触发情绪变化：

```json
{
  "keywords": {
    "开心": {"joy": 0.3, "trust": 0.1},
    "对不起": {"sadness": 0.2, "trust": -0.1},
    "好厉害": {"joy": 0.2, "surprise": 0.3}
  }
}
```

**自定义方法：**

- 增加或减少关键词条目
- 调整每个关键词触发的情绪向量变化幅度（0.0 ~ 1.0）
- 支持负值（如 `trust: -0.1` 表示信任度下降）

### 6.3 AGENT_PRONOUNS — 角色名设定

`AGENT_PRONOUNS` 是一个纯文本配置文件，定义 Agent 的名称和自称/他称方式：

```
# Agent 名称配置
AGENT_NAME=葵
SELF_REFERENCE=我
USER_REFERENCE=你
ALTERNATE_NAMES=小葵,向葵酱
PLURAL_SELF=我们
```

**自定义方法：**

- 替换 `AGENT_NAME` 为任意角色名称
- 调整 `SELF_REFERENCE` 和 `USER_REFERENCE` 以匹配角色关系
- 在 `ALTERNATE_NAMES` 中列出可供引用的别名

### 6.4 其他自定义维度

| 配置文件 | 路径 | 自定义内容 |
|---------|------|-----------|
| 插件开关 | `profiles/*.yaml` | 启用/禁用各个插件 |
| ChromaDB 集合名 | 插件配置 | 修改向量数据库集合名称 |
| 情绪衰减速率 | emotion-governor 配置 | 调整情绪回归基线的速度 |
| 记忆检索 Top-K | memory-rag 配置 | 控制注入上下文中的记忆片段数量 |
| 贴纸库 | `data/stickers/` | 增加/替换贴纸图片文件 |

---

## 附录 A：技术栈一览

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| Agent 框架 | Hermes Agent | Nous Research 出品，提供钩子系统 |
| 情感模型 | Plutchik Wheel | 8 维度 + 16 复合情绪 |
| 向量数据库 | ChromaDB | 轻量、本地化、Python 原生 |
| 嵌入模型 | BGE (BAAI) | 中文优化，Sentence-Transformers |
| QQ 桥接 | NapCat | Webhook 驱动，支持群聊/私聊 |
| 配置文件 | JSON / YAML | 插件配置、情绪映射、语气模板 |

## 附录 B：相关资源

- [Hermes Agent 官方文档](https://hermes-agent.nousresearch.com/docs)
- [Plutchik 情绪轮盘](https://en.wikipedia.org/wiki/Robert_Plutchik)
- [ChromaDB](https://www.trychroma.com/)
- [BGE Embedding](https://github.com/FlagOpen/FlagEmbedding)
- [NapCat](https://napcat.napneko.icu/)
