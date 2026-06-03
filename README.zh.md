<p align="center">
  <a href="README.md"><kbd style="display:inline-block;padding:8px 24px;margin:3px;background:#f6f8fa;color:#333;border-radius:7px;font-weight:600;font-size:14px;border:1px solid #d0d7de;box-shadow:0 1px 3px rgba(0,0,0,0.06)">English</kbd></a>
  <a href="README.zh.md"><kbd style="display:inline-block;padding:8px 24px;margin:3px;background:#1a1a1a;color:#fff;border-radius:7px;font-weight:600;font-size:14px;border:1px solid #444;box-shadow:0 2px 4px rgba(0,0,0,0.3)">中文</kbd></a>
  <a href="https://qm.qq.com/q/721815130" target="_blank"><kbd style="display:inline-block;padding:8px 24px;margin:3px;background:#07C160;color:#fff;border-radius:7px;font-weight:600;font-size:14px;border:1px solid #06ad56;box-shadow:0 2px 4px rgba(7,193,96,0.3)">加入 QQ 群</kbd></a>
  <a href="mailto:ofgm@foxmail.com"><kbd style="display:inline-block;padding:8px 24px;margin:3px;background:#4A90D9;color:#fff;border-radius:7px;font-weight:600;font-size:14px;border:1px solid #3a7bc8;box-shadow:0 2px 4px rgba(74,144,217,0.3)">✉ ofgm@foxmail.com</kbd></a>
</p>

# Mukou Aoi — Hermes Agent 人格化引擎套件

让 AI Agent 不只是回答问题，而是有血有肉地活着。

**Mukou Aoi** 是一个为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 打造的人格化引擎套件。它不是又一个 AI 框架，而是一整套让 Agent 拥有情绪、记忆、人格一致性和社交能力的插件与技能集合。

---

## 架构图

<p align="center">
  <a href="assets/architecture-v2.png" target="_blank"><img src="assets/architecture-v2.png" alt="Mukou Aoi Architecture" width="90%"/></a>
</p>

架构说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 组件

| 组件 | 说明 |
|-----------|-------------|
| Emotion Governor | 8 维 Plutchik 情绪向量，关键词触发，16 种复合情绪，自然波动衰减，风格注入 |
| Mode Switch | `@work` / `@life` 模式切换，生活模式自动限制回复长度 |
| Memory RAG | ChromaDB + BGE 向量检索，持久化 Agent 记忆 |
| Reflection System | 自动画像归档，个体/近期反思流水线，评分引擎与证据校验 |
| QQ Bridge | NapCat + Webhook 群聊桥接，消息评分，会话管理，多群支持 |
| Sticker System | 情绪匹配表情包自动追加，让对话更有表现力 |

配合 SOUL.md / MEMORY.md 持久人格配置，Agent 在重启后保持身份一致。

---

## 前置条件

- Hermes Agent（推荐 v0.15+）
- Python >= 3.11
- （可选）ChromaDB 用于 Memory RAG
- （可选）SiliconFlow API Key 用于 BGE 向量嵌入
- （可选）NapCat + Docker 用于 QQ 群聊桥接

---

## 安装

### 源码安装

```bash
git clone https://github.com/zhangtengjin-byte/MukouAoi.git
cd MukouAoi
pip install -e .

# 一键部署到 Hermes
mukou-aoi-install
```

### 手动部署

1. 将 `plugins/emotion-governor/` 复制到 `~/.hermes/hermes-agent/plugins/`
2. 将 `plugins/mode-switch/` 复制到 `~/.hermes/hermes-agent/plugins/`
3. 将 `mukou_aoi/examples/tone_map.json` 复制到 `~/.hermes/tone_map.json`
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

## 文档

| 文档 | 说明 |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构概览，数据流，组件关系 |
| [EMOTION_SYSTEM.md](docs/EMOTION_SYSTEM.md) | 情绪系统深度解析：8 维向量，16 种复合情绪，算法 |
| [MEMORY_RAG.md](docs/MEMORY_RAG.md) | 记忆 RAG 系统：ChromaDB，向量检索，自动归档 |
| [REFLECTION.md](docs/REFLECTION.md) | 反思系统：画像更新，评分引擎，校验流水线 |
| [NAPCAT_BRIDGE.md](docs/NAPCAT_BRIDGE.md) | QQ 群聊桥接：NapCat 部署，双通道消息，消息过滤，会话管理 |
| [CRON_MAINTENANCE.md](docs/CRON_MAINTENANCE.md) | 定时任务：情绪波动、反思、画像更新、记忆去毒（必需）；NapCat 监控、早报、总结（选装） |

---

## 自定义

### 情绪表达

编辑 `~/.hermes/tone_map.json` 自定义每种情绪：
- **风格描述**：Agent 在各情绪状态下的语气
- **例句**：注入 LLM 上下文的模板
- **语气词**：句末语气词列表
- **禁用词**：当前情绪状态下禁止使用的词
- **Emoji**：每种情绪对应的表情符号

### 关键词映射

编辑 `~/.hermes/emotion_map.json` 配置：
- `_verb_emotions`：动词到情绪的映射
- `_adjective_emotions`：形容词到情绪的映射
- `_negation_keywords`：否定词列表
- `_intensity_map`：副词到强度倍数映射

### Agent 身份

修改 `plugins/emotion-governor/__init__.py` 中的 `AGENT_PRONOUNS` 和 `USER_PRONOUNS`：

```python
AGENT_PRONOUNS = ["YourAgentName", "your-agent"]
USER_PRONOUNS = ["User", "user"]
```

---

## 项目结构

<p align="center">
  <a href="assets/structure-1780516769.png" target="_blank"><img src="assets/structure-1780516769.png" alt="Mukou Aoi Project Structure" width="90%"/></a>
</p>

---

## 贡献

如果你有让 AI Agent 更有人性的想法，欢迎提交 Issue 或 PR。

---

## 许可证

MIT License — 可自由使用、修改和分发。保留原始版权声明。

---

## 致谢

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) — 底层 AI Agent 框架
- [西园寺の双黄又蛋蛋](https://github.com/GiriYomi) — 提供有价值的想法和见解
- [Dear Mr. N.A.](mailto:1065696132@qq.com) — 提供压力测试群聊渠道
- [ChromaDB](https://www.trychroma.com/) — 向量数据库
- [NapCat](https://napcat.napneko.icu/) — QQ 框架
