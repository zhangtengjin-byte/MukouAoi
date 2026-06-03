# Mukou Aoi 记忆 RAG 系统（Memory RAG）

## 1. 概述

记忆 RAG（检索增强生成）系统让葵拥有**长期记忆**能力。它通过向量数据库存储对话摘要，在每次对话前检索最相关历史记忆，注入到 LLM 上下文中，使葵能"记住"过去和用户的互动。

### 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 向量数据库 | ChromaDB | 轻量本地持久化，Python 原生 |
| 嵌入模型 | BAAI/bge-large-zh-v1.5 | 1024 维，中文优化 |
| Embedding API | SiliconFlow（硅基流动） | OpenAI 兼容格式，免费额度 |
| 摘要模型 | DeepSeek Chat | 压缩对话为记忆摘要 |
| Fallback 嵌入 | 无（DeepSeek 不支持嵌入） | 备胎已移除 |

## 2. 系统架构

```
┌──────────────────────────────────────────────────┐
│  Memory RAG (plugin: memory-rag)                  │
│                                                    │
│  pre_llm_call ──────────────────────────────────┐ │
│  │  1. 用户消息 → 存入对话缓冲 (deque, maxlen=15) │ │
│  │  2. 缓冲满 5 轮 → 异步触发摘要+存储           │ │
│  │  3. 用户消息 → Retriever.search() → 向量检索   │ │
│  │  4. Injector.format_memory_block() → 注入      │ │
│  └──────────────────────────────────────────────── │ │
│                                                    │
│  组件：                                            │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │
│  │ Embedder │ │ Store  │ │Retriever│ │ Injector │ │
│  │(Silicon- │ │(Chroma)│ │(检索器)│ │(注入器)  │ │
│  │ Flow     │ │        │ │        │ │          │ │
│  │ BGE)     │ │        │ │        │ │          │ │
│  └──────────┘ └────────┘ └────────┘ └──────────┘ │
└──────────────────────────────────────────────────┘
```

### 2.1 Embedder（嵌入器） — `embedder.py`

**多 Provider 抽象架构**：

```
BaseEmbedder (抽象基类)
  └── SiliconFlowEmbedder (主力)
       — BAAI/bge-large-zh-v1.5 (1024维)
       — API: api.siliconflow.cn/v1/embeddings
       — 自动分批（每批最多 16 条，防 413）
```

`FallbackEmbedder` 封装了自动降级逻辑：
- 先调 SiliconFlow
- 如果 HTTP 429/5xx/超时 → 降级单条重试
- 两次都失败 → 抛异常（**无备胎**，DeepSeek 不支持 embedding）

> **API Key 配置**：通过环境变量 `SILICONFLOW_API_KEY` 设置

### 2.2 Store（向量存储） — `store.py`

**多 Provider 抽象架构**：

```
BaseStore (抽象基类)
  ├── ChromaStore (主力)
  │   — ChromaDB PersistentClient
  │   — 默认路径: ~/.hermes/chroma_db
  │   — 默认 collection: hermes_memory
  │   — 哑 embedding function（阻止下载 79MB ONNX 模型）
  └── QdrantStore (预留，待实现)
```

写入流程：

```python
# store.py 核心写入
def ingest(self, document, metadata=None, doc_id=None):
    meta = metadata.copy() if metadata else {}
    if "timestamp" not in meta:
        meta["timestamp"] = datetime.now(TZ_SHANGHAI).isoformat()

    embedding = self._embedder.embed_single(document)  # ← 外部算向量

    doc_id = doc_id or f"mem_{ts}_{count:06d}"
    self._collection.upsert(
        ids=[doc_id],
        documents=[document],
        metadatas=[meta],
        embeddings=[embedding],  # ← 手动传向量，不做 defualt embedding
    )
    return doc_id
```

### 2.3 Retriever（检索器） — `retriever.py`

```python
class Retriever:
    def __init__(self, top_k=3, similarity_threshold=0.70):
        ...

    def search(self, query, top_k=None, threshold=None):
        # 1. 用户消息 → SiliconFlow embedding
        query_embedding = self._embedder.embed_single(query)
        # 2. ChromaDB 向量相似度搜索
        results = self._store.query(
            query_embeddings=[query_embedding],
            n_results=k,
        )
        # 3. 余弦距离 → 相似度 (distance∈[0,2], sim=1-distance/2)
        # 4. 过滤低于阈值的命中
        # 5. 按相似度降序返回
```

### 2.4 Injector（注入器） — `injector.py`

将检索结果格式化为 LLM context 提示块：

```
══════════════════════════════
记忆检索结果（相关性从高到低）：
══════════════════════════════
【2026-06-03 · 相似度 87%】用户说……葵说……
【2026-06-01 · 相似度 72%】用户决定将情绪系统从……
══════════════════════════════
```

控制参数：
- `max_per_hit=100`：每条记忆最多展示字数
- `max_total=600`：注入总字数上限

### 2.5 Ingester（摘要引擎） — `ingester.py`

使用 DeepSeek Chat 将对话压缩为 200–400 字的记忆摘要：

```python
def summarize_chunk(conversation_turns):
    # 构建 prompt："将以下对话压缩成一段 200-400 字的记忆摘要"
    # 要求保留：关键话题、结论、用户的决策/偏好/情绪、
    #           技术名词、参数、路径
    #           末尾用【关键词】标注 3-5 个搜索词
    # 调用 DeepSeek API，temperature=0.3，max_tokens=300
```

同时提取**重要性评分**（`extract_importance`）和**记忆类型**（`_classify_type`）：

| 类型 | 触发词 | 说明 |
|------|--------|------|
| `preference` | 偏好/喜欢/不吃/讨厌 | 偏好信息 |
| `decision` | 决定/选/以后/换成 | 决策记录 |
| `correction` | 纠正/不是/记错 | 纠正/更新 |
| `conversation` | 默认 | 普通对话 |

## 3. 记忆存储机制

### 3.1 自动分段存储

每积累 **5 轮**（`CHUNK_SIZE=5`）对话，自动触发异步摘要+存储：

```python
def _trigger_chunk_summary(sid):
    buffer = _conversation_buffers[sid]  # deque(maxlen=15)
    if len(buffer) >= CHUNK_SIZE:
        chunk = list(buffer)[-CHUNK_SIZE:]  # 取最后 5 轮
        # 异步线程：summarize_chunk → build_memory_record → store.ingest
        # 完成后清空已处理的 5 轮
```

### 3.2 手动存储（`/remember`）

用户可通过 `/remember` 命令立即将当前对话缓冲压缩存档：

```
/remember 今天讨论了 项目环境 的网络配置
```

### 3.3 删除记忆（`/forget`）

```
/forget mem_20260603_005158_000005    # 按 ID 删除
/forget 项目                       # 按关键词搜索删除第一条
```

### 3.4 统计查询（`/stats` 或 `/记忆`）

查看记忆库总条数等信息。

## 4. 记忆检索与注入流程

```
用户消息 "上次说的 项目 配置怎么样了？"
  │
  ▼
pre_llm_call hook
  │
  ├─ 消息存入对话缓冲
  │
  ├─ 缓冲满 5 轮？→ 异步触发摘要存储（不阻塞回复）
  │
  ├─ 消息长度 ≥ 4 字符？→ 继续，否则跳过
  │
  ├─ 跳过模式匹配：/reset, /model, /new 等命令跳过
  │
  ├─ Retriever.search("上次说的 项目 配置怎么样了？")
  │   ├─ SiliconFlow BGE embedding → 1024维向量
  │   └─ ChromaDB 余弦相似度搜索 → Top-K 结果
  │
  ├─ Injector.format_memory_block(hits)
  │   └─ 格式化为记忆块（含分隔线和相似度）
  │
  └─ 返回 {"context": "记忆块文本"} → 注入 system prompt
```

## 5. 工具接口

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `memory_status` | 查看记忆库状态 | 无参数 |
| `memory_search` | 搜索记忆 | `query`(必填), `top_k`(默认5), `threshold`(默认0.5) |
| `memory_remember` | 手动存入记忆 | `content`(必填), `type`(默认conversation), `importance`(默认0.5) |
| `memory_remember_cmd` | `/remember` 命令处理 | `note`(可选备注) |

## 6. 自定义配置

### 6.1 修改 embedding Provider

编辑 `embedder.py` 中的 API 配置：

```python
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "你的key")
```

可通过环境变量或 `.env` 文件配置。如需更换模型，修改：

```python
class SiliconFlowEmbedder(BaseEmbedder):
    BASE_URL = "https://api.siliconflow.cn/v1"
    MODEL = "BAAI/bge-large-zh-v1.5"  # 可替换为其他模型
```

### 6.2 修改 ChromaDB 路径

```python
# store.py
CHROMA_PATH = os.path.expanduser("~/.hermes/chroma_db")  # 修改路径
COLLECTION_NAME = "hermes_memory"  # 修改集合名
```

### 6.3 修改检索参数

```yaml
# plugin.yaml of memory-rag
config:
  - key: memory_rag.top_k
    default: 5        # 每次检索返回的记忆条数
  - key: memory_rag.similarity_threshold
    default: 0.55     # 相似度阈值 (0-1)
  - key: memory_rag.enabled
    default: true     # 开关
```

或直接修改 `Retriever` 实例化参数：

```python
# retriever.py
_retriever = Retriever(top_k=5, similarity_threshold=0.65)
```

### 6.4 修改自动分段间隔

```python
# __init__.py
CHUNK_SIZE = 5  # 每 N 轮触发一次自动摘要存储
```

### 6.5 切换向量库 Provider

```python
# store.py — 通过 get_store() 切换
store = get_store("chroma")     # ChromaDB（当前主力）
store = get_store("qdrant", host="localhost", port=6333)  # Qdrant（待实现）
```

## 7. 会话 FTS5 搜索

除了 ChromaDB 向量检索，葵还通过 Hermes 内置的 `session_search` 工具使用 **SQLite FTS5** 进行全文搜索：

```yaml
# config.yaml 中的 session_search 配置
auxiliary:
  session_search:
    provider: deepseek
    model: deepseek-v4-pro
    max_concurrency: 2
    timeout: 120
```

FTS5 搜索用于快速查找历史会话中的精确文本匹配，补充向量检索的语义相似度搜索。

## 8. 数据文件

| 文件/目录 | 用途 |
|-----------|------|
| `~/.hermes/chroma_db/` | ChromaDB 持久化数据（向量库） |
| `~/.hermes/emotion_state_history.json` | 情绪变化历史记录 |
| `~/.hermes/sessions/` | Hermes 会话存档（JSON） |
| `~/.hermes/workspace/individuals_db/` | 个体库（独立的 ChromaDB） |
