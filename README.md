# Mukou Aoi — Hermes Agent 人格化引擎套件

> 让 AI Agent 不是只回答问题，而是有血有肉地活着。

**Mukou Aoi** 是一个为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 打造的人格化引擎套件。它不是又一个 AI 框架，而是一整套**让 Agent 拥有情绪、记忆、人格一致性和社交能力**的插件与技能集合。

---

## ✨ 特性

| 组件 | 作用 |
|------|------|
| **Emotion Governor** | 八维 Plutchik 情绪向量 + 关键词触发 + 16 种复合情绪 + 自然波动衰减 + 风格注入 |
| **Mode Switch** | `@work` / `@life` 模式切换，生活模式自动约束回复长度 |
| **Memory RAG** | ChromaDB + BGE 向量检索，让 Agent 记住你是谁 |
| **Reflection System** | 画像自动更新 + 近期/个体反思 + 打分引擎 + 验证管道 |
| **QQ Bridge** | NapCat + Webhook 群聊桥接，消息过滤评分，会话管理 |
| **Sticker System** | 情绪匹配表情包自动追加，让对话更生动 |

搭配 SOUL.md / MEMORY.md 持久化人格设定，Agent 重启后依然知道「我是谁」。

---

## 🧱 架构总览

```
                      ┌──────────────┐
                      │  User Input   │
                      └──────┬───────┘
                             │
                      ┌──────▼───────┐
                      │   Gateway    │ ← QQ Bot / NapCat / CLI / Webhook
                      └──────┬───────┘
                             │
                ┌────────────▼────────────┐
                │   pre_gateway_dispatch  │ ← mode-switch: @work/@life
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │     pre_llm_call        │ ← emotion-governor: 情绪检测+注入
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │     Hermes Agent        │ ← LLM 推理 + 工具调用
                │  (情绪上下文已注入)       │
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │         Skills          │ ← memory-rag / reflection / sticker
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │  post_llm_call → Send   │
                └─────────────────────────┘
```

详细架构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 📦 安装

> CI 状态：⏳ 等待运行中（首次启动可能需要几分钟）

### 前提

- Hermes Agent（推荐 v0.15+）
- Python ≥ 3.11
- （可选）ChromaDB（用于记忆 RAG）
- （可选）SiliconFlow API Key（用于 BGE 向量嵌入）
- （可选）NapCat + Docker（用于 QQ 群聊桥接）

### 从源码安装

```bash
git clone https://github.com/your-username/mukou-aoi.git
cd mukou-aoi
pip install -e .

# 一键部署到 Hermes
mukou-aoi-install
```

### 手动部署

1. 将 `plugins/emotion-governor/` 复制到 `~/.hermes/hermes-agent/plugins/`
2. 将 `plugins/mode-switch/` 复制到 `~/.hermes/hermes-agent/plugins/`
3. 复制 `mukou_aoi/examples/tone_map.json` 到 `~/.hermes/tone_map.json`
4. 在 `~/.hermes/config.yaml` 中启用插件
5. 重启 Hermes Gateway

### 配置示例

```yaml
# ~/.hermes/config.yaml
plugins:
  emotion-governor:
    enabled: true
  mode-switch:
    enabled: true
```

完整配置示例见 [examples/config.example.yaml](examples/config.example.yaml)。

---

## 📚 文档

| 文档 | 说明 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构总览、数据流、组件关系 |
| [docs/EMOTION_SYSTEM.md](docs/EMOTION_SYSTEM.md) | 情绪系统深度解析：8 维向量、16 复合情绪、算法细节 |
| [docs/MEMORY_RAG.md](docs/MEMORY_RAG.md) | 记忆 RAG 系统：ChromaDB、向量检索、自动存档 |
| [docs/REFLECTION.md](docs/REFLECTION.md) | 反思系统：画像更新、打分引擎、验证管道 |
| [docs/NAPCAT_BRIDGE.md](docs/NAPCAT_BRIDGE.md) | QQ 群聊桥接：NapCat 部署、传入传出双通路、消息过滤、会话管理 |
| [docs/CRON_MAINTENANCE.md](docs/CRON_MAINTENANCE.md) | 定时任务：画像去毒（必需）、每日早报与总结（可选） |

---

## 🎨 自定义

### 情绪表达

编辑 `~/.hermes/tone_map.json` 可以自定义每种情绪的：
- **风格描述**：当前情绪下 Agent 的语气
- **句式示例**：注入到 LLM 上下文的模板
- **语气词**：句尾语气词列表
- **禁用词**：当前情绪下禁止使用的词语
- **emoji**：情绪对应的表情符号

### 关键词映射

编辑 `~/.hermes/emotion_map.json` 可以配置：
- `_verb_emotions`：动词→情绪变化映射
- `_adjective_emotions`：形容词→情绪变化映射
- `_negation_keywords`：否定词列表
- `_intensity_map`：程度副词→强度倍率

### Agent 名称

在 `plugins/emotion-governor/__init__.py` 中修改 `AGENT_PRONOUNS` 和 `USER_PRONOUNS`：

```python
AGENT_PRONOUNS = ["YourAgentName", "your-agent"]
USER_PRONOUNS = ["User", "user"]
```

---

## 📦 项目结构

```
MukouAoi/
├── pyproject.toml              # Python 包定义
├── LICENSE                     # MIT
├── README.md                   # 本文件
├── docs/                       # 架构文档
│   ├── ARCHITECTURE.md
│   ├── EMOTION_SYSTEM.md
│   ├── MEMORY_RAG.md
│   ├── REFLECTION.md
│   └── NAPCAT_BRIDGE.md
├── plugins/                    # Hermes 插件
│   ├── emotion-governor/       # 情绪引擎
│   │   ├── __init__.py
│   │   └── plugin.yaml
│   └── mode-switch/            # 模式切换
│       ├── __init__.py
│       ├── mode.txt
│       └── plugin.yaml
├── mukou_aoi/                  # Python 包
│   ├── __init__.py
│   ├── install.py              # 一键安装脚本
│   └── examples/               # 示例数据
│       └── tone_map.json
├── examples/                   # 配置文件示例
│   └── config.example.yaml
└── skills/                     # （可选）复用的 Skill 文档
```

---

## 🤝 贡献

如果你也有让 Agent 更有人味的想法，欢迎提 Issue 或 PR。

---

## 📄 许可

MIT License — 可自由使用、修改、商用，保留原始版权声明即可。

---

## 🙏 致谢

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) — 强大的 AI Agent 框架
- [蛋蛋](https://github.com/GiriYomi) — 提供了很多思路上的帮助
- [ChromaDB](https://www.trychroma.com/) — 向量数据库
- [NapCat](https://napcat.napneko.icu/) — QQ 框架
