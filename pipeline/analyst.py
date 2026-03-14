"""
pipeline/analyst.py — 第五阶段：趋势分析、盲区发现、Idea 生成

职责：
- 趋势判断预处理（classify_trend）
- Claude 趋势分析（Sonnet）
- 盲区发现
- Idea 生成
- 报告渲染（Markdown）
- 触发 Git Push
"""

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pipeline.collector import (
    ROOT, init_db, load_config, load_prompts, get_anthropic_client
)

REPORTS_DIR = ROOT / "output" / "reports"


def classify_trend(papers_by_month):
    """基于月度论文数分类趋势"""
    if len(papers_by_month) < 6:
        papers_by_month = [0] * (6 - len(papers_by_month)) + papers_by_month

    recent_3m = sum(papers_by_month[-3:])
    prev_3m = sum(papers_by_month[-6:-3])

    if prev_3m == 0:
        return "emerging"
    ratio = recent_3m / prev_3m
    if ratio > 1.5 and recent_3m >= 5:
        return "emerging"
    if recent_3m >= 10:
        return "hot"
    if ratio < 0.5:
        return "declining"
    return "stable"


def get_cluster_time_distribution(conn, topic):
    """获取每个 cluster 的月度论文分布"""
    rows = conn.execute("""
        SELECT c.id, c.name, p.published_date
        FROM clusters c
        JOIN paper_clusters pc ON c.id = pc.cluster_id
        JOIN papers p ON pc.paper_id = p.id
        WHERE c.topic = ?
    """, (topic,)).fetchall()

    cluster_months = defaultdict(lambda: defaultdict(int))
    cluster_names = {}

    for cluster_id, cluster_name, pub_date in rows:
        cluster_names[cluster_id] = cluster_name
        if pub_date:
            month_key = pub_date[:7]  # YYYY-MM
            cluster_months[cluster_id][month_key] += 1

    return cluster_names, cluster_months


def update_cluster_trends(conn, topic):
    """计算并更新各 cluster 的趋势"""
    cluster_names, cluster_months = get_cluster_time_distribution(conn, topic)

    # 获取所有月份并排序
    all_months = set()
    for months in cluster_months.values():
        all_months.update(months.keys())
    sorted_months = sorted(all_months)

    trends = {}
    for cluster_id, months in cluster_months.items():
        papers_by_month = [months.get(m, 0) for m in sorted_months]
        trend = classify_trend(papers_by_month)
        trends[cluster_id] = trend
        conn.execute(
            "UPDATE clusters SET trend = ? WHERE id = ?",
            (trend, cluster_id)
        )
    conn.commit()

    return trends, cluster_names, cluster_months, sorted_months


def run_trend_analysis(conn, config, prompts, topic):
    """调用 Claude Sonnet 做趋势分析"""
    client = get_anthropic_client(config)
    model = config["models"]["analysis"]
    prompt_cfg = prompts["trend_analysis"]

    # 准备数据
    clusters = conn.execute("""
        SELECT id, name, summary, core_methods, paper_count, trend
        FROM clusters WHERE topic = ?
    """, (topic,)).fetchall()

    clusters_data = "\n".join(
        f"- {r[1]} (trend: {r[5]}, papers: {r[4]}): {r[2]}"
        for r in clusters
    )

    _, cluster_months = get_cluster_time_distribution(conn, topic)
    cluster_names_map = {r[0]: r[1] for r in clusters}

    all_months = set()
    for months in cluster_months.values():
        all_months.update(months.keys())
    sorted_months = sorted(all_months)

    time_dist = ""
    for cid, months in cluster_months.items():
        name = cluster_names_map.get(cid, f"Cluster {cid}")
        counts = [str(months.get(m, 0)) for m in sorted_months]
        time_dist += f"- {name}: {', '.join(f'{m}:{c}' for m, c in zip(sorted_months, counts))}\n"

    time_range = f"Last {config.get('time_range_months', 6)} months"

    user_msg = prompt_cfg["user"].format(
        topic=topic,
        time_range=time_range,
        clusters_data=clusters_data,
        time_distribution=time_dist or "No time distribution data available",
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
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
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[analyst] 趋势分析失败: {e}")
                return {"overall_summary": "Analysis unavailable", "hot_directions": [], "declining_directions": [], "emerging_directions": []}


def run_blind_spot_discovery(conn, config, prompts, topic):
    """调用 Claude Sonnet 做盲区发现"""
    client = get_anthropic_client(config)
    model = config["models"]["analysis"]
    prompt_cfg = prompts["blind_spot_discovery"]

    # 汇总所有论文的 limitations 和 future_work
    analyses = conn.execute("""
        SELECT pa.limitations, pa.future_work_mentioned
        FROM paper_analysis pa
        JOIN papers p ON pa.paper_id = p.id
        WHERE p.status = 'embedded'
    """).fetchall()

    all_limitations = []
    all_future_work = []
    for lim, fw in analyses:
        try:
            all_limitations.extend(json.loads(lim) if lim else [])
        except json.JSONDecodeError:
            pass
        try:
            all_future_work.extend(json.loads(fw) if fw else [])
        except json.JSONDecodeError:
            pass

    clusters = conn.execute(
        "SELECT name, summary FROM clusters WHERE topic = ?", (topic,)
    ).fetchall()
    cluster_summaries = "\n".join(f"- {r[0]}: {r[1]}" for r in clusters)

    user_msg = prompt_cfg["user"].format(
        topic=topic,
        paper_count=len(analyses),
        all_limitations="\n".join(f"- {l}" for l in all_limitations[:100]),
        all_future_work="\n".join(f"- {f}" for f in all_future_work[:100]),
        cluster_summaries=cluster_summaries,
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
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
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[analyst] 盲区发现失败: {e}")
                return {"blind_spots": []}


def run_idea_generation(conn, config, prompts, topic, blind_spots_data):
    """调用 Claude Sonnet 生成研究 Idea"""
    client = get_anthropic_client(config)
    model = config["models"]["analysis"]
    prompt_cfg = prompts["idea_generation"]

    # 汇总方法摘要
    clusters = conn.execute("""
        SELECT name, core_methods, summary
        FROM clusters WHERE topic = ?
    """, (topic,)).fetchall()

    methods_summary = "\n".join(
        f"- {r[0]}: methods={r[1]}, {r[2]}"
        for r in clusters
    )

    # 高分论文
    notable = conn.execute("""
        SELECT p.title, p.venue, pa.novelty_score, pa.key_contribution
        FROM papers p
        JOIN paper_analysis pa ON p.id = pa.paper_id
        WHERE p.status = 'embedded'
        ORDER BY pa.novelty_score DESC
        LIMIT 10
    """).fetchall()

    notable_papers = "\n".join(
        f"- {r[0]} ({r[1] or 'arXiv'}, novelty={r[2]}): {r[3]}"
        for r in notable
    )

    user_msg = prompt_cfg["user"].format(
        topic=topic,
        blind_spots=json.dumps(blind_spots_data.get("blind_spots", []), indent=2),
        methods_summary=methods_summary,
        notable_papers=notable_papers,
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
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
            return json.loads(text)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[analyst] Idea 生成失败: {e}")
                return {"ideas": []}


def save_ideas(conn, topic, ideas_data):
    """保存 Ideas 到数据库"""
    run_date = datetime.now().strftime("%Y-%m-%d")
    c = conn.cursor()

    for idea in ideas_data.get("ideas", []):
        c.execute("""
            INSERT INTO ideas
            (topic, run_date, title, problem_statement, addresses_blind_spot,
             proposed_approach, key_hypothesis, related_work,
             difference_from_existing, experiment_design, potential_risks,
             novelty_assessment, estimated_difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            topic, run_date,
            idea.get("title", ""),
            idea.get("problem_statement", ""),
            idea.get("addresses_blind_spot", ""),
            idea.get("proposed_approach", ""),
            idea.get("key_hypothesis", ""),
            json.dumps(idea.get("related_work", [])),
            idea.get("difference_from_existing", ""),
            idea.get("experiment_design", ""),
            json.dumps(idea.get("potential_risks", [])),
            idea.get("novelty_assessment", "moderate"),
            idea.get("estimated_difficulty", "medium"),
        ))
    conn.commit()
    print(f"[analyst]   已保存 {len(ideas_data.get('ideas', []))} 个 Idea")


def generate_report(config, prompts, topic, trend_data, blind_spots_data, ideas_data, conn):
    """调用 Claude Sonnet 生成 Markdown 报告"""
    client = get_anthropic_client(config)
    model = config["models"]["analysis"]
    prompt_cfg = prompts["report_generation"]

    paper_count = conn.execute("SELECT COUNT(*) FROM papers WHERE status = 'embedded'").fetchone()[0]
    cluster_count = conn.execute("SELECT COUNT(*) FROM clusters WHERE topic = ?", (topic,)).fetchone()[0]
    time_range = f"Last {config.get('time_range_months', 6)} months"
    date = datetime.now().strftime("%Y-%m-%d")

    # 高分论文
    top_papers = conn.execute("""
        SELECT p.title, p.venue, pa.novelty_score, pa.key_contribution
        FROM papers p
        JOIN paper_analysis pa ON p.id = pa.paper_id
        ORDER BY pa.novelty_score DESC
        LIMIT 10
    """).fetchall()

    top_papers_str = "\n".join(
        f"- {r[0]} | {r[1] or 'arXiv'} | novelty={r[2]} | {r[3]}"
        for r in top_papers
    )

    user_msg = prompt_cfg["user"].format(
        topic=topic,
        time_range=time_range,
        paper_count=paper_count,
        cluster_count=cluster_count,
        trend_data=json.dumps(trend_data, indent=2),
        blind_spots_data=json.dumps(blind_spots_data, indent=2),
        ideas_data=json.dumps(ideas_data, indent=2),
        top_papers=top_papers_str,
        date=date,
    )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=prompt_cfg["system"],
                messages=[{"role": "user", "content": user_msg}],
                timeout=120,
            )
            return response.content[0].text.strip()
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[analyst] 报告生成失败: {e}")
                return f"# {topic} Report\n\nReport generation failed."


def save_report(topic, report_md):
    """保存 Markdown 报告"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m")
    filename = f"{topic.replace(' ', '-')}_{date_str}.md"
    report_path = REPORTS_DIR / filename
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[analyst]   报告已保存: {report_path}")
    return report_path


def analyze(conn=None, config=None, prompts=None, progress_callback=None):
    """
    执行完整分析流程。

    Args:
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

    topic = config["topic"]

    def report(status, message, progress):
        if progress_callback:
            progress_callback("analyst", status, message, progress)
        print(f"[analyst] {message}")

    report("running", "开始分析...", 0)

    # Step 1: 趋势预处理
    report("running", "正在计算趋势...", 10)
    trends, cluster_names, cluster_months, sorted_months = update_cluster_trends(conn, topic)

    # Step 2: Claude 趋势分析
    report("running", "正在生成趋势分析...", 20)
    trend_data = run_trend_analysis(conn, config, prompts, topic)

    # Step 3: 盲区发现
    report("running", "正在发现研究盲区...", 40)
    blind_spots_data = run_blind_spot_discovery(conn, config, prompts, topic)

    # Step 4: Idea 生成
    report("running", "正在生成研究 Idea...", 60)
    ideas_data = run_idea_generation(conn, config, prompts, topic, blind_spots_data)
    save_ideas(conn, topic, ideas_data)

    # Step 5: 报告渲染
    report("running", "正在生成 Markdown 报告...", 80)
    report_md = generate_report(config, prompts, topic, trend_data, blind_spots_data, ideas_data, conn)
    report_path = save_report(topic, report_md)

    # Step 6: Git Push
    report("running", "正在推送报告...", 95)
    try:
        from scripts.git_push import push_report
        push_report(config, report_path, topic)
    except Exception as e:
        print(f"[analyst]   Git push 跳过: {e}")

    report("done", f"✓ 分析完成，报告已保存", 100)
    return conn


if __name__ == "__main__":
    conn = init_db()
    analyze(conn)
    conn.close()
