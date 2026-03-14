# Paper Radar

Iterative top-venue paper tracking and research insight generation system. Input a research topic, and Paper Radar automatically collects, analyzes, clusters, and generates trend reports with actionable research ideas.

## Features

- **Automated paper collection** from arXiv + Semantic Scholar with top-venue and high-velocity filtering
- **Manual paper addition** via arXiv IDs or local PDF upload
- **PDF parsing** with intelligent section extraction (Abstract, Method, Conclusion, etc.)
- **Claude-powered structured analysis** of each paper (Haiku for extraction, Sonnet for synthesis)
- **UMAP + HDBSCAN clustering** to identify research sub-directions
- **Trend analysis** with emerging/hot/declining/stable classification
- **Blind spot discovery** from aggregated limitations and future work
- **Research idea generation** with novelty and feasibility assessment
- **Idea refinement** with targeted literature search and deepened analysis
- **Interactive Web UI** with D3.js cluster visualization, real-time SSE progress
- **Markdown report generation** with auto-push to GitHub

## Quick Start

```bash
# 1. Clone the repo
git clone <your-repo-url> && cd paper-radar

# 2. Install all dependencies (Python + Node)
./start.sh install

# 3. Set API keys
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"  # optional, for embeddings; 不设则自动用本地模型

# 4. Run the full pipeline
./start.sh run --topic "offline reinforcement learning"
```

### start.sh 用法

```bash
./start.sh install                                # 安装 Python + Node 依赖（首次运行）
./start.sh run                                    # 使用 config.yaml 默认配置运行 pipeline
./start.sh run --topic "LLM reasoning"            # 指定研究主题
./start.sh run --months 3                         # 指定时间范围
./start.sh run --papers 2401.12345,2402.00001     # 手动添加论文
./start.sh web                                    # 启动 Web UI（前后端同时启动）
./start.sh api                                    # 只启动后端 API
./start.sh refine 1                               # 深化指定 Idea
./start.sh help                                   # 查看帮助
```

### Web UI

```bash
./start.sh web
```

启动后访问：
- 前端 UI：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- 按 `Ctrl+C` 同时关闭前后端

### 直接使用 Python（不用 start.sh）

```bash
pip install -r requirements.txt
python run.py --topic "reinforcement learning"    # 运行 pipeline
python run.py --refine 1                          # 深化 Idea
python web/app.py                                 # 启动后端
```

## Configuration

All settings are in `config.yaml`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `topic` | string | `"reinforcement learning"` | Research topic to analyze |
| `time_range_months` | int | `6` | How far back to search |
| `anthropic_api_key` | string | `""` | Anthropic API key (env var preferred) |
| `openai_api_key` | string | `""` | OpenAI API key for embeddings |
| `models.extraction` | string | `"claude-haiku-4-5"` | Model for paper parsing |
| `models.analysis` | string | `"claude-sonnet-4-5"` | Model for trend/idea generation |
| `models.refinement` | string | `"claude-sonnet-4-5"` | Model for idea deepening |
| `embedding.provider` | string | `"openai"` | `openai` or `local` |
| `embedding.model` | string | `"text-embedding-3-small"` | OpenAI embedding model |
| `embedding.local_model` | string | `"all-MiniLM-L6-v2"` | Local sentence-transformers model |
| `collection.max_papers_per_keyword` | int | `50` | Max papers per search keyword |
| `collection.citation_velocity_threshold` | float | `0.5` | Min citations/day for velocity filter |
| `collection.max_papers_to_analyze` | int | `50` | Max papers entering full analysis |
| `refinement.max_papers` | int | `20` | Max papers in targeted refinement search |
| `git.reports_repo_path` | string | `""` | Path to report repo (empty = skip push) |

## How to Describe Your Topic

### Recommended

| Input | Notes |
|-------|-------|
| `reinforcement learning` | Broad sub-field, auto-expands keywords |
| `offline reinforcement learning` | Specific direction, more precise results |
| `LLM reasoning and planning` | Multi-word combo, covers cross-cutting work |
| `diffusion models for robotics` | Cross-domain combo, great for finding blind spots |

### Not Recommended

| Input | Problem |
|-------|---------|
| `AI` | Too broad, paper count explodes |
| `MAPPO with communication constraints` | Too narrow, insufficient papers |

### Suggested Granularity

Choose a "research sub-direction" level, e.g., `multi-agent reinforcement learning` is better than `reinforcement learning`, but `MAPPO with communication constraints` is too specific.

## How Papers Are Selected

Paper Radar collects papers meeting **any** of these criteria:

**1. Top Venue Papers**
Verified via Semantic Scholar's `venue` field against built-in whitelist (NeurIPS, ICML, ICLR, ACL, CVPR, etc.).

**2. arXiv High-Velocity Papers**
For papers published within 180 days, normalized citation velocity is computed:

```
citation_velocity = citationCount / max(days_since_published, 30)
```

Papers with velocity >= threshold (default 0.5, i.e., ~1 citation every 2 days) are included even without top-venue publication.

**3. Manually Specified Papers**
Added via arXiv ID or PDF upload, bypassing all filters.

Adjust `citation_velocity_threshold` and venue lists in `config.yaml`.

## Internal Prompts

All Claude prompts are defined in `prompts.yaml` — no prompts are hardcoded. You can modify system/user prompts to customize behavior:

| Prompt | Purpose | Model |
|--------|---------|-------|
| `keyword_expansion` | Topic to search keywords + venue category | Haiku |
| `paper_extraction` | Paper sections to structured JSON | Haiku |
| `cluster_naming` | Paper cluster to name + summary | Haiku |
| `trend_analysis` | Time data to trend report | Sonnet |
| `blind_spot_discovery` | Limitations to blind spots | Sonnet |
| `idea_generation` | Blind spots + methods to ideas | Sonnet |
| `report_generation` | All data to Markdown report | Sonnet |
| `idea_keyword_extraction` | Idea to targeted search keywords | Haiku |
| `idea_deepening` | Idea + new papers to refined plan | Sonnet |

## Venue List

Default whitelist by category (auto-selected based on topic):

| Category | Venues |
|----------|--------|
| Machine Learning | NeurIPS, ICML, ICLR, JMLR, TMLR |
| NLP | ACL, EMNLP, NAACL, TACL, EACL |
| Computer Vision | CVPR, ICCV, ECCV, TPAMI, IJCV |
| Robotics | CoRL, ICRA, RSS, IROS |
| AI General | AAAI, IJCAI, UAI |

Customize by editing the `venues` section in `config.yaml`.

## Output Format

Reports are saved to `output/reports/{topic}_{YYYY-MM}.md` with this structure:

```
# {Topic} Research Landscape Report
## Key Takeaways
## Overview
## Sub-fields & Clusters
## Trend Analysis
## Research Blind Spots
## Research Ideas
## Notable Papers
## Methodology Note
```

Refinement reports are appended as `## Idea Refinement: {title}` sections.

## Cost Estimation

Per run (assuming 30 papers analyzed):

| Component | API Calls | Estimated Cost |
|-----------|-----------|---------------|
| Keyword expansion | 1x Haiku | ~$0.01 |
| Paper extraction | 30x Haiku | ~$0.30 |
| Cluster naming | 3-5x Haiku | ~$0.05 |
| Trend analysis | 1x Sonnet | ~$0.10 |
| Blind spot discovery | 1x Sonnet | ~$0.10 |
| Idea generation | 1x Sonnet | ~$0.10 |
| Report generation | 1x Sonnet | ~$0.15 |
| Embeddings (OpenAI) | 30 texts | ~$0.01 |
| **Total** | | **~$0.80** |

Idea refinement adds ~$0.30-0.50 per idea.

## Development Roadmap

- [ ] Multi-topic comparison reports
- [ ] Citation graph analysis
- [ ] Automated weekly/monthly scheduling
- [ ] Paper recommendation based on user history
- [ ] Integration with Zotero/Mendeley
- [ ] Email/Slack notifications for new high-impact papers
- [ ] Fine-grained PDF parsing with layout analysis
- [ ] Collaborative annotations and comments
