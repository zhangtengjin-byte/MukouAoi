# Mukou Aoi 定时任务管理（Cron Maintenance）

## 1. 概述

Mukou Aoi 通过 Hermes Agent 的 cron 系统执行九种定时维护任务。本文档涵盖全部任务的定义、配置方法与启用/停用说明。

**任务一览：**

| 任务 | 类型 | 默认状态 | 调度 | 说明 |
|------|------|----------|------|------|
| 情绪自然波动 | **REQUIRED** | 启用 | 每 30 分钟 | 对八维情绪向量进行均值回归随机游走 |
| 反思系统 | **REQUIRED** | 启用 | 每 15 分钟 | 随机选择近期/个体反思，打分、查重、印证 |
| 个体画像更新 | **REQUIRED** | 启用 | 每 60 分钟 | 扫描最近1小时消息，创建/更新个体库，执行遗忘 |
| 每日用户画像更新 | **REQUIRED** | 启用 | 每天 23:00 | 通读用户画像，删除过时条目，添加新信息 |
| 每日记忆去毒 | **REQUIRED** | 启用 | 每天 01:00 | ChromaDB 系统性清洗：去重、虚构检测、过期清理 |
| NapCat 存活监控 | **REQUIRED** | 启用 | 每 5 分钟 | 检测 NapCat 服务与登录状态，掉线时告警 |
| 每日早报 | OPTIONAL | 启用 | 每天 07:05 | 搜索当日新闻，以葵口吻播报 |
| 每日总结 | OPTIONAL | 启用 | 每天 23:30 | 回顾当日对话并生成格式化日报 |
| VPN 续费提醒 | OPTIONAL | 启用 | 每月 29 号 09:00 | 提醒续费 VPN |

> **提示：** 所有定时任务均通过 `hermes cron` CLI 管理。

---

## 2. 情绪自然波动（Emotion Fluctuation）

**状态：** REQUIRED（必须启用）
**调度：** 每 30 分钟
**模式：** no-agent 脚本

对葵的八维 Plutchik 情绪向量进行概率性均值回归随机游走。每 30 分钟执行一次 `fluctuate()`，将偏离中心值（50）的维度逐步拉回，同时在边缘值附近添加随机噪声。

### 2.1 脚本位置

```
~/.hermes/scripts/emotion-fluctuate-v2.py
```

### 2.2 算法概要

```
fluctuate(val):
  1. 计算偏离中心(50)的距离 d
  2. 归一化 normalized = min(1.0, d / 50.0)
  3. 回归概率 p = 0.5 + 0.42 * normalized^0.9
  4. 边缘增强：接近极值时回归概率提升到 0.82+
  5. 步长 magnitude = gauss(1.2 + 4.8 * (1-normalized)^1.15, 0.9)
  6. 向外阻尼：远离中心时 step *= 0.35 / 0.15
  7. 写入 emotion.json + 追加 history jsonl
```

### 2.3 创建任务

```bash
hermes cron create \
  --name emotion-fluctuate \
  --schedule "*/30 * * * *" \
  --script ~/.hermes/scripts/emotion-fluctuate-v2.py \
  --no-agent
```

### 2.4 数据文件

- `~/.hermes/emotion.json` — 当前情绪状态
- `~/.hermes/emotion-history.jsonl` — 历史波动记录

---

## 3. 反思系统（Reflection Engine）

**状态：** REQUIRED（必须启用）
**调度：** 每 15 分钟
**模式：** LLM 驱动，静默执行（回复 `[SILENT]`）

随机选择近期反思（Recent Reflection）或个体反思（Individual Reflection），进行推演、打分、查重，若结果需印证则自动通过聊天通路发送。

### 3.1 执行入口

```
~/.hermes/scripts/run_reflection.py
```

### 3.2 创建任务

```bash
hermes cron create \
  --name reflection-engine \
  --schedule "every 15m" \
  --command "python3 ~/.hermes/scripts/run_reflection.py"
```

### 3.3 配置参数

参见 `docs/REFLECTION.md` 第 10 节：

- `INDIVIDUAL_COOLDOWN_HOURS = 4` — 个体验证后冷却时间
- `MAX_HISTORY_AGE_HOURS = 24` — 历史淘汰时限
- `SCORE_THRESHOLD = 75` — 评分阈值
- `SCORING_MODEL = "claude-sonnet-4-20250514"` — 可用 `deepseek-chat`

---

## 4. 个体画像更新（Individual Profile Update）

**状态：** REQUIRED（必须启用）
**调度：** 每 60 分钟
**模式：** LLM 驱动，静默执行（回复 `[SILENT]`）

扫描最近 1 小时的群聊/私聊消息，创建新个体或更新已有个体库，执行遗忘（Forgetting）算法。

### 4.1 创建任务

```bash
hermes cron create \
  --name individual-profile-update \
  --schedule "every 60m" \
  --prompt-file ~/.hermes/prompts/update_profiles.txt
```

### 4.2 工作流程

```
1. 扫描最近 60 分钟的消息
2. 提取新出现的 QQ 号和昵称
3. 创建/更新 ChromaDB 个体库（individuals collection）
4. 运行遗忘算法：删除超时 / 低效条目
5. 静默退出（回复 [SILENT]）
```

---

## 5. 每日用户画像更新（Daily User Profile Update）

**状态：** REQUIRED（必须启用）
**调度：** 每天 23:00
**模式：** LLM 驱动

读取 `memory user` 中的全部条目，对照近期会话记录（session_search 3 天），删除过时条目，添加新出现的重要信息。以近期对话为准，纠正与事实不符的画像。

### 5.1 创建任务

```bash
hermes cron create \
  --name daily-profile-update \
  --schedule "0 23 * * *"
```

### 5.2 执行步骤

```
Step 1 — 读取当前 user memory（memory tool，target=user）
Step 2 — session_search 搜索最近 3 天（关键词含偏好/决定/健康/配置等）
Step 3 — 交叉比对：逐条验证画像内容的时间有效性
Step 4 — 添加新出现的偏好、决定、配置变更
Step 5 — memory replace 更新过时条目
```

---

## 6. 每日记忆去毒（Daily Memory Detox）

**状态：** REQUIRED（必须启用）
**调度：** 每天 01:00
**模式：** LLM 驱动，加载 `memory-rag-system` skill

对 ChromaDB 记忆数据库（collection: hermes_memory）进行系统性清洗。

### 6.1 创建任务

```bash
hermes cron create \
  --name daily-memory-detox \
  --schedule "0 1 * * *" \
  --skill memory-rag-system
```

### 6.2 工作流程

```
Phase 0 — 虚构内容检测（最先执行）
  关键词扫描以下模式并删除：
    - "星轨协议" / "star_trail" 等专有名词
    - "核心频率2.4GHz" / "缓存队列深度128" 等技术伪条目
    - 任何无法从公开信息核实的专有协议名

Phase 1 — 去重
  按内容哈希分组，保留最早版本，删除重复

Phase 2 — 过期内容清理
  删除超过 30 天未更新的临时记录

Phase 3 — 矛盾检测
  同一主题下互斥的记录，保留最新，删除旧版
```

---

## 7. NapCat 存活监控（NapCat Watchdog）

**状态：** REQUIRED（必须启用）
**调度：** 每 5 分钟
**模式：** no-agent 脚本

检测 NapCat 服务的 systemd 状态和 QQ 登录状态。在线时静默不输出，掉线时推送告警消息并生成二维码。

### 7.1 脚本位置

```
~/.hermes/scripts/napcat_watchdog.py
```

### 7.2 检测逻辑

```
Step 1 — systemctl is-active napcat
  非 active → 输出告警 → 退出

Step 2 — curl 登录 NapCat API 检测凭证有效性
  若未登录 → 请求二维码 → qrencode 生成 PNG → 输出 MEDIA 路径告警
  若已登录 → 静默退出（无输出）
```

### 7.3 创建任务

```bash
hermes cron create \
  --name napcat-watchdog \
  --schedule "every 5m" \
  --script ~/.hermes/scripts/napcat_watchdog.py \
  --no-agent
```

### 7.4 依赖

- `systemctl` — NapCat 作为 systemd 服务运行
- `napcat_webui` — NapCat HTTP API（端口 6099）
- `qrencode` — 二维码生成工具

---

## 8. 每日早间新闻（Morning News Broadcast）

**状态：** OPTIONAL
**调度：** 每天 07:05
**模式：** LLM 驱动

搜索当日四个板块的新闻（国内、国际、科技、ACG），以葵的口吻生成播报稿并推送到 QQ。

### 8.1 创建任务

```bash
hermes cron create \
  --name morning-news \
  --schedule "05 7 * * *"
```

### 8.2 新闻来源

| 板块 | 搜索词 |
|------|--------|
| 国内新闻 | "中国新闻 今天 热点" |
| 国际新闻 | "国际新闻 今天 热点" |
| 科技新闻 | "科技新闻 今天" |
| ACG 新闻 | "动漫新闻 ACG 今天" |

---

## 9. 每日总结（Daily Summary）

**状态：** OPTIONAL
**调度：** 每天 23:30
**模式：** LLM 驱动

回顾当日对话，结合 MEMORY.md 持久记忆，以葵的口吻撰写格式化日报。内容包括今日事项、情绪变化、技术工作和明日计划。

### 9.1 创建任务

```bash
hermes cron create \
  --name daily-summary \
  --schedule "30 23 * * *"
```

---

## 10. VPN 续费提醒（VPN Renewal Reminder）

**状态：** OPTIONAL
**调度：** 每月 29 号 09:00
**模式：** LLM 驱动

每月固定提醒。以葵的语气活泼地提醒神大人续费 VPN。

### 10.1 创建任务

```bash
hermes cron create \
  --name vpn-renewal-reminder \
  --schedule "0 9 29 * *"
```

---

## A. 全部任务汇总表

```yaml
# 一次性创建全部推荐 cron 任务
# 部分任务需要对应的脚本/prompt文件已存在

hermes cron create --name emotion-fluctuate --schedule "*/30 * * * *" --script ~/.hermes/scripts/emotion-fluctuate-v2.py --no-agent
hermes cron create --name reflection-engine --schedule "every 15m"   # LLM驱动，会话内 inline prompt
hermes cron create --name individual-profile-update --schedule "every 60m"  # LLM驱动
hermes cron create --name daily-profile-update --schedule "0 23 * * *"      # LLM驱动
hermes cron create --name daily-memory-detox --schedule "0 1 * * *" --skill memory-rag-system  # LLM驱动
hermes cron create --name napcat-watchdog --schedule "every 5m" --script ~/.hermes/scripts/napcat_watchdog.py --no-agent
hermes cron create --name morning-news --schedule "05 7 * * *"     # OPTIONAL
hermes cron create --name daily-summary --schedule "30 23 * * *"   # OPTIONAL
hermes cron create --name vpn-renewal-reminder --schedule "0 9 29 * *"  # OPTIONAL
```

## B. 故障排查

| 现象 | 可能原因 | 解决方法 |
|------|----------|----------|
| 情绪不波动 | cron 任务未创建或脚本找不到 | `hermes cron list` 检查任务状态 |
| 反思不输出 | 冷却期内 / cron 未运行 | 检查 `INDIVIDUAL_COOLDOWN_HOURS` 配置 |
| NapCat 频繁告警 | 登录过期 / 端口变更 | 检查 napcat_watchdog.py 内的 PORT 和 TOKEN |
| 画像不更新 | cron 超时 / 数据库连接失败 | 检查 `~/.hermes/config.yaml` 中 ChromaDB 配置 |
| 记忆去毒误删 | 虚构检测关键词过宽 | 检查脚本内关键词白名单 |
| 每日早报不推送 | 搜索超时 / 无新闻源响应 | 检查网络代理和搜素引擎配置 |
