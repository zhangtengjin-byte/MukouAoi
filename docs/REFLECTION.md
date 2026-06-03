# Mukou Aoi 反思系统（Reflection）

## 1. 概述

反思系统是葵对群聊成员的**持续性洞察引擎**。它通过定期分析对话记录，自动推测个体特征、行为模式和事件关联，并将有效洞察写入**个体画像库**（ChromaDB），使葵对每个群成员的了解不断深化。

```
每 5 分钟（Cron 定时）→ 反思引擎：
  ├─ run_recent_reflection()  → 全局近期反思（15分钟窗口）
  └─ run_individual_reflection() → 个体深度反思（随机选人）
        │
        ▼
  打分引擎评分 → 阈值判断 → 印证/静默 → 写入历史 JSONL
```

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Reflection System                                               │
│                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐                  │
│  │ recent_reflection │     │individual_reflect│                  │
│  │ (全局近期推演)     │     │ (个体深度反思)    │                  │
│  └────────┬─────────┘     └────────┬─────────┘                  │
│           │                        │                             │
│           ▼                        ▼                             │
│  ┌──────────────────────────────────────────────┐               │
│  │              Scoring Engine                   │               │
│  │  Score = 逻辑一致性(0.4) + 信息充足度(0.3)    │               │
│  │          + 关注价值(0.3)                      │               │
│  │  阈值: ≥ 75 分 → verified（可印证）           │               │
│  │        < 75 分 → silent（静默）               │               │
│  └──────────────────────┬───────────────────────┘               │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────┐               │
│  │            Verification Pipeline              │               │
│  │  1. judge_privacy() → private/public 判断    │               │
│  │  2. generate_verification_message() → 生成验证│              │
│  │  3. route_and_send() → 路由发送（私聊/群聊）   │              │
│  │  4. feed_emotion() → 情绪回灌                 │              │
│  └──────────────────────┬───────────────────────┘               │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────┐               │
│  │            Data Stores                        │               │
│  │  ├─ Individuals DB (ChromaDB) ← 画像更新     │               │
│  │  └─ reflection_history.jsonl ← 历史记录      │               │
│  └──────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 反思模式

### 3.1 全局近期反思（`run_recent_reflection`）

**触发方式**：Cron 定时任务（每 5 分钟）

**流程**：

```
1. 拉取最近 15 分钟所有 session 文件中的用户消息
2. 消息不足 3 条 → 跳过
3. 以最近消息为 query，从长期记忆（ChromaDB）检索相关记忆
4. 读取当前情绪状态作为「滤镜」
5. LLM 推演：找消息间的关联 → 产生推测结论
6. check_duplicate() → 重复则静默（标记 duplicate=True）
7. score_conclusion() → 打分
8. 分数 ≥ 75 → 进入验证管线
9. 分数 < 75 → 静默（仅写入历史）
10. write_history() → 写入 reflection_history.jsonl
```

**应用场景**：
- 发现群聊话题之间的关联
- 检测系统异常（如重复 cron 提示）
- 推测用户情绪变化的可能原因

### 3.2 个体深度反思（`run_individual_reflection`）

**触发方式**：Cron 定时任务（每 5 分钟）

**流程**：

```
1. 初始化（每次调用）
2. 从个体库（individuals_manager）加载最近 12h 活跃个体列表
3. 冷却过滤：跳过过去 4 小时内已发过验证消息的个体
4. 随机选一个活跃个体（最多重试 3 次）
5. 自动补全缺失信息（name/groups）
6. 读取该个体的 recent_messages + profile
7. 读取当前情绪状态作为「滤镜」
8. LLM 推演：结合画像 + 消息 → 尝试推导新洞察
9. check_duplicate(individual_qq=qq) → 同一人去重
10. score_conclusion(conclusion, evidence, profile_data) → 打分
11. 分数 ≥ 75 → 进入验证管线，并尝试更新个体画像
12. 分数 < 75 → 静默（仅写入历史）
13. 去重失败/无洞察 → 重新选人（最多 3 次）
```

**应用场景**：
- 发现个体在特定情绪下的行为模式变化
- 推断个体的新偏好或性格特征
- 识别个体间的关系进展
- 捕捉个体的自我突破或状态改变

## 4. 个体库（Individuals DB）

### 4.1 存储

基于 **ChromaDB**，使用 **SiliconFlow BGE-large-zh-v1.5** 嵌入：

- **Collection**: `individuals`
- **路径**: `~/.hermes/workspace/individuals_db/`
- **维度**: 1024 维
- **距离**: cosine

个体条目结构：

```json
{
  "id": "individual:qq:1234567890",
  "document": "姓名: 用户。性格特点: 认真，技术控。偏好: 技术，写作，AI。",
  "metadata": {
    "name": "用户",
    "qq": "1234567890",
    "source": "群聊",
    "first_seen": "2026-06-01T00:00:00+08:00",
    "profile_json": "{\"traits\": [...], \"relationships\": {...}, \"preferences\": [...], \"facts\": [...]}",
    "profile_count": 12,
    "profile_updated": "2026-06-04T00:52:10+08:00",
    "last_interaction": "2026-06-04T00:52:10+08:00",
    "groups_json": "[\"987654321\"]",
    "recent_messages_json": "[...]"
  }
}
```

### 4.2 画像更新

反思系统在验证（verified）后，会自动将 LLM 建议的新特征/事实写入个体库：

```python
def _try_update_individual_profile(qq, reflection_result):
    suggested_traits = reflection_result.get("suggested_traits", [])
    suggested_facts = reflection_result.get("suggested_facts", [])
    # 去重后追加到现有画像
    mgr.update_individual(qq, {"profile": updates})
```

## 5. 打分引擎（Scoring Engine）

### 5.1 三维度评分

```python
Score = 逻辑一致性(×0.4) + 信息充足度(×0.3) + 关注价值(×0.3)
```

| 维度 | 权重 | 说明 |
|------|------|------|
| 逻辑一致性 | 0.4 | 结论是否从证据中合理推导？有无逻辑跳跃？ |
| 信息充足度 | 0.3 | 证据是否充分支撑结论？证据量是否足够？ |
| 关注价值 | 0.3 | 结论对了解该人物是否有新洞察？ |

### 5.2 LLM 评分

打分引擎通过 **Claude Sonnet 4**（通过 MiniMax 代理）或 **DeepSeek Chat**（fallback）进行评分：

```python
def score_conclusion(conclusion, evidence, profile_data=None):
    # 1. 构建评分 prompt
    # 2. 调用 Claude/MiniMax（优先）
    # 3. 失败降级 → DeepSeek
    # 4. 两次都失败 → 默认 50 分
    # 5. 解析 JSON 响应 → 计算加权总分
    # 6. 返回 (total_score, breakdown)
```

### 5.3 阈值

- **默认阈值**: 75 分
- **≥ 75**: 认定为有价值洞察，进入验证管线
- **< 75**: 静默丢弃（保留在历史中供去重参考）

### 5.4 打分响应格式

```json
{
  "logic_consistency": 85,
  "info_sufficiency": 60,
  "attention_value": 70,
  "total": 73.0,
  "reasoning": "逻辑一致性较高，从证据中可合理推导……"
}
```

## 6. 去重机制

### 6.1 语义去重

反思引擎使用 LLM 判断新结论是否与最近 24h 的历史结论语义近似：

```python
def check_duplicate(new_conclusion, individual_qq=""):
    # 读取 24h 历史
    # 如果指定了 individual_qq，只比较同一人的结论
    # LLM 判断：DUPLICATE or UNIQUE
```

### 6.2 个体冷却

已验证的个体在 **4 小时**内不会被再次选中为反思对象，避免频繁骚扰同一人。

## 7. 验证管线（Verification）

### 7.1 私密性判断

```python
judge_privacy(conclusion, evidence, individual_qq) → "public" | "private"
```

- **public**：技术讨论、兴趣爱好、群聊一般话题
- **private**：健康、情感、家庭隐私、个人生活细节

### 7.2 生成验证消息

根据私密性判断结果，生成葵风格的天然验证消息：

```python
generate_verification_message(conclusion, evidence, qq, name, is_private)
```

- 私密消息：温柔的关心/安慰，小心翼翼的试探
- 公开消息：轻松的提问/接话/肯定，欢快地搭话
- 必须符合葵的语气风格：碎片化短句、语气词、甜腻

### 7.3 路由发送

```
route_and_send(verification_message, individual_qq, group_id)
  → 私密话题 → 私聊发送
  → 公开话题 → 群聊发送
  → 验证消息回灌 → 更新情绪状态
```

### 7.4 情绪回灌

验证消息发出后，`_feed_emotion()` 扫描消息中的 emotion_map 关键词，自动将匹配的情绪增量写回 `emotion.json`，实现"说话影响情绪"的闭环。

## 8. 历史记录

所有反思结果（包括静默的）写入 `~/.hermes/workspace/reflection_history.jsonl`：

```jsonl
{"type": "individual", "individual": "1234567890", "individual_name": "用户昵称", "conclusion": "用户在写作瓶颈后进入高度兴奋的创作活跃期……", "score": 84.0, "action": "verified", "evidence": ["...", "..."], "time": "2026-06-03T03:20:59+08:00", "duplicate": false}
{"type": "recent", "conclusion": "群聊中反复出现相同的系统提示……", "score": 0, "action": "silent", "evidence": ["...", "..."], "time": "2026-06-03T05:40:02+08:00", "duplicate": true}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `type` | `"recent"` 全局反思 / `"individual"` 个体反思 |
| `individual` | 个体 QQ 号（仅个体反思） |
| `individual_name` | 个体昵称 |
| `conclusion` | LLM 得出的推测结论 |
| `score` | 打分总分（0=去重失败/跳过） |
| `action` | `"verified"` 可印证 / `"silent"` 静默 |
| `evidence` | 证据列表 |
| `duplicate` | 是否为重复结论 |
| `score_breakdown` | 三维度评分明细（仅非重复条目） |

**淘汰机制**：超过 24 小时的旧条目自动清理（`clean_history()`）。

## 9. 情绪滤镜

反思引擎在调用 LLM 推演前，会读取当前情绪状态作为**分析滤镜**：

```
【葵当前情绪：欣喜：很开心很甜，语气活泼】
请将此情绪作为你分析的「滤镜」——
如果是开心/乐观，倾向于看到积极面；
如果是愤怒/攻击性，可以对人产生更尖锐的解读；
如果是悲伤/悔恨，可以注意到脆弱和遗憾。
```

这使得反思结论能反映出葵当前情绪状态的影响，产生多样化的洞察。

## 10. 自定义配置

### 10.1 调整打分阈值

```python
# reflection_engine.py
SCORE_THRESHOLD = 75   # 提高→更严格，降低→更宽松
```

### 10.2 调整反思频率

通过 Hermes Cron 任务配置（每 5 分钟执行一次）：

```yaml
# config.yaml 中 cron 配置
cron:
  wrap_response: true
  max_parallel_jobs: null
```

### 10.3 调整冷却时间

```python
INDIVIDUAL_COOLDOWN_HOURS = 4  # 个体验证后冷却时间（小时）
MAX_HISTORY_AGE_HOURS = 24     # 历史淘汰时限
```

### 10.4 评分模型配置

```python
# reflection_scorer.py
SCORING_MODEL = "claude-sonnet-4-20250514"  # 或 "deepseek-chat"
SCORING_TIMEOUT = 45.0
```

## 11. Cron 回调入口

反思系统通过 Hermes 的 cron 系统定时触发。执行入口位于 `reflection_engine.py` 或相应的 cron 处理函数中：

1. 调用 `run_recent_reflection(minutes=15)` — 全局推演
2. 调用 `run_individual_reflection()` — 个体深度反思
3. 结果交给 `verify()` 做后续的印证/发送
