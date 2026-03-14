# CLAUDE.md — Paper Radar 项目构建说明

本文件供 Claude Code 阅读，用于从零搭建 Paper Radar 项目。请严格按照本文件的架构、技术栈和规范进行构建。

---

## 项目定位

Paper Radar 是一个**迭代式顶会论文追踪与研究洞察生成系统**。

用户输入一个研究主题（如「强化学习」），系统自动：
1. 从 arXiv + Semantic Scholar 采集近期**顶会/顶刊论文**以及 **arXiv 高增速论文**
2. 支持用户手动指定额外论文（arXiv ID 或本地 PDF）
3. 下载 PDF 并提取关键段落
4. 调用 Claude API 结构化解析每篇论文
5. 对论文做向量化聚类，识别子方向
6. 生成趋势分析、领域盲区、研究 Idea
7. 用户选定感兴趣的 Idea 后，系统定向补充搜索并深化该 Idea
8. 输出 Markdown 报告并自动 push 到 GitHub
9. 同时提供交互式 Web UI

---

## 目录结构（必须严格遵守）

```
paper-radar/
│
├── CLAUDE.md                        # 本文件
├── README.md                        # 用户使用文档（见下方规范）
├── config.yaml                      # 用户配置文件
├── prompts.yaml                     # 所有 Claude Prompt 模板（透明公开）
├── requirements.txt                 # Python 依赖
├── run.py                           # 一键入口
│
├── pipeline/
│   ├── __init__.py
│   ├── collector.py                 # 第一阶段：论文采集（顶会过滤 + 高增速过滤）
│   ├── downloader.py                # 第二阶段：PDF 下载与段落提取
│   ├── extractor.py                 # 第三阶段：Claude 结构化解析
│   ├── embedder.py                  # 第四阶段：向量化与聚类
│   ├── analyst.py                   # 第五阶段：趋势分析、盲区发现、Idea 生成
│   └── refiner.py                   # 第六阶段：Idea 定向搜索与深化
│
├── storage/
│   ├── papers.db                    # SQLite 数据库（运行时生成）
│   ├── pdfs/                        # 下载的 PDF 文件（运行时生成）
│   └── vectors/                     # ChromaDB 向量索引（运行时生成）
│
├── output/
│   └── reports/                     # 生成的 Markdown 报告（运行时生成）
│
├── web/
│   ├── app.py                       # FastAPI 后端
│   ├── requirements-web.txt         # Web 额外依赖
│   └── frontend/
│       ├── package.json
│       ├── vite.config.js
│       ├── src/
│       │   ├── App.jsx
│       │   ├── pages/
│       │   │   ├── Dashboard.jsx    # 主面板：输入 + 手动论文 + pipeline 进度
│       │   │   ├── Overview.jsx     # 全景图：UMAP 散点图 + 热力图
│       │   │   ├── Report.jsx       # 报告页：趋势 + 盲区 + Idea 卡片
│       │   │   └── IdeaRefine.jsx   # Idea 深化页：选择 Idea + 深化报告
│       │   └── components/
│       │       ├── PaperCard.jsx
│       │       ├── ClusterMap.jsx   # UMAP 交互散点图（D3.js）
│       │       └── ProgressLog.jsx  # 实时进度（SSE）
│       └── public/
│
└── scripts/
    └── git_push.py                  # 自动 git commit + push 到报告 repo
```

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 采集 | `arxiv` + `requests` | arXiv Python 库 + Semantic Scholar REST API |
| PDF 解析 | `pymupdf`（fitz） | 段落识别，不使用 pdfplumber |
| LLM 解析 | `anthropic` SDK | Haiku 做结构化解析，Sonnet 做趋势分析与深化 |
| 向量化 | `openai` embedding 或 `sentence-transformers` | text-embedding-3-small 优先 |
| 聚类 | `umap-learn` + `hdbscan` | 不使用 KMeans |
| 向量存储 | `chromadb` | 本地持久化 |
| 关系存储 | `sqlite3`（标准库） | 不引入 ORM |
| Git 自动化 | `gitpython` | 自动 commit + push |
| 后端 | `fastapi` + `uvicorn` | SSE 推送 pipeline 进度 |
| 前端 | React + D3.js | 使用 Vite 构建 |

---

## 论文采集策略（核心设计）

系统采集两类论文，通过以下任意一个条件的论文均进入后续 pipeline：

### 条件一：顶会顶刊论文
- 通过 Semantic Scholar API 查询论文的 `venue` 字段
- 与 `config.yaml` 中 `venues` 白名单做匹配（大小写不敏感，支持部分匹配）
- 匹配成功即保留，不设引用数门槛（顶会新论文引用可能为 0）

### 条件二：arXiv 高增速论文
- 针对近 180 天内发布的 arXiv 论文
- 计算归一化引用速度：
  ```
  citation_velocity = citationCount / max(days_since_published, 30)
  ```
- `citation_velocity >= config.collection.citation_velocity_threshold`（默认 0.5）则保留
- 此条件专门捕获「尚未发顶会但已在社区爆发」的论文

### 条件三：手动指定论文
- 用户通过 CLI 参数 `--papers arxiv_id1,arxiv_id2` 或 Web UI 上传指定
- 直接跳过采集阶段，进入 downloader
- 在 `papers` 表中标记 `source = 'manual'`，不受任何过滤条件限制

**过滤流程：**
```
arXiv 关键词搜索（宽泛拉取）
          ↓
Semantic Scholar 批量查询（venue + citationCount + publicationDate）
          ↓
    并行判断两个条件：
    ├── venue 在顶会白名单 → 保留（passed_by = 'venue'）
    └── citation_velocity >= 阈值 且 days_since_published <= 180 → 保留（passed_by = 'velocity'）
          ↓
手动指定论文直接合并（passed_by = 'manual'）
          ↓
去重（按 arXiv ID）
          ↓
写入 SQLite papers 表
```

---

## 各模块实现规范

### pipeline/collector.py

**职责**：采集论文，过滤出顶会论文和高增速论文。

**流程**：
1. 读取 `config.yaml` 中的主题、时间窗口、过滤阈值
2. 调用 `prompts.yaml` 中的 `keyword_expansion` Prompt，让 Claude 扩展关键词列表，同时返回 `venues_category` 用于自动选择顶会白名单
3. 用扩展后的关键词并发查询 arXiv API
4. 对每篇论文查询 Semantic Scholar API，获取 `venue`、`citationCount`、`publicationDate`
5. 按采集策略过滤（顶会 OR 高增速）
6. 如有 `--papers` 参数，合并手动指定论文
7. 将结果写入 SQLite `papers` 表

**Semantic Scholar 批量查询 endpoint**：
```
GET https://api.semanticscholar.org/graph/v1/paper/search
  ?query={title}
  &fields=venue,citationCount,influentialCitationCount,publicationDate,externalIds
```

**citation_velocity 计算代码示例**：
```python
from datetime import datetime

def calc_citation_velocity(citation_count: int, publication_date: str) -> float:
    if not publication_date:
        return 0.0
    pub_date = datetime.strptime(publication_date, "%Y-%m-%d")
    days = max((datetime.now() - pub_date).days, 30)
    return citation_count / days
```

**SQLite papers 表结构**：
```sql
CREATE TABLE papers (
    id TEXT PRIMARY KEY,              -- arXiv ID
    title TEXT,
    abstract TEXT,
    authors TEXT,                     -- JSON array
    published_date TEXT,
    venue TEXT,
    citation_count INTEGER,
    citation_velocity REAL,           -- citationCount / days_since_published
    passed_by TEXT,                   -- 'venue' | 'velocity' | 'manual' | 'venue+velocity'
    source TEXT DEFAULT 'auto',       -- 'auto' | 'manual'
    arxiv_url TEXT,
    pdf_url TEXT,
    status TEXT DEFAULT 'collected'   -- collected/downloaded/parsed/embedded
);
```

---

### pipeline/downloader.py

**职责**：下载 PDF，提取关键段落。

**流程**：
1. 从 SQLite 读取 `status = 'collected'` 的论文
2. 下载 PDF 到 `storage/pdfs/` 目录（文件名为 arXiv ID）
3. 用 pymupdf 提取以下段落（通过字体大小和关键词识别章节标题）：
   - Abstract
   - Introduction（只取前两段）
   - Method / Methodology / Approach（完整）
   - Conclusion（完整）
   - Limitation / Limitations / Future Work（完整）
4. 如果段落识别失败，fallback：将全文按 token 分块，取前 1/4 和后 1/4
5. 将提取结果存入 SQLite `paper_sections` 表
6. 更新 `papers.status = 'downloaded'`

**pymupdf 段落识别策略**：
- 遍历所有 block，检测字体大小 > 正文平均值 * 1.2 的文字为标题
- 匹配标题关键词列表：`["abstract", "introduction", "method", "approach", "conclusion", "limitation", "future work"]`
- 大小写不敏感匹配

**SQLite paper_sections 表结构**：
```sql
CREATE TABLE paper_sections (
    paper_id TEXT PRIMARY KEY,
    abstract TEXT,
    introduction TEXT,
    method TEXT,
    conclusion TEXT,
    limitation TEXT,
    raw_text TEXT,                    -- fallback 全文前1/4+后1/4
    extraction_method TEXT,           -- 'structured' | 'fallback'
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);
```

---

### pipeline/extractor.py

**职责**：调用 Claude Haiku 对每篇论文做结构化解析。

**流程**：
1. 从 SQLite 读取 `status = 'downloaded'` 的论文及其段落
2. 构建 Prompt（从 `prompts.yaml` 读取 `paper_extraction` 模板）
3. 调用 Claude API（模型：`claude-haiku-4-5`）
4. 解析返回的 JSON，写入 SQLite `paper_analysis` 表
5. 更新 `papers.status = 'parsed'`

**Claude 调用规范**：
- 每次调用传入：system prompt + 论文各段落拼接内容
- 要求返回纯 JSON，不含 markdown 代码块
- 加入重试逻辑（最多 3 次，指数退避：1s, 2s, 4s）
- 超时设置：60 秒

**SQLite paper_analysis 表结构**：
```sql
CREATE TABLE paper_analysis (
    paper_id TEXT PRIMARY KEY,
    research_problem TEXT,
    core_method TEXT,
    key_contribution TEXT,
    baselines_beaten TEXT,            -- JSON array
    limitations TEXT,                 -- JSON array
    future_work_mentioned TEXT,       -- JSON array
    sub_field_tags TEXT,              -- JSON array
    novelty_score INTEGER,            -- 1-10，Claude 自评
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);
```

---

### pipeline/embedder.py

**职责**：向量化论文，做聚类分析。

**流程**：
1. 从 SQLite 读取 `status = 'parsed'` 的论文
2. 拼接 `research_problem + core_method` 作为向量化文本
3. 调用 OpenAI `text-embedding-3-small` 或本地 `sentence-transformers/all-MiniLM-L6-v2`（依据 `config.yaml`）
4. 存入 ChromaDB（collection 名称为主题名）
5. 用 UMAP 降维到 2D，用 HDBSCAN 聚类
6. 对每个 cluster 调用 Claude Haiku（从 `prompts.yaml` 读取 `cluster_naming` 模板）生成名称和摘要
7. 将聚类结果写入 SQLite `clusters` 表和 `paper_clusters` 表
8. 更新 `papers.status = 'embedded'`

**SQLite clusters 表结构**：
```sql
CREATE TABLE clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    name TEXT,                        -- Claude 命名
    summary TEXT,                     -- Claude 描述
    core_methods TEXT,                -- JSON array
    open_questions TEXT,              -- JSON array
    paper_count INTEGER,
    trend TEXT                        -- 'emerging' | 'hot' | 'declining' | 'stable'
);

CREATE TABLE paper_clusters (
    paper_id TEXT,
    cluster_id INTEGER,
    umap_x REAL,
    umap_y REAL,
    FOREIGN KEY (paper_id) REFERENCES papers(id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
);
```

---

### pipeline/analyst.py

**职责**：趋势分析、盲区发现、Idea 生成，输出最终报告。

**流程**：

**Step 1 — 趋势判断预处理**（在调用 Claude 之前做）：
```python
def classify_trend(papers_by_month: list[int]) -> str:
    recent_3m = sum(papers_by_month[-3:])
    prev_3m = sum(papers_by_month[-6:-3])
    if prev_3m == 0:
        return 'emerging'
    ratio = recent_3m / prev_3m
    if ratio > 1.5 and recent_3m >= 5:
        return 'emerging'
    if recent_3m >= 10:
        return 'hot'
    if ratio < 0.5:
        return 'declining'
    return 'stable'
```

**Step 2 — Claude 趋势分析**：使用 `prompts.yaml` 中 `trend_analysis` 模板，模型：`claude-sonnet-4-5`

**Step 3 — 盲区发现**：汇总所有论文的 `limitations` + `future_work_mentioned` 字段，使用 `blind_spot_discovery` 模板

**Step 4 — Idea 生成**：使用 `idea_generation` 模板，生成 3-5 个结构化 Idea，写入 `ideas` 表

**Step 5 — 报告渲染**：使用 `report_generation` 模板，生成 Markdown 报告，保存到 `output/reports/{topic}_{YYYY-MM}.md`

**Step 6 — Git Push**：调用 `scripts/git_push.py`

**SQLite ideas 表结构**（存储生成的 Idea，供后续深化使用）：
```sql
CREATE TABLE ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT,
    run_date TEXT,
    title TEXT,
    problem_statement TEXT,
    addresses_blind_spot TEXT,
    proposed_approach TEXT,
    key_hypothesis TEXT,
    related_work TEXT,                -- JSON array
    difference_from_existing TEXT,
    experiment_design TEXT,
    potential_risks TEXT,             -- JSON array
    novelty_assessment TEXT,          -- 'incremental' | 'moderate' | 'high'
    estimated_difficulty TEXT,        -- 'low' | 'medium' | 'high'
    refined BOOLEAN DEFAULT FALSE
);
```

---

### pipeline/refiner.py

**职责**：接收用户选定的 Idea，定向搜索相关论文，输出深化分析报告。

**触发方式**：用户在 Web UI 的 Report 页面点击「深化这个 Idea」，或通过 CLI `python run.py --refine idea_id`。

**流程**：

**Step 1 — 提取搜索关键词**：
- 读取 `ideas` 表中指定 `idea_id` 的完整内容
- 调用 Claude Haiku（`prompts.yaml` 中 `idea_keyword_extraction` 模板）提取 5-8 个精准搜索关键词
- 这些关键词专门针对该 Idea 的具体技术点，比初始关键词更精准

**Step 2 — 定向搜索**（规模小，10-20 篇）：
- 采集策略与主流程完全相同：**顶会顶刊 OR arXiv 高增速论文**
- 使用相同的 `citation_velocity` 阈值和顶会白名单
- 排除已在 `papers.db` 中的论文（按 arXiv ID 去重）
- 结果存入 `refinement_papers` 表（不写入主 `papers` 表）

**Step 3 — 快速摘要解析**：
- 只用摘要，不下载 PDF（`config.yaml` 中 `refinement.use_abstract_only: true`）
- 调用 Claude Haiku 做简化版结构化解析（只提取 `research_problem`、`core_method`、`limitations`）

**Step 4 — Idea 深化分析**：
- 将原始 Idea + 新找到的相关论文摘要解析结果一并输入 Claude Sonnet
- 使用 `prompts.yaml` 中 `idea_deepening` 模板
- 输出深化报告，写入 `idea_refinements` 表

**Step 5 — 存储与输出**：
- 深化报告渲染为 Markdown，追加到原报告文件末尾（新增 `## Idea 深化：{title}` 章节）
- 更新 `ideas.refined = TRUE`
- 触发 Git Push

**SQLite refinement_papers 表结构**：
```sql
CREATE TABLE refinement_papers (
    id TEXT PRIMARY KEY,              -- arXiv ID
    idea_id INTEGER,
    title TEXT,
    abstract TEXT,
    venue TEXT,
    citation_velocity REAL,
    passed_by TEXT,                   -- 'venue' | 'velocity'
    research_problem TEXT,
    core_method TEXT,
    limitations TEXT,                 -- JSON array
    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE TABLE idea_refinements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id INTEGER,
    run_date TEXT,
    papers_found INTEGER,
    closest_existing_work TEXT,       -- JSON array，最接近的已有工作
    overlap_analysis TEXT,            -- 与已有工作的差异分析
    method_detail TEXT,               -- 细化后的技术路线
    recommended_baselines TEXT,       -- JSON array
    recommended_datasets TEXT,        -- JSON array
    feasibility_assessment TEXT,      -- 可行性评估（更新版）
    mvp_experiment TEXT,              -- 最小可验证实验
    updated_risks TEXT,               -- JSON array
    report_md TEXT,                   -- 完整 Markdown 深化报告
    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);
```

---

### scripts/git_push.py

**职责**：将生成的 Markdown 报告自动 push 到 GitHub 报告 repo。

**流程**：
1. 从 `config.yaml` 读取 `git.reports_repo_path`
2. 如果路径为空，打印提示并跳过，不报错
3. 将报告文件复制到对应子目录（按主题名分类，空格替换为连字符）
4. 更新报告 repo 的 `README.md` 索引（在对应主题的列表下追加新报告链接）
5. `git add → git commit → git push`
6. commit message 使用 `config.yaml` 中的 `commit_message_template`

---

### web/app.py

**职责**：FastAPI 后端，为 Web UI 提供所有接口。

**必须实现的接口**：

```
POST /api/run
  body: {topic: str, time_range_months: int}
  描述: 触发完整 pipeline（采集→解析→聚类→分析）

POST /api/upload
  body: {arxiv_ids: list[str]} 或 multipart/form-data（PDF 文件）
  描述: 手动添加指定论文，直接进入 downloader 阶段

GET  /api/progress
  描述: SSE 接口，实时推送 pipeline 进度日志
  格式: {"step": str, "status": str, "message": str, "progress": int}

GET  /api/papers
  query: topic, source (all|auto|manual)
  描述: 返回论文列表，含 passed_by 和 source 字段

GET  /api/clusters
  query: topic
  描述: 返回聚类结果（含 UMAP 坐标、cluster 名称、trend）

GET  /api/report
  query: topic
  描述: 返回最终报告 JSON（含 ideas 列表）

GET  /api/report/md
  query: topic
  描述: 返回 Markdown 原文

GET  /api/ideas
  query: topic
  描述: 返回该主题所有生成的 Idea 列表（含 refined 状态）

POST /api/refine
  body: {idea_id: int}
  描述: 触发 Idea 深化流程（定向搜索 + 深化分析）

GET  /api/refinement/{idea_id}
  描述: 返回指定 Idea 的深化报告
```

**SSE 进度格式**：
```json
{"step": "collector", "status": "running", "message": "正在采集 arXiv 论文...", "progress": 20}
```

`step` 枚举值：`collector` | `downloader` | `extractor` | `embedder` | `analyst` | `refiner`
`status` 枚举值：`pending` | `running` | `done` | `error`

---

### Web UI（React）

**Dashboard.jsx**：
- 文本输入框：研究主题
- 下拉框：时间范围（3个月 / 6个月 / 1年）
- 手动论文添加区域：
  - 文本输入框：输入 arXiv ID（逗号分隔，支持多个）
  - 文件上传区：拖拽上传本地 PDF
  - 已添加论文预览列表（可逐条删除）
- 运行按钮
- 实时日志区域（SSE 流式展示，带进度条，颜色区分不同 step）

**Overview.jsx**：
- 左侧：Cluster 列表（含 trend 标签：🔥热门 / 🚀新兴 / 📉降温 / 📊稳定），点击高亮对应区域
- 中间：UMAP 交互散点图（D3.js），每个点是一篇论文，颜色按 cluster，形状区分 `passed_by`（顶会用圆形、高增速用三角形、手动用星形），hover 显示标题和 venue
- 右侧：时间热力图，X 轴月份，Y 轴 cluster，颜色深度表示论文数量

**Report.jsx**：
- 顶部：概览统计卡片（总论文数 / 顶会论文数 / 高增速论文数 / 手动论文数 / cluster 数 / 时间范围）
- 趋势摘要区块（prose 形式）
- 盲区列表（可展开，展示支持该盲区判断的论文引用依据）
- Idea 卡片列表，每张卡片包含：
  - 标题、问题定义、方法路线摘要
  - 新颖度标签（incremental / moderate / high）、难度标签
  - 两个按钮：「🔍 深化这个 Idea」（触发 refiner，跳转 IdeaRefine 页）、「📄 导出 Markdown」

**IdeaRefine.jsx**：
- 顶部：原始 Idea 完整内容卡片
- 中间：定向搜索实时进度（SSE，同 Dashboard 风格）
- 下方：深化报告展示，分区块展示：
  - 最接近的已有工作（含论文标题、venue、差异分析）
  - 细化后的技术路线（比原 Idea 更具体）
  - 推荐基线模型和数据集
  - 最小可验证实验（MVP experiment）
  - 更新后的风险点
- 底部：导出按钮（导出完整深化报告为 Markdown）

---

## config.yaml 规范

```yaml
# 基本配置
topic: "reinforcement learning"
time_range_months: 6

# API Keys（优先从环境变量读取，config 中的值作为 fallback）
anthropic_api_key: ""         # 或环境变量 ANTHROPIC_API_KEY
openai_api_key: ""            # 用于 embedding，留空则使用本地模型

# LLM 模型配置
models:
  extraction: "claude-haiku-4-5"       # 论文结构化解析（按篇调用）
  analysis: "claude-sonnet-4-5"        # 趋势分析、盲区、Idea 生成
  refinement: "claude-sonnet-4-5"      # Idea 深化分析

# 向量化配置
embedding:
  provider: "openai"                   # openai 或 local
  model: "text-embedding-3-small"
  local_model: "all-MiniLM-L6-v2"

# 顶会白名单（按领域分组，keyword_expansion 返回的 venues_category 决定使用哪组）
venues:
  machine_learning:
    - NeurIPS
    - ICML
    - ICLR
    - JMLR
    - TMLR
  nlp:
    - ACL
    - EMNLP
    - NAACL
    - TACL
    - EACL
  cv:
    - CVPR
    - ICCV
    - ECCV
    - TPAMI
    - IJCV
  robotics:
    - CoRL
    - ICRA
    - RSS
    - IROS
  ai_general:
    - AAAI
    - IJCAI
    - UAI

# 采集配置
collection:
  max_papers_per_keyword: 50
  citation_velocity_threshold: 0.5    # 每天引用数 >= 此值视为高增速
  max_days_for_velocity: 180          # 只对发布 180 天内的论文做增速判断
  max_papers_to_analyze: 50          # 进入全文解析的上限

# Idea 深化配置
refinement:
  max_papers: 20                      # 定向搜索最多采集论文数
  use_abstract_only: true             # 只用摘要，不下载 PDF

# Git 报告 Repo 配置
git:
  reports_repo_path: ""               # 本地报告 repo 路径，留空则跳过 push
  auto_push: true
  commit_message_template: "📄 Add {topic} report ({date})"

# Web UI 配置
web:
  host: "0.0.0.0"
  port: 8000
  cors_origins: ["http://localhost:3000"]
```

---

## README.md 规范

README.md 必须包含以下章节，按此顺序：

```
# Paper Radar 🔭

一句话介绍。

## Features

## Quick Start
（3步启动：clone → 配置 config.yaml → python run.py）

## Configuration
（config.yaml 各字段说明表格）

## How to Describe Your Topic（Prompt 使用指南）

## How Papers Are Selected（采集策略说明）

## Internal Prompts（内部 Prompt 模板说明）

## Venue List
（顶会白名单说明及自定义方法）

## Output Format
（报告结构说明，含深化报告结构）

## Cost Estimation

## Development Roadmap
```

**"How to Describe Your Topic" 章节内容**：

```markdown
## How to Describe Your Topic

### ✅ 推荐写法

| 写法 | 说明 |
|------|------|
| `reinforcement learning` | 通用子领域，自动扩展关键词 |
| `offline reinforcement learning` | 细分方向，结果更精准 |
| `LLM reasoning and planning` | 多词组合，覆盖交叉方向 |
| `diffusion models for robotics` | 跨领域组合，适合找交叉盲区 |

### ⚠️ 不推荐写法

| 写法 | 问题 |
|------|------|
| `AI` | 过于宽泛，论文数量爆炸 |
| `MAPPO with communication constraints` | 过于细节，采集不到足够论文 |

### 建议粒度
选择「一个研究子方向」级别，例如 `multi-agent reinforcement learning`
优于 `reinforcement learning`，但 `MAPPO with communication constraints` 过细。
```

**"How Papers Are Selected" 章节内容**：

```markdown
## How Papers Are Selected

Paper Radar 采集以下两类论文（满足任意一条即纳入）：

**① 顶会顶刊论文**
通过 Semantic Scholar 验证发表 venue，与内置白名单匹配。
白名单涵盖 NeurIPS、ICML、ICLR、ACL、CVPR 等主流顶会。

**② arXiv 高增速论文**
针对近 180 天内的 arXiv 预印本，计算归一化引用速度：

  citation_velocity = citationCount / max(days_since_published, 30)

速度超过阈值（默认 0.5，即平均每天半个引用）的论文视为社区高关注，
即使尚未发表于顶会也纳入分析。

**③ 手动指定论文**
通过 arXiv ID 或上传 PDF 直接添加，不受上述过滤限制。

你可以在 `config.yaml` 中调整 `citation_velocity_threshold` 和顶会白名单。
```

---

## prompts.yaml 规范

prompts.yaml 是系统中所有 Claude Prompt 的唯一来源，代码中**禁止**硬编码任何 Prompt 字符串，必须从此文件读取。具体内容见 `prompts.yaml` 文件。

| 名称 | 用途 | 模型 |
|------|------|------|
| `keyword_expansion` | 主题 → 英文关键词 + 领域分类 | Haiku |
| `paper_extraction` | 单篇论文全文段落 → 结构化 JSON | Haiku |
| `cluster_naming` | 论文簇 → 子方向名称和摘要 | Haiku |
| `trend_analysis` | 时序数据 → 趋势判断报告 | Sonnet |
| `blind_spot_discovery` | 局限性汇总 → 盲区识别 | Sonnet |
| `idea_generation` | 盲区 + 方法摘要 → 研究 Idea | Sonnet |
| `report_generation` | 所有分析数据 → Markdown 报告 | Sonnet |
| `idea_keyword_extraction` | Idea 内容 → 定向搜索关键词 | Haiku |
| `idea_deepening` | Idea + 新论文解析 → 深化分析报告 | Sonnet |

---

## 代码规范

1. 所有 Python 文件顶部必须有模块说明注释
2. 每个 pipeline 模块必须可以独立运行（`if __name__ == "__main__"` 测试入口）
3. 所有 Claude API 调用必须有重试逻辑（最多 3 次，指数退避：1s, 2s, 4s）
4. 所有外部 API 调用必须有超时设置（HTTP 请求 30 秒，PDF 下载 120 秒）
5. pipeline 每个阶段结束时打印进度日志（格式：`[阶段名] ✓ 完成 X 篇论文处理`）
6. 错误必须被捕获并记录，单篇论文失败不能中断整个 pipeline
7. API Key 优先从环境变量读取，config.yaml 中的值作为 fallback
8. 所有文件路径使用 `pathlib.Path`，不使用字符串拼接

---

## 构建顺序

请按以下顺序构建，每一步完成后验证可运行：

1. 创建目录结构 + `requirements.txt` + `config.yaml` + `prompts.yaml`
2. 实现 `pipeline/collector.py`（含 SQLite 初始化、顶会过滤、citation_velocity 过滤、manual 模式）
3. 实现 `pipeline/downloader.py`（含 pymupdf 段落识别和 fallback）
4. 实现 `pipeline/extractor.py`（含重试逻辑）
5. 实现 `pipeline/embedder.py`（含 UMAP + HDBSCAN + cluster 命名）
6. 实现 `pipeline/analyst.py`（含趋势分析、盲区发现、Idea 生成、Markdown 渲染、ideas 表写入）
7. 实现 `pipeline/refiner.py`（含定向搜索、快速摘要解析、深化分析、refinement_papers 表）
8. 实现 `scripts/git_push.py`
9. 实现 `run.py`（串联整个 pipeline，支持 `--papers arxiv_id1,id2` 和 `--refine idea_id` 参数）
10. 实现 `web/app.py`（FastAPI，含全部接口和 SSE）
11. 实现 Web UI（React，四个页面：Dashboard / Overview / Report / IdeaRefine）
12. 完善 `README.md`