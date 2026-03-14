"""
pipeline/refiner.py — 第六阶段：Idea 定向搜索与深化

职责：
- 接收用户选定的 Idea
- 提取定向搜索关键词
- 小规模定向搜索（10-20 篇）
- 快速摘要解析
- Claude Sonnet 深化分析
- 输出深化报告
"""

import json
import time
from datetime import datetime, timedelta

import arxiv
import requests

from pipeline.collector import (
    ROOT, DB_PATH, init_db, load_config, load_prompts,
    get_anthropic_client, query_semantic_scholar, calc_citation_velocity,
    SEMANTIC_SCHOLAR_SEARCH, SS_FIELDS,
)

REPORTS_DIR = ROOT / "output" / "reports"


def get_idea(conn, idea_id):
    """从数据库获取 Idea"""
    row = conn.execute("""
        SELECT id, topic, title, problem_statement, proposed_approach,
               key_hypothesis, related_work, addresses_blind_spot
        FROM ideas WHERE id = ?
    """, (idea_id,)).fetchone()

    if not row:
        raise ValueError(f"Idea {idea_id} 不存在")

    return {
        "id": row[0],
        "topic": row[1],
        "title": row[2],
        "problem_statement": row[3],
        "proposed_approach": row[4],
        "key_hypothesis": row[5],
        "related_work": row[6],
        "addresses_blind_spot": row[7],
    }


def extract_search_keywords(idea, config, prompts):
    """Step 1: 调用 Claude Haiku 提取定向搜索关键词"""
    client = get_anthropic_client(config)
    model = config["models"]["extraction"]
    prompt_cfg = prompts["idea_keyword_extraction"]

    related_work = idea["related_work"]
    if isinstance(related_work, str):
        try:
            related_work = json.loads(related_work)
        except json.JSONDecodeError:
            related_work = [related_work]

    user_msg = prompt_cfg["user"].format(
        idea_title=idea["title"],
        problem_statement=idea["problem_statement"],
        proposed_approach=idea["proposed_approach"],
        related_work=", ".join(related_work) if isinstance(related_work, list) else str(related_work),
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=prompt_cfg["system"],
                messages=[{"role": "user", "content": user_msg}],
                timeout=60,
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = json.loads(text)
            print(f"[refiner]   关键词: {result['keywords']}")
            return result["keywords"]
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[refiner]   关键词提取失败: {e}")
                # fallback: 从标题提取
                return idea["title"].split()[:5]


def targeted_search(keywords, idea_id, config, conn):
    """Step 2: 定向搜索，规模小（10-20 篇）"""
    max_papers = config["refinement"]["max_papers"]

    # 获取已存在的论文 ID（去重用）
    existing_ids = set(
        r[0] for r in conn.execute("SELECT id FROM papers").fetchall()
    )

    venues_config = config.get("venues", {})
    # 合并所有白名单
    all_venues = []
    for category_venues in venues_config.values():
        all_venues.extend(category_venues)
    whitelist_lower = [v.lower() for v in all_venues]

    threshold = config["collection"]["citation_velocity_threshold"]
    found_papers = {}

    for kw in keywords:
        if len(found_papers) >= max_papers:
            break

        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=kw,
                max_results=10,
                sort_by=arxiv.SortCriterion.Relevance,
            )
            for paper in client.results(search):
                arxiv_id = paper.entry_id.split("/abs/")[-1].split("v")[0]
                if arxiv_id in existing_ids or arxiv_id in found_papers:
                    continue

                # 查询 Semantic Scholar
                ss_data = query_semantic_scholar(arxiv_id, paper.title)
                venue = ""
                citation_count = 0
                pub_date = paper.published.strftime("%Y-%m-%d")

                if ss_data:
                    venue = ss_data.get("venue", "") or ""
                    citation_count = ss_data.get("citationCount", 0) or 0

                velocity = calc_citation_velocity(citation_count, pub_date)

                # 相同的过滤逻辑
                venue_match = any(v in venue.lower() for v in whitelist_lower) if venue else False
                days = (datetime.now() - paper.published.replace(tzinfo=None)).days
                velocity_match = velocity >= threshold and days <= 180

                if venue_match or velocity_match:
                    passed_by = "venue" if venue_match else "velocity"
                    found_papers[arxiv_id] = {
                        "id": arxiv_id,
                        "title": paper.title,
                        "abstract": paper.summary,
                        "venue": venue,
                        "citation_velocity": velocity,
                        "passed_by": passed_by,
                    }

                if len(found_papers) >= max_papers:
                    break

                time.sleep(0.5)

        except Exception as e:
            print(f"[refiner]   搜索 '{kw}' 失败: {e}")

    # 保存到 refinement_papers 表
    c = conn.cursor()
    for pid, paper in found_papers.items():
        c.execute("""
            INSERT OR IGNORE INTO refinement_papers
            (id, idea_id, title, abstract, venue, citation_velocity, passed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            pid, idea_id,
            paper["title"], paper["abstract"],
            paper["venue"], paper["citation_velocity"], paper["passed_by"],
        ))
    conn.commit()

    print(f"[refiner]   定向搜索找到 {len(found_papers)} 篇论文")
    return found_papers


def quick_abstract_parse(papers, idea_id, config, prompts, conn):
    """Step 3: 快速摘要解析（只用摘要）"""
    client = get_anthropic_client(config)
    model = config["models"]["extraction"]

    parsed = []
    for pid, paper in papers.items():
        # 简化版：只提取 research_problem, core_method, limitations
        prompt = f"""Analyze this paper abstract and return a JSON object:
{{
  "research_problem": "one sentence",
  "core_method": "one sentence",
  "limitations": ["limitation1", "limitation2"]
}}

Title: {paper['title']}
Abstract: {paper['abstract']}

Return ONLY valid JSON."""

        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=512,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=60,
                )
                text = response.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                result = json.loads(text)

                # 更新数据库
                conn.execute("""
                    UPDATE refinement_papers
                    SET research_problem = ?, core_method = ?, limitations = ?
                    WHERE id = ? AND idea_id = ?
                """, (
                    result.get("research_problem", ""),
                    result.get("core_method", ""),
                    json.dumps(result.get("limitations", [])),
                    pid, idea_id,
                ))

                parsed.append({
                    "title": paper["title"],
                    "venue": paper["venue"],
                    **result,
                })
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)

        time.sleep(0.3)

    conn.commit()
    print(f"[refiner]   摘要解析完成 {len(parsed)} 篇")
    return parsed


def deepen_idea(idea, parsed_papers, config, prompts):
    """Step 4: Claude Sonnet 深化分析"""
    client = get_anthropic_client(config)
    model = config["models"]["refinement"]
    prompt_cfg = prompts["idea_deepening"]

    related_work = idea["related_work"]
    if isinstance(related_work, str):
        try:
            related_work = json.loads(related_work)
        except json.JSONDecodeError:
            related_work = [related_work]

    new_papers_summary = "\n".join(
        f"- {p['title']} ({p.get('venue', 'arXiv')})\n"
        f"  Problem: {p.get('research_problem', 'N/A')}\n"
        f"  Method: {p.get('core_method', 'N/A')}\n"
        f"  Limitations: {p.get('limitations', [])}"
        for p in parsed_papers
    )

    user_msg = prompt_cfg["user"].format(
        idea_title=idea["title"],
        problem_statement=idea["problem_statement"],
        proposed_approach=idea["proposed_approach"],
        key_hypothesis=idea["key_hypothesis"],
        related_work=", ".join(related_work) if isinstance(related_work, list) else str(related_work),
        papers_count=len(parsed_papers),
        new_papers_summary=new_papers_summary or "No new papers found.",
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=prompt_cfg["system"],
                messages=[{"role": "user", "content": user_msg}],
                timeout=120,
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[refiner]   深化分析失败: {e}")
                return None


def render_refinement_report(idea, deepening_result):
    """渲染深化报告为 Markdown"""
    if not deepening_result:
        return f"## Idea 深化：{idea['title']}\n\n深化分析失败。"

    md = f"## Idea 深化：{idea['title']}\n\n"
    md += f"**问题定义**: {idea['problem_statement']}\n\n"
    md += f"**原始方法**: {idea['proposed_approach']}\n\n"

    md += "### 最接近的已有工作\n\n"
    for work in deepening_result.get("closest_existing_work", []):
        md += f"- **{work.get('title', 'N/A')}** ({work.get('venue', 'N/A')})\n"
        md += f"  - 相似度: {work.get('similarity', 'N/A')}\n"
        md += f"  - 关键差异: {work.get('key_difference', 'N/A')}\n"

    md += f"\n### 重叠分析\n\n{deepening_result.get('overlap_analysis', 'N/A')}\n\n"
    md += f"### 细化后的技术路线\n\n{deepening_result.get('method_detail', 'N/A')}\n\n"

    md += "### 推荐基线\n\n"
    for b in deepening_result.get("recommended_baselines", []):
        md += f"- {b}\n"

    md += "\n### 推荐数据集\n\n"
    for d in deepening_result.get("recommended_datasets", []):
        md += f"- {d}\n"

    md += f"\n### 最小可验证实验\n\n{deepening_result.get('mvp_experiment', 'N/A')}\n\n"
    md += f"### 可行性评估\n\n{deepening_result.get('feasibility_assessment', 'N/A')}\n\n"

    md += "### 更新后的风险\n\n"
    for r in deepening_result.get("updated_risks", []):
        md += f"- {r}\n"

    verdict = deepening_result.get("verdict", "N/A")
    md += f"\n### 结论: **{verdict.upper()}**\n\n"
    md += f"{deepening_result.get('verdict_reason', '')}\n"

    return md


def save_refinement(conn, idea_id, deepening_result, report_md, papers_found):
    """保存深化结果到数据库"""
    c = conn.cursor()
    c.execute("""
        INSERT INTO idea_refinements
        (idea_id, run_date, papers_found, closest_existing_work, overlap_analysis,
         method_detail, recommended_baselines, recommended_datasets,
         feasibility_assessment, mvp_experiment, updated_risks, report_md)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        idea_id,
        datetime.now().strftime("%Y-%m-%d"),
        papers_found,
        json.dumps(deepening_result.get("closest_existing_work", [])),
        deepening_result.get("overlap_analysis", ""),
        deepening_result.get("method_detail", ""),
        json.dumps(deepening_result.get("recommended_baselines", [])),
        json.dumps(deepening_result.get("recommended_datasets", [])),
        deepening_result.get("feasibility_assessment", ""),
        deepening_result.get("mvp_experiment", ""),
        json.dumps(deepening_result.get("updated_risks", [])),
        report_md,
    ))
    c.execute("UPDATE ideas SET refined = TRUE WHERE id = ?", (idea_id,))
    conn.commit()


def append_to_report(topic, report_md):
    """将深化报告追加到原报告文件"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m")
    filename = f"{topic.replace(' ', '-')}_{date_str}.md"
    report_path = REPORTS_DIR / filename

    if report_path.exists():
        existing = report_path.read_text(encoding="utf-8")
        report_path.write_text(existing + "\n\n---\n\n" + report_md, encoding="utf-8")
    else:
        report_path.write_text(report_md, encoding="utf-8")

    return report_path


def refine(idea_id, conn=None, config=None, prompts=None, progress_callback=None):
    """
    执行 Idea 深化流程。

    Args:
        idea_id: 要深化的 Idea ID
        conn: SQLite 连接
        config: 配置字典
        prompts: Prompt 模板字典
        progress_callback: 进度回调函数
    """
    if config is None:
        config = load_config()
    if prompts is None:
        prompts = load_prompts()
    if conn is None:
        conn = init_db()

    def report(status, message, progress):
        if progress_callback:
            progress_callback("refiner", status, message, progress)
        print(f"[refiner] {message}")

    report("running", f"开始深化 Idea #{idea_id}...", 0)

    # 获取 Idea
    idea = get_idea(conn, idea_id)
    topic = idea["topic"]

    # Step 1: 提取搜索关键词
    report("running", "正在提取搜索关键词...", 10)
    keywords = extract_search_keywords(idea, config, prompts)

    # Step 2: 定向搜索
    report("running", f"正在定向搜索（{len(keywords)} 个关键词）...", 30)
    found_papers = targeted_search(keywords, idea_id, config, conn)

    # Step 3: 快速摘要解析
    report("running", f"正在解析 {len(found_papers)} 篇论文摘要...", 50)
    parsed_papers = quick_abstract_parse(found_papers, idea_id, config, prompts, conn)

    # Step 4: 深化分析
    report("running", "正在进行深化分析...", 70)
    deepening_result = deepen_idea(idea, parsed_papers, config, prompts)

    if deepening_result:
        # Step 5: 渲染并保存
        report("running", "正在保存深化报告...", 90)
        report_md = render_refinement_report(idea, deepening_result)
        save_refinement(conn, idea_id, deepening_result, report_md, len(found_papers))
        report_path = append_to_report(topic, report_md)

        # Git Push
        try:
            from scripts.git_push import push_report
            push_report(config, report_path, topic)
        except Exception as e:
            print(f"[refiner]   Git push 跳过: {e}")

        report("done", f"✓ Idea #{idea_id} 深化完成", 100)
    else:
        report("error", f"Idea #{idea_id} 深化失败", 100)

    return conn


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Paper Radar - Idea 深化")
    parser.add_argument("idea_id", type=int, help="要深化的 Idea ID")
    args = parser.parse_args()

    conn = init_db()
    refine(args.idea_id, conn)
    conn.close()
