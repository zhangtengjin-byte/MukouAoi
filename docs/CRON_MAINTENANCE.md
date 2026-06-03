# Mukou Aoi 定时任务管理（Cron Maintenance）

## 1. 概述

Mukou Aoi 通过 Hermes Agent 的 cron 系统执行三种定时维护任务。本文档涵盖配置与启用/停用方法。

**任务一览：**

| 任务 | 类型 | 默认状态 | 建议时间 | 说明 |
|------|------|----------|----------|------|
| 画像定时去毒（Profile Memory Detox） | **REQUIRED** | 启用 | 每天 23:00 | 清理用户画像中的过时信息 |
| 每日早报（Morning News Broadcast） | OPTIONAL | 禁用 | 每天 08:00 | 搜索并推送当日新闻摘要 |
| 每日总结（Daily Summary） | OPTIONAL | 禁用 | 每天 23:30 | 回顾当日对话并生成总结报告 |

> **提示：** 所有定时任务均通过 `hermes cron` CLI 管理。Hermes 的 cron 行为取决于 Hermes Agent 版本，请查阅 Hermes 官方文档确认具体语法。

---

## 2. 画像定时去毒（Profile Memory Detox）

**状态：** ✅ REQUIRED（必须启用）

画像去毒是葵维护用户画像准确性的核心机制。它定期读取 ChromaDB 中的用户画像，比对近期对话记录，识别并移除已过时或矛盾的信息，然后将更新后的画像写回数据库并记录变更日志。

### 2.1 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  Profile Memory Detox                                        │
│                                                              │
│  步骤 1 ── 读取画像                                           │
│    ChromaDB.individuals.get(target_user_id) → profile        │
│    ↓                                                         │
│  步骤 2 ── 提取待验证事实                                      │
│    profile.facts[] → 逐个提取 (key:value) 对                  │
│    ↓                                                         │
│  步骤 3 ── 搜索近期会话进行验证                                 │
│    session_search(target_user, time_window=7d)               │
│    → 检查每条事实是否有矛盾 / 已被新信息取代                    │
│    ↓                                                         │
│  步骤 4 ── 过滤 & 标记                                          │
│    stale_facts[] ← 识别出的过期/矛盾事实                       │
│    kept_facts[] ← 仍有效的事实                                 │
│    ↓                                                         │
│  步骤 5 ── 更新画像并写回                                       │
│    profile.facts = kept_facts                                 │
│    ChromaDB.individuals.update(profile)                      │
│    ↓                                                         │
│  步骤 6 ── 记录变更日志                                        │
│    detox_log.jsonl ← {timestamp, user, removed, reason}      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 创建定时任务

```bash
# 创建画像去毒定时任务 — 每天 23:00 执行
hermes cron create \
  --name profile-detox \
  --schedule "0 23 * * *" \
  --command "python3 ~/MukouAoi/scripts/detox_profiles.py" \
  --description "每日画像去毒：清理用户画像中的过时/矛盾信息"
```

验证创建是否成功：

```bash
# 列出所有 cron 任务
hermes cron list

# 查看特定任务详情
hermes cron show profile-detox
```

### 2.3 任务脚本参考（`detox_profiles.py`）

```python
#!/usr/bin/env python3
"""
画像去毒脚本 — 每日定时执行
读取所有用户画像 → 验证事实有效期 → 移除过时条目 → 写回
"""
import json
import logging
from datetime import datetime, timedelta

# 伪代码示意，具体实现请参考实际源码
def run_detox():
    # 1. 从 ChromaDB 读取所有个体画像
    profiles = chromadb.individuals.get_all()

    for user_id, profile in profiles.items():
        original_count = len(profile.get("facts", []))
        stale_facts = []

        for fact in profile["facts"]:
            # 2. 搜索最近 7 天会话验证该事实
            sessions = session_search(
                user_id=user_id,
                time_window=timedelta(days=7)
            )

            # 3. 判断是否有矛盾证据或已过时
            if is_contradicted(fact, sessions) or is_outdated(fact):
                stale_facts.append(fact)

        # 4. 移除过时事实
        profile["facts"] = [
            f for f in profile["facts"] if f not in stale_facts
        ]

        # 5. 写回数据库
        chromadb.individuals.update(user_id, profile)

        # 6. 记录日志
        if stale_facts:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "removed_count": len(stale_facts),
                "original_count": original_count,
                "new_count": len(profile["facts"]),
                "removed_facts": stale_facts,
                "reason": "contradicted_or_outdated",
            }
            append_log("detox_log.jsonl", log_entry)

if __name__ == "__main__":
    run_detox()
```

### 2.4 查看去毒日志

```bash
# 查看最近去毒记录
tail -n 20 ~/MukouAoi/data/detox_log.jsonl

# 统计某用户累计移除了多少条事实
grep '"user_id":"user_xxx"' ~/MukouAoi/data/detox_log.jsonl \
  | python3 -c "import sys,json; data=[json.loads(l) for l in sys.stdin]; print(sum(d['removed_count'] for d in data))"
```

### 2.5 临时停用 / 恢复

```bash
# 暂停去毒任务（不删除配置）
hermes cron pause profile-detox

# 恢复任务
hermes cron resume profile-detox

# 完全删除任务（谨慎操作）
hermes cron delete profile-detox
```

---

## 3. 每日早报（Morning News Broadcast）

**状态：** ⚠️ OPTIONAL（可选，默认禁用）

每日早报是一个可选功能，在每天早上定时搜索新闻、整理头条、生成简报，然后推送到 QQ 群聊或保存为本地 Markdown 文件。

### 3.1 前置依赖

- SearXNG 实例（或其它可用的 Web Search API）
- QQ 群聊机器人（通过 NapCat Bridge）— **仅推送模式需要**

### 3.2 工作流程

```
┌─────────────────────────────────────────────────────────┐
│  Morning News Broadcast                                  │
│                                                          │
│  搜索新闻 ─── SearXNG / 搜索引擎                            │
│    ↓                                                     │
│  汇总精选 ─── 取 TOP 5~8 条，去重、排序                     │
│    ↓                                                     │
│  LLM 润色 ─── 生成自然语言简报（带摘要 + 来源链接）          │
│    ↓                                                     │
│  输出 ───→ QQ 群推送 | 本地 Markdown 文件                  │
└─────────────────────────────────────────────────────────┘
```

### 3.3 创建定时任务

```bash
# === 方案 A：推送到 QQ ===
hermes cron create \
  --name morning-news \
  --schedule "0 8 * * *" \
  --command "python3 ~/MukouAoi/scripts/morning_news.py --output qq" \
  --description "每日早报：搜索最新新闻并推送到 QQ 群"

# === 方案 B：保存为本地文件 ===
hermes cron create \
  --name morning-news \
  --schedule "0 8 * * *" \
  --command "python3 ~/MukouAoi/scripts/morning_news.py --output markdown --dir ~/daily_news" \
  --description "每日早报：搜索最新新闻并保存为 Markdown"
```

### 3.4 任务脚本参考（`morning_news.py`）

```python
#!/usr/bin/env python3
"""晨间新闻简报 — 搜索、整理、推送"""
import argparse
import json


def fetch_news():
    """通过 SearXNG 或配置的搜索引擎获取新闻"""
    # 调用 SearXNG API 或 Hermes 内置 web_search 技能
    results = web_search(query="今日要闻 热点新闻", top_k=8)
    return results


def curate_news(raw_news):
    """调用 LLM 汇总润色"""
    prompt = f"""从以下新闻中精选 TOP 5 条最重要的，生成中文简报。
每条包含：标题、一句话摘要、来源。
格式：Markdown 列表。"""
    # 调用 LLM 生成
    return llm_generate(prompt, context=raw_news)


def push_to_qq(briefing):
    """通过 NapCat Bridge 发送到 QQ 群"""
    # napcat_bridge.send_group_msg(group_id=..., message=briefing)
    pass


def save_markdown(briefing, output_dir):
    """保存为本地 Markdown 文件"""
    from datetime import date
    path = Path(output_dir) / f"晨间简报_{date.today().isoformat()}.md"
    path.write_text(briefing, encoding="utf-8")
    print(f"已保存: {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=["qq", "markdown"], default="markdown")
    parser.add_argument("--dir", default="~/daily_news")
    args = parser.parse_args()

    raw = fetch_news()
    briefing = curate_news(raw)

    if args.output == "qq":
        push_to_qq(briefing)
    else:
        save_markdown(briefing, args.dir)
```

### 3.5 启用与停用

```bash
# 启用（创建后默认启用）
hermes cron resume morning-news

# 停用
hermes cron pause morning-news

# 手动触发一次测试
hermes cron run morning-news

# 查看下次执行时间
hermes cron show morning-news
```

### 3.6 配置示例（YAML）

如需持久化配置，可在 Hermes 配置目录下创建 `cron_news_config.yaml`：

```yaml
# ~/.hermes/config/cron_news_config.yaml
morning_news:
  enabled: false               # 设为 true 启用
  schedule: "0 8 * * *"        # 每天早上 8:00
  output_mode: "markdown"      # qq | markdown
  output_dir: "~/daily_news"
  search_engine: "searxng"     # searxng | google | bing
  searxng_url: "http://localhost:8888"
  top_k: 8
  language: "zh-CN"
  qq_group_id: "123456789"     # 仅推送模式需要
```

---

## 4. 每日总结（Daily Summary）

**状态：** ⚠️ OPTIONAL（可选，默认禁用）

每日总结在深夜回顾当天所有对话，提取关键话题、重要共识和待办事项，生成总结报告。可保存为 Markdown 文件或推送到 QQ。

### 4.1 工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  Daily Summary                                               │
│                                                              │
│  步骤 1 ── 收集当天对话                                       │
│    → 从 ChromaDB / 会话存档中筛选当日 (00:00~23:59) 记录      │
│    ↓                                                         │
│  步骤 2 ── 按话题聚类                                          │
│    → 主题提取 → 同话题合并 → 排除无意义闲聊                   │
│    ↓                                                         │
│  步骤 3 ── LLM 生成总结                                        │
│    → 每条话题生成：参与人 + 关键结论 + 待办项                  │
│    ↓                                                         │
│  步骤 4 ── 输出                                               │
│    → QQ 群推送 | 保存为 Markdown                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 创建定时任务

```bash
# === 方案 A：推送到 QQ ===
hermes cron create \
  --name daily-summary \
  --schedule "30 23 * * *" \
  --command "python3 ~/MukouAoi/scripts/daily_summary.py --output qq" \
  --description "每日总结：回顾当天对话内容并推送至 QQ"

# === 方案 B：保存为本地文件 ===
hermes cron create \
  --name daily-summary \
  --schedule "30 23 * * *" \
  --command "python3 ~/MukouAoi/scripts/daily_summary.py --output markdown --dir ~/daily_summaries" \
  --description "每日总结：回顾当天对话内容并保存为 Markdown"
```

### 4.3 任务脚本参考（`daily_summary.py`）

```python
#!/usr/bin/env python3
"""每日对话总结 — 收集、聚类、总结"""
import argparse
from datetime import datetime, date
from pathlib import Path


def collect_today_sessions():
    """从 ChromaDB / 会话存档中获取当天的对话记录"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    today_end = datetime.now().replace(hour=23, minute=59, second=59)

    # 搜索 ChromaDB memory collection
    sessions = chromadb.memory.search(
        time_range=(today_start, today_end),
        top_k=200,
    )
    return sessions


def cluster_by_topic(sessions):
    """按话题聚类，识别关键讨论主题"""
    # 提取主题关键词 → 合并 → 排序（按对话量/参与人数）
    pass


def generate_summary(clusters):
    """调用 LLM 生成结构化总结"""
    prompt = """今天是 {today}。以下是今天的对话主题聚类，请生成一份中文总结。

格式要求：
- 每个主题一段
- 包含：参与人、关键结论、待办事项（如有）
- 整体语气简洁自然"""
    return llm_generate(prompt, context=clusters)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", choices=["qq", "markdown"], default="markdown")
    parser.add_argument("--dir", default="~/daily_summaries")
    args = parser.parse_args()

    sessions = collect_today_sessions()
    clusters = cluster_by_topic(sessions)
    summary = generate_summary(clusters)

    if args.output == "qq":
        push_to_qq(summary)
    else:
        save_markdown(summary, args.dir)
```

### 4.4 启用与停用

```bash
# 启用
hermes cron resume daily-summary

# 停用
hermes cron pause daily-summary

# 手动触发
hermes cron run daily-summary

# 查看状态
hermes cron show daily-summary
```

### 4.5 配置示例（YAML）

```yaml
# ~/.hermes/config/cron_summary_config.yaml
daily_summary:
  enabled: false               # 设为 true 启用
  schedule: "30 23 * * *"      # 每晚 23:30
  output_mode: "markdown"      # qq | markdown
  output_dir: "~/daily_summaries"
  timezone: "Asia/Shanghai"
  max_topics: 10               # 最多总结的话题数
  min_topic_length: 3          # 最少对话轮数才视为独立话题
  qq_group_id: "123456789"     # 仅推送模式需要
```

---

## 5. 综合管理

### 5.1 任务一览

```bash
# 列出所有 cron 任务
hermes cron list

# 输出示例：
# profile-detox   │ 0 23 * * *   │ 每天 23:00  │ 画像定时去毒      │ ACTIVE
# morning-news    │ 0 8 * * *    │ 每天 08:00  │ 每日早报（可选）  │ PAUSED
# daily-summary   │ 30 23 * * *  │ 每天 23:30  │ 每日总结（可选）  │ PAUSED
```

### 5.2 批量管理

```bash
# 一键停用所有可选任务（保留画像去毒）
hermes cron pause morning-news
hermes cron pause daily-summary

# 一键启用所有可选任务
hermes cron resume morning-news
hermes cron resume daily-summary

# 查看任务执行日志
tail -f ~/.hermes/logs/cron.log
```

### 5.3 时间与排期

建议所有定时任务使用东八区（Asia/Shanghai）：

```bash
# 可通过 Hermes 配置文件设置时区
# ~/.hermes/config/hermes.yaml
# timezone: "Asia/Shanghai"

# 查看当前 Hermes 时区
hermes config get timezone
```

| 任务 | Cron 表达式 | 说明 | 与其它任务间隔 |
|------|-------------|------|---------------|
| 画像去毒 | `0 23 * * *` | 23:00 | — |
| 每日早报 | `0 8 * * *` | 08:00 | 与总结相隔 > 15h |
| 每日总结 | `30 23 * * *` | 23:30 | 去毒完成 30 min 后 |

---

## 6. 故障排查

### 6.1 常见问题

| 问题 | 可能原因 | 解决 |
|------|----------|------|
| cron 任务未执行 | Hermes 未运行 | 检查 `hermes status`，确保 agent 在线 |
| 画像去毒报错 | ChromaDB 连接失败 | 检查 ~/.hermes/chroma_db 权限与磁盘空间 |
| 早报无新闻 | SearXNG 未配置 / 不可用 | 检查搜素引擎配置，`curl http://localhost:8888` 测试 |
| 总结为空 | 当天无有效对话 | 这是正常行为，日志中会记录 `no_sessions_today` |

### 6.2 查看日志

```bash
# 查看所有 cron 执行日志
tail -n 50 ~/.hermes/logs/cron.log

# 按任务名过滤
grep 'profile-detox' ~/.hermes/logs/cron.log

# 按日期过滤
grep '2026-06-04' ~/.hermes/logs/cron.log
```

### 6.3 手动调试

```bash
# 模拟画像去毒执行（不写库，仅输出差异预览）
python3 ~/MukouAoi/scripts/detox_profiles.py --dry-run

# 手动生成早报（不推送，仅输出到终端）
python3 ~/MukouAoi/scripts/morning_news.py --dry-run

# 手动生成总结（不推送，仅输出到终端）
python3 ~/MukouAoi/scripts/daily_summary.py --dry-run
```

---

## 7. 与葵其它系统的关系

```
          ┌──────────────────┐
          │   Emotion System  │  ← 定时任务执行结果会影响情绪状态
          └────────┬─────────┘
                   │
┌──────────────────┼──────────────────┐
│  Cron Tasks       │                   │
│  ┌──────────────┐│                   │
│  │ Profile      │├── 读写 ──→ ChromaDB (Individuals)
│  │ Detox        ││                   │
│  ├──────────────┤│                   │
│  │ Morning News │├── 推送 ──→ NapCat Bridge → QQ 群
│  ├──────────────┤│                   │
│  │ Daily        │├── 读取 ──→ ChromaDB (Memory)
│  │ Summary      │├── 推送 ──→ NapCat Bridge → QQ 群
│  └──────────────┘│                   │
└──────────────────┴──────────────────┘
                   │
          ┌────────▼─────────┐
          │   Reflection     │  ← 每日总结的素材也可能进入反思系统
          └──────────────────┘
```

---

## 附录 A：快速参考 — 完整配置命令一览

```bash
#!/bin/bash
# 一键部署所有 cron 任务（按需选择）

# === REQUIRED：画像去毒 ===
hermes cron create \
  --name profile-detox \
  --schedule "0 23 * * *" \
  --command "python3 ~/MukouAoi/scripts/detox_profiles.py" \
  --description "每日画像去毒"

# === OPTIONAL：每日早报（推送到 QQ） ===
hermes cron create \
  --name morning-news \
  --schedule "0 8 * * *" \
  --command "python3 ~/MukouAoi/scripts/morning_news.py --output qq" \
  --description "每日早报"

# === OPTIONAL：每日总结（推送到 QQ） ===
hermes cron create \
  --name daily-summary \
  --schedule "30 23 * * *" \
  --command "python3 ~/MukouAoi/scripts/daily_summary.py --output qq" \
  --description "每日总结"
```
