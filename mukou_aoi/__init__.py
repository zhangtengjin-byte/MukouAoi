"""
Mukou Aoi — Hermes Agent 人格化引擎套件

为 Hermes Agent 提供完整的人格化能力：
  - emotion-governor：八维情绪向量 + 关键词触发 + 复合情绪 + 自然波动 + 风格注入
  - mode-switch：@work/@life 模式切换 + 字数限制
  - 记忆 RAG 系统（ChromaDB + BGE 向量检索）
  - 反思系统（画像更新 + 近期/个体反思 + 打分引擎）
  - QQ 群聊桥接（NapCat + Hermes Webhook）
  - 表情包自动追加系统
"""

__version__ = "1.0.0"
