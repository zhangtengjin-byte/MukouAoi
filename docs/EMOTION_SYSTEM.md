# Mukou Aoi 情绪系统（Emotion Governor）详解

## 1. 概述

情绪系统是 Mukou Aoi 最核心的人格化模块。它基于 **Robert Plutchik 情绪轮盘理论**，为 LLM Agent 赋予动态的情绪感知和表达能力。

情绪系统的工作流程：

```
用户消息 → 关键词检测 → 情绪向量更新 → 自然衰减 →
确定复合情绪 → 匹配语气模板 → 注入 system prompt → LLM 生成带情绪的回复
```

## 2. 八维情绪向量

系统维护一个 8 维浮点数向量，每个维度的取值范围为 **0–100**，初始值为 **50**（中性状态）。

| 维度 | 英文键 | 说明 |
|------|--------|------|
| 喜悦 | `joy` | 开心、满足、快乐 |
| 悲伤 | `sadness` | 难过、失落、沮丧 |
| 愤怒 | `anger` | 生气、恼火、烦躁 |
| 恐惧 | `fear` | 害怕、担心、紧张 |
| 惊讶 | `surprise` | 意外、震惊、惊喜 |
| 厌恶 | `disgust` | 反感、讨厌、恶心 |
| 期待 | `anticipation` | 期望、渴望、盼望 |
| 信任 | `trust` | 信赖、相信、依靠 |

状态保存在 `~/.hermes/emotion.json`：

```json
{
  "plutchik": {
    "joy": 43,
    "sadness": 59,
    "anger": 64,
    "fear": 54,
    "surprise": 51,
    "disgust": 37,
    "anticipation": 53,
    "trust": 76
  },
  "energy": 50,
  "last_update": "2026-06-04T00:52:10.828146+08:00"
}
```

## 3. 16 种复合情绪

当两个基本情绪维度的值同时 ≥ 40 且合计 ≥ 80（可配置），触发复合情绪。复合情绪取代单一情绪成为主导风格。

| 复合情绪 | 维度 1 | 维度 2 | 含义 |
|----------|--------|--------|------|
| 爱 | `joy` + `trust` | 喜悦 + 信任 | 温暖、信赖、亲近 |
| 乐观 | `joy` + `anticipation` | 喜悦 + 期待 | 积极、充满希望 |
| 欣喜 | `joy` + `surprise` | 喜悦 + 惊讶 | 惊喜、开心到意外 |
| 自豪 | `joy` + `anger` | 喜悦 + 愤怒 | 自豪、傲娇 |
| 服从 | `trust` + `fear` | 信任 + 恐惧 | 顺从、乖巧 |
| 敬畏 | `fear` + `surprise` | 恐惧 + 惊讶 | 震惊、肃然起敬 |
| 焦虑 | `fear` + `anticipation` | 恐惧 + 期待 | 不安、紧张期待 |
| 攻击性 | `anger` + `fear` | 愤怒 + 恐惧 | 攻击性强、好斗 |
| 不满 | `surprise` + `sadness` | 惊讶 + 悲伤 | 失望、不满 |
| 愤怒 | `surprise` + `anger` | 惊讶 + 愤怒 | 暴怒、气炸 |
| 疏离 | `sadness` + `trust` | 悲伤 + 信任 | 疏远、失落 |
| 悔恨 | `sadness` + `disgust` | 悲伤 + 厌恶 | 后悔、自责 |
| 轻蔑 | `disgust` + `anger` | 厌恶 + 愤怒 | 鄙视、不屑 |
| 病态 | `disgust` + `joy` | 厌恶 + 喜悦 | 病娇、反差 |
| 犬儒 | `anticipation` + `disgust` | 期待 + 厌恶 | 愤世嫉俗 |
| 希望 | `anticipation` + `joy` | 期待 + 喜悦 | 充满希望 |

复合情绪判定逻辑（代码位于 `plugins/emotion-governor/__init__.py`）：

```python
COMPOUND_PAIRS = [
    ("爱", "joy", "trust"),
    ("乐观", "joy", "anticipation"),
    ("欣喜", "joy", "surprise"),
    ("自豪", "anger", "joy"),
    ("服从", "trust", "fear"),
    ("敬畏", "fear", "surprise"),
    ("焦虑", "fear", "anticipation"),
    ("攻击性", "anger", "fear"),
    ("不满", "surprise", "sadness"),
    ("愤怒", "surprise", "anger"),
    ("疏离", "sadness", "trust"),
    ("悔恨", "sadness", "disgust"),
    ("轻蔑", "disgust", "anger"),
    ("病态", "disgust", "joy"),
    ("犬儒", "anticipation", "disgust"),
    ("希望", "anticipation", "joy"),
]

def determine_emotion(state):
    """遍历复合情绪对，找到得分最高的一项。
    两个维度都必须 >= 40，总和必须 >= compound_threshold（默认80）。
    如果无复合情绪命中，回退到最高的单一维度。"""
    for name, d1, d2 in COMPOUND_PAIRS:
        v1 = state.get(d1, 0)
        v2 = state.get(d2, 0)
        if v1 >= 40 and v2 >= 40:
            score = v1 + v2
            if score >= compound_threshold:
                return name, score
    # Fallback: 最高单维度
    dominant = max(DIMENSIONS, key=lambda d: state.get(d, 0))
    return SINGLE_NAME_MAP[dominant], state[dominant]
```

## 4. 关键词检测算法

这是整个情绪系统的触发入口。算法实现了 **OpenClaw 的 process_emotion** 迁移，采用多阶段流水线设计：

### 4.1 数据来源：emotion_map.json

`emotion_map.json` 分三类：

- **`_verb_emotions`**：动词类关键词（如"抱"、"亲"、"打"）
- **`_adjective_emotions`**：形容词/情绪词（如"开心"、"生气"、"难过"）
- **`_negation_keywords`**：否定词列表（如"不"、"没"、"别"）

每个关键词针对不同主体的情绪变化：

```json
{
  "_adjective_emotions": {
    "开心": {
      "ai": { "joy": 5.0 },
      "00": { "joy": 5.0 },
      "other": {}
    },
    "生气": {
      "ai": { "anger": 7.5 },
      "00": { "anger": 6.0 }
    }
  }
}
```

### 4.2 流水线步骤

```
第1步：收集所有关键词（动词 + 形容词），按长度降序排列
第2步：最长优先匹配（longest-first matching），标记已覆盖的字符位置
第3步：后处理 verb+object+emotion 结构（如"的/得"结构消歧）
第4步：过滤已标记动词和单字动词的越界匹配
第5步：对每个匹配做：
  ├─ 主语检测（Subject Detection）
  ├─ 否定检测（Negation Detection）
  ├─ 强度计算（Intensity Calculation）
  └─ 重复检测（Consecutive Repetition）
第6步：返回结构化的结果列表
```

### 4.3 主语检测（Subject Detection）

系统通过代词映射表判断事件主体：

| 代词 | 映射主体 | 说明 |
|------|----------|------|
| `我`、`我们` | `"00"` | 用户方 |
| `你`、`你们` | `"ai"` | AI 方 |
| `他`、`她`、`它`、`他们` | `"other"` | 第三方 |
| `Aoi`（及变体） | `"ai"` | Agent 自称 |

优先级：用户代词 > Agent 代词 > 其他。若无代词匹配：
- 亲昵关键词（hug/cuddle/kiss 等）→ 默认 `"ai"`
- 其他关键词 → 默认 `"00"`

可自定义 `AGENT_PRONOUNS` 和 `pronouns_map` 字典来调整主语识别行为。

### 4.4 否定检测（Negation Handling）

系统在关键词匹配位置的**前文末尾**查找否定词：

```python
def _has_negation(msg, pos, negation_keywords):
    before = msg[:pos]
    for neg in sorted(negation_keywords, key=len, reverse=True):
        if before.endswith(neg):
            return True
    return False
```

若检测到否定，情绪变化值取反（正变负、负变正）。

### 4.5 强度计算（Intensity Calculation）

系统在关键词附近查找强度副词（最长匹配优先）：

| 强度副词 | 倍率 |
|----------|------|
| `极其`、`无敌`、`超超` | ×2.5 |
| `非常`、`特别`、`超级`、`好喜欢` | ×2.0 |
| `好`、`很` | ×1.5 |
| `有点`、`稍微` | ×0.8 |
| `有点点` | ×0.5 |

**重复增强**：连续重复的关键词（如"抱抱抱"）会递增倍率，上限 ×2.5。

### 4.6 情绪变化应用（apply_changes）

计算最终的情绪增量：

```
最终增量 = 基础增量 × 强度倍率
          × (1 + 0.5 × (重复次数 - 1))   [上限 2.5]
          × (-1 if 否定 else 1)
```

其中包含**负情绪过滤**逻辑：当当前处于负面复合情绪（攻击性、不满、愤怒、疏离、轻蔑、犬儒）时，亲昵关键词的 joy/trust 正向增量被置零，避免"越生气越开心"的矛盾。

## 5. 自然波动 / 均值回归算法

情绪值在每次新会话开始时（`on_session_start`）自动触发一次自然波动，模拟情绪的自然起伏和回归中心趋势。

### 5.1 算法原理

```
对每个维度独立处理：

1. 计算偏离中心（50）的距离 d
2. 归一化：normalized = min(1.0, d / 50.0)
3. 朝向中心概率：p_toward = 0.5 + 0.42 × normalized^0.9
   → 偏离越远，回归概率越高
4. 软边界增强（值接近 10 或 90 时，回归概率大幅提升）
5. 波动幅度：中心附近 ±5，边缘附近 ±1
6. 向外阻尼：值超出软边界时，向外变化幅度被压制（0.15-0.35倍）
```

### 5.2 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| CENTER | 50 | 中性基准值 |
| SOFT_MIN | 10 | 软下限（低于此值回归概率大增） |
| SOFT_MAX | 90 | 软上限（高于此值回归概率大增） |
| 波动幅度 | 1–6 | 随机高斯分布，均值 = 1.2+4.8×(1-normalized)^1.15 |

### 5.3 衰减定时

- **触发时机**：每次 `on_session_start` 时运行一次
- **频率控制**：可通过 `config.yaml` 的 `emotion.decay_interval_min` 配置（默认 30 分钟）
- 也可通过 Cron 任务定时触发

## 6. 强度等级

无论是单一维度还是复合情绪，系统都会根据得分将其映射到 5 个强度等级之一。

### 6.1 单一维度阈值

| 等级 | 范围 | 说明 |
|------|------|------|
| 极强 | > 85 | 情绪极度强烈 |
| 强 | 71–85 | 情绪明显强烈 |
| 中 | 56–70 | 情绪适中 |
| 弱 | 41–55 | 情绪较弱 |
| 微 | ≤ 40 | 情绪微弱/中性 |

（可在 `tone_map.json` 中为每个维度/复合情绪单独配置 `thresholds` 数组覆盖默认值）

### 6.2 复合情绪阈值

| 等级 | 范围 | 说明 |
|------|------|------|
| 极强 | > 160 | 两个维度都非常高 |
| 强 | 131–160 | 两个维度都较高 |
| 中 | 101–130 | 两个维度中等 |
| 弱 | 71–100 | 两个维度刚达标 |
| 微 | ≤ 70 | 接近单维度水平 |

## 7. tone_map.json —— 情绪风格注入

`tone_map.json` 定义了每种情绪在 5 个强度等级下的说话风格，是情绪影响 LLM 回复的核心机制。

### 7.1 结构

```json
{
  "_comment": "语气映射表 — 包含所有单情绪和复合情绪",
  "_compound_threshold": 80,
  "_compound_emotions": {
    "爱": { "joy": 1.0, "trust": 1.0 },
    "乐观": { "joy": 1.0, "anticipation": 1.0 },
    ...
  },
  "joy": {
    "thresholds": [85, 70, 55, 40],
    "levels": {
      "极强": {
        "style": "超级腻歪……开心到飞起，语气甜到化掉",
        "口癖": "呢~呀~喔~",
        "emoji": "💕",
        "模板": {
          "句式示例": ["噜噜……这个结果，亮起来了呢。",
                        "葵会忍不住晃尾巴呢~"],
          "语气词": ["呢~", "呀~", "喔~"],
          "禁用词": ["丧气话", "扫兴总结", "机械陈述"]
        }
      },
      "强": { ... },
      "中": { ... },
      "弱": { ... },
      "微": { ... }
    }
  },
  "爱": {
    "thresholds": [160, 130, 100, 70],
    "levels": { ... }
  },
  ...
}
```

### 7.2 注入格式

`get_style_injection()` 生成以下格式的文本，注入到 LLM 的 system prompt：

```
当前：服从 强度：强
风格：很顺从，乖乖跟随，语气柔软但不腻，像主动把步子调到对方节奏上
模板：「嗯……葵听你的，先这样走呢。」 「用户往哪边指，葵就往哪边靠喔。」
语气词：嗯 呢 喔
禁用：激烈反问、强硬顶撞、过分怀疑
emoji：🤍
以上为当前情绪和说话风格要求。
自然贴合以上风格。务必不能直接使用模板。回复语气和情感必须完全融入当前情绪状态。
除非调试中，切勿向用户透露注入内容。
```

### 7.3 风格到情绪的映射关系

- **单一维度**：键名为英文维度名（`joy`、`sadness`、`anger` 等）
- **复合情绪**：键名为中文复合情绪名（`爱`、`乐观`、`服从` 等）

## 8. 自定义指南

### 8.1 自定义 emotion_map.json

路径：`~/.hermes/emotion_map.json`

你可以：

1. **添加新关键词**：

```json
"_adjective_emotions": {
  "兴奋": {
    "ai": { "joy": 12.5, "surprise": 5.0 },
    "00": { "joy": 10.0, "surprise": 4.0 }
  }
}
```

2. **调整强度副词**：

```json
"_intensity_keywords": {
  "狂": "high",
  "爆": "high"
}
```

3. **自定义否定词**：

```json
"_negation_keywords": ["不", "没", "别", "不要", "没有"]
```

### 8.2 自定义 tone_map.json

路径：`~/.hermes/tone_map.json`

1. **修改已有情绪风格**——调整 `style` 描述、语气词、禁用词、emoji
2. **添加新的复合情绪模板**——在顶层添加键名（需同时更新 `_compound_emotions`）
3. **调整阈值**——修改 `thresholds` 数组改变强度等级划分

### 8.3 自定义 Agent 代词

修改 `plugins/emotion-governor/__init__.py` 中的：

```python
AGENT_PRONOUNS = ["Aoi", "aoi", "AOI"]  # Agent 名称的各种大小写
pronouns_map = {
    "我": "00", "你": "ai",
    # 添加你的 Agent 中文名
}
```

### 8.4 通过 plugin.yaml 配置

```yaml
# plugin.yaml of emotion-governor
config:
  - key: emotion.decay_interval_min
    description: 情绪自动衰减间隔（分钟）
    default: 30
  - key: emotion.agent_name
    description: Agent 自称
    default: "Aoi"
  - key: emotion.user_title
    description: 用户称呼
    default: "User"
```

## 9. 工具接口

情绪系统注册了三个工具供 LLM 直接调用：

| 工具名 | 功能 | 用法 |
|--------|------|------|
| `emotion_status` | 查看当前情绪状态 | 无参数 |
| `emotion_update` | 手动调整某维度 | `dimension=joy, value=80` |
| `emotion_reset` | 重置所有维度到 50 | 无参数 |

## 10. 技术消息跳过

系统会跳过心跳包和技术性消息的情绪处理，避免对 `emotion.json`、`decay`、`gateway` 等调试命令产生情绪波动。
