"""
pipeline/collector.py — 第一阶段：论文采集

职责：
- 从 arXiv 搜索论文
- 通过 Semantic Scholar 获取 venue、citation 信息
- 按顶会白名单和 citation velocity 过滤
- 合并手动指定论文
- 结果写入 SQLite papers 表
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import arxiv
import requests
import yaml
import anthropic

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "storage" / "papers.db"
CONFIG_PATH = ROOT / "config.yaml"
PROMPTS_PATH = ROOT / "prompts.yaml"

SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper"
SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
SS_FIELDS = "venue,citationCount,influentialCitationCount,publicationDate,externalIds"


def load_config():
    """加载配置文件"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_prompts():
    """加载 Prompt 模板"""
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_db():
    """初始化 SQLite 数据库，创建所有需要的表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            authors TEXT,
            published_date TEXT,
            venue TEXT,
            citation_count INTEGER,
            citation_velocity REAL,
            passed_by TEXT,
            source TEXT DEFAULT 'auto',
            arxiv_url TEXT,
            pdf_url TEXT,
            status TEXT DEFAULT 'collected'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS paper_sections (
            paper_id TEXT PRIMARY KEY,
            abstract TEXT,
            introduction TEXT,
            method TEXT,
            conclusion TEXT,
            limitation TEXT,
            raw_text TEXT,
            extraction_method TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS paper_analysis (
            paper_id TEXT PRIMARY KEY,
            research_problem TEXT,
            core_method TEXT,
            key_contribution TEXT,
            baselines_beaten TEXT,
            limitations TEXT,
            future_work_mentioned TEXT,
            sub_field_tags TEXT,
            novelty_score INTEGER,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            name TEXT,
            summary TEXT,
            core_methods TEXT,
            open_questions TEXT,
            paper_count INTEGER,
            trend TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS paper_clusters (
            paper_id TEXT,
            cluster_id INTEGER,
            umap_x REAL,
            umap_y REAL,
            FOREIGN KEY (paper_id) REFERENCES papers(id),
            FOREIGN KEY (cluster_id) REFERENCES clusters(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            run_date TEXT,
            title TEXT,
            problem_statement TEXT,
            addresses_blind_spot TEXT,
            proposed_approach TEXT,
            key_hypothesis TEXT,
            related_work TEXT,
            difference_from_existing TEXT,
            experiment_design TEXT,
            potential_risks TEXT,
            novelty_assessment TEXT,
            estimated_difficulty TEXT,
            refined BOOLEAN DEFAULT FALSE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS refinement_papers (
            id TEXT PRIMARY KEY,
            idea_id INTEGER,
            title TEXT,
            abstract TEXT,
            venue TEXT,
            citation_velocity REAL,
            passed_by TEXT,
            research_problem TEXT,
            core_method TEXT,
            limitations TEXT,
            FOREIGN KEY (idea_id) REFERENCES ideas(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS idea_refinements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idea_id INTEGER,
            run_date TEXT,
            papers_found INTEGER,
            closest_existing_work TEXT,
            overlap_analysis TEXT,
            method_detail TEXT,
            recommended_baselines TEXT,
            recommended_datasets TEXT,
            feasibility_assessment TEXT,
            mvp_experiment TEXT,
            updated_risks TEXT,
            report_md TEXT,
            FOREIGN KEY (idea_id) REFERENCES ideas(id)
        )
    """)

    conn.commit()
    return conn


def get_anthropic_client(config):
    """创建 Anthropic 客户端，优先使用环境变量"""
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY") or config.get("anthropic_api_key")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 未设置。请设置环境变量或在 config.yaml 中配置。")
    return anthropic.Anthropic(api_key=api_key)


def expand_keywords(config, prompts):
    """调用 Claude Haiku 扩展关键词"""
    client = get_anthropic_client(config)
    topic = config["topic"]
    prompt_cfg = prompts["keyword_expansion"]

    user_msg = prompt_cfg["user"].format(topic=topic)

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=config["models"]["extraction"],
                max_tokens=1024,
                system=prompt_cfg["system"],
                messages=[{"role": "user", "content": user_msg}],
                timeout=60,
            )
            text = response.content[0].text.strip()
            # 尝试提取 JSON（可能被包裹在 markdown 代码块中）
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            print(f"[collector] ✓ 关键词扩展完成: {result['keywords']}")
            print(f"[collector]   领域分类: {result['venues_category']}")
            return result
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt
                print(f"[collector] 关键词扩展失败，{wait}s 后重试: {e}")
                time.sleep(wait)
            else:
                raise RuntimeError(f"关键词扩展失败: {e}")


def search_arxiv(keywords, config):
    """用扩展后的关键词并发查询 arXiv"""
    max_per_kw = config["collection"]["max_papers_per_keyword"]
    time_range_months = config.get("time_range_months", 6)
    cutoff_date = datetime.now() - timedelta(days=time_range_months * 30)

    all_papers = {}

    def fetch_keyword(kw):
        results = []
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=kw,
                max_results=max_per_kw,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            for paper in client.results(search):
                if paper.published.replace(tzinfo=None) < cutoff_date:
                    continue
                arxiv_id = paper.entry_id.split("/abs/")[-1].split("v")[0]
                results.append({
                    "id": arxiv_id,
                    "title": paper.title,
                    "abstract": paper.summary,
                    "authors": json.dumps([a.name for a in paper.authors]),
                    "published_date": paper.published.strftime("%Y-%m-%d"),
                    "arxiv_url": paper.entry_id,
                    "pdf_url": paper.pdf_url,
                })
        except Exception as e:
            print(f"[collector] arXiv 搜索 '{kw}' 失败: {e}")
        return results

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_keyword, kw): kw for kw in keywords}
        for future in as_completed(futures):
            kw = futures[future]
            try:
                papers = future.result()
                for p in papers:
                    if p["id"] not in all_papers:
                        all_papers[p["id"]] = p
                print(f"[collector]   arXiv '{kw}': {len(papers)} 篇")
            except Exception as e:
                print(f"[collector]   arXiv '{kw}' 出错: {e}")

    print(f"[collector] ✓ arXiv 搜索完成，共 {len(all_papers)} 篇（去重后）")
    return all_papers


def calc_citation_velocity(citation_count, publication_date):
    """计算归一化引用速度"""
    if not publication_date:
        return 0.0
    try:
        pub_date = datetime.strptime(publication_date, "%Y-%m-%d")
    except ValueError:
        return 0.0
    days = max((datetime.now() - pub_date).days, 30)
    return citation_count / days


def query_semantic_scholar(paper_id, title):
    """查询单篇论文的 Semantic Scholar 信息"""
    # 先尝试用 arXiv ID 查询
    try:
        url = f"{SEMANTIC_SCHOLAR_API}/ARXIV:{paper_id}"
        resp = requests.get(url, params={"fields": SS_FIELDS}, timeout=30)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # fallback: 用标题搜索
    try:
        resp = requests.get(
            SEMANTIC_SCHOLAR_SEARCH,
            params={"query": title, "fields": SS_FIELDS, "limit": 1},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return data["data"][0]
    except Exception:
        pass

    return None


def enrich_with_semantic_scholar(papers):
    """批量查询 Semantic Scholar，添加 venue 和引用信息"""
    enriched = {}
    total = len(papers)

    for i, (pid, paper) in enumerate(papers.items()):
        ss_data = query_semantic_scholar(pid, paper["title"])
        if ss_data:
            paper["venue"] = ss_data.get("venue", "")
            paper["citation_count"] = ss_data.get("citationCount", 0) or 0
            paper["citation_velocity"] = calc_citation_velocity(
                paper["citation_count"], paper["published_date"]
            )
        else:
            paper["venue"] = ""
            paper["citation_count"] = 0
            paper["citation_velocity"] = 0.0

        enriched[pid] = paper

        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"[collector]   Semantic Scholar: {i + 1}/{total}")

        # 尊重速率限制
        time.sleep(0.5)

    print(f"[collector] ✓ Semantic Scholar 查询完成")
    return enriched


def filter_papers(papers, config, venues_category):
    """按顶会白名单和 citation velocity 过滤"""
    venues_config = config.get("venues", {})
    threshold = config["collection"]["citation_velocity_threshold"]
    max_days = config["collection"]["max_days_for_velocity"]

    # 构建白名单（主类别 + ai_general）
    whitelist = []
    if venues_category in venues_config:
        whitelist.extend(venues_config[venues_category])
    if venues_category != "ai_general" and "ai_general" in venues_config:
        whitelist.extend(venues_config["ai_general"])
    whitelist_lower = [v.lower() for v in whitelist]

    filtered = {}
    for pid, paper in papers.items():
        venue = (paper.get("venue") or "").strip()
        venue_match = any(wv in venue.lower() for wv in whitelist_lower) if venue else False

        pub_date = paper.get("published_date", "")
        velocity = paper.get("citation_velocity", 0.0)
        days_since = 999
        if pub_date:
            try:
                days_since = (datetime.now() - datetime.strptime(pub_date, "%Y-%m-%d")).days
            except ValueError:
                pass
        velocity_match = velocity >= threshold and days_since <= max_days

        if venue_match and velocity_match:
            paper["passed_by"] = "venue+velocity"
        elif venue_match:
            paper["passed_by"] = "venue"
        elif velocity_match:
            paper["passed_by"] = "velocity"
        else:
            continue

        filtered[pid] = paper

    print(f"[collector] ✓ 过滤完成: {len(filtered)}/{len(papers)} 篇通过")
    venue_count = sum(1 for p in filtered.values() if "venue" in p["passed_by"])
    velocity_count = sum(1 for p in filtered.values() if "velocity" in p["passed_by"])
    print(f"[collector]   顶会: {venue_count} 篇, 高增速: {velocity_count} 篇")
    return filtered


def add_manual_papers(manual_ids, conn):
    """添加手动指定的论文"""
    if not manual_ids:
        return

    papers = {}
    for arxiv_id in manual_ids:
        arxiv_id = arxiv_id.strip()
        if not arxiv_id:
            continue

        try:
            client = arxiv.Client()
            search = arxiv.Search(id_list=[arxiv_id])
            for paper in client.results(search):
                papers[arxiv_id] = {
                    "id": arxiv_id,
                    "title": paper.title,
                    "abstract": paper.summary,
                    "authors": json.dumps([a.name for a in paper.authors]),
                    "published_date": paper.published.strftime("%Y-%m-%d"),
                    "venue": "",
                    "citation_count": 0,
                    "citation_velocity": 0.0,
                    "passed_by": "manual",
                    "source": "manual",
                    "arxiv_url": paper.entry_id,
                    "pdf_url": paper.pdf_url,
                }
                break
        except Exception as e:
            print(f"[collector] 手动论文 {arxiv_id} 获取失败: {e}")

    if papers:
        save_papers(papers, conn)
        print(f"[collector] ✓ 手动论文添加: {len(papers)} 篇")

    return papers


def save_papers(papers, conn):
    """将论文保存到 SQLite"""
    c = conn.cursor()
    saved = 0
    for pid, paper in papers.items():
        try:
            c.execute("""
                INSERT OR IGNORE INTO papers
                (id, title, abstract, authors, published_date, venue, citation_count,
                 citation_velocity, passed_by, source, arxiv_url, pdf_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                paper["id"],
                paper["title"],
                paper["abstract"],
                paper["authors"],
                paper["published_date"],
                paper.get("venue", ""),
                paper.get("citation_count", 0),
                paper.get("citation_velocity", 0.0),
                paper.get("passed_by", ""),
                paper.get("source", "auto"),
                paper.get("arxiv_url", ""),
                paper.get("pdf_url", ""),
                "collected",
            ))
            saved += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    return saved


def collect(config=None, prompts=None, manual_ids=None, conn=None, progress_callback=None):
    """
    执行完整采集流程。

    Args:
        config: 配置字典，为 None 时从文件加载
        prompts: Prompt 模板字典，为 None 时从文件加载
        manual_ids: 手动指定的 arXiv ID 列表
        conn: SQLite 连接，为 None 时自动创建
        progress_callback: 进度回调函数 (step, status, message, progress)
    """
    if config is None:
        config = load_config()
    if prompts is None:
        prompts = load_prompts()
    if conn is None:
        conn = init_db()

    def report(status, message, progress):
        if progress_callback:
            progress_callback("collector", status, message, progress)
        print(f"[collector] {message}")

    report("running", "开始采集论文...", 0)

    # Step 1: 关键词扩展
    report("running", "正在扩展关键词...", 10)
    kw_result = expand_keywords(config, prompts)
    keywords = kw_result["keywords"]
    venues_category = kw_result["venues_category"]

    # Step 2: arXiv 搜索
    report("running", f"正在搜索 arXiv（{len(keywords)} 个关键词）...", 20)
    papers = search_arxiv(keywords, config)

    if not papers:
        report("done", "未找到任何论文", 100)
        return conn

    # Step 3: Semantic Scholar 查询
    report("running", f"正在查询 Semantic Scholar（{len(papers)} 篇）...", 40)
    papers = enrich_with_semantic_scholar(papers)

    # Step 4: 过滤
    report("running", "正在过滤论文...", 70)
    filtered = filter_papers(papers, config, venues_category)

    # Step 5: 限制数量
    max_analyze = config["collection"]["max_papers_to_analyze"]
    if len(filtered) > max_analyze:
        # 优先保留顶会论文，然后按 citation_velocity 排序
        sorted_papers = sorted(
            filtered.values(),
            key=lambda p: (
                1 if "venue" in p.get("passed_by", "") else 0,
                p.get("citation_velocity", 0),
            ),
            reverse=True,
        )
        filtered = {p["id"]: p for p in sorted_papers[:max_analyze]}
        print(f"[collector]   截取前 {max_analyze} 篇")

    # Step 6: 保存到 SQLite
    report("running", "正在保存到数据库...", 80)
    saved = save_papers(filtered, conn)

    # Step 7: 手动论文
    if manual_ids:
        report("running", "正在添加手动论文...", 90)
        add_manual_papers(manual_ids, conn)

    total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    report("done", f"✓ 完成采集，共 {total} 篇论文", 100)

    return conn


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Paper Radar - 论文采集")
    parser.add_argument("--papers", type=str, help="手动指定 arXiv ID（逗号分隔）")
    args = parser.parse_args()

    manual = args.papers.split(",") if args.papers else None
    conn = collect(manual_ids=manual)
    conn.close()
