"""
pipeline/extractor.py — 第三阶段：Claude 结构化解析

职责：
- 调用 Claude Haiku 对每篇论文做结构化解析
- 从 prompts.yaml 读取 paper_extraction 模板
- 解析返回的 JSON 写入 paper_analysis 表
"""

import json
import time

from pipeline.collector import (
    init_db, load_config, load_prompts, get_anthropic_client
)


def extract_paper(client, model, prompt_cfg, paper_id, title, sections):
    """对单篇论文做结构化解析"""
    user_msg = prompt_cfg["user"].format(
        title=title,
        abstract=sections.get("abstract", "N/A"),
        introduction=sections.get("introduction", "N/A"),
        method=sections.get("method", "N/A"),
        conclusion=sections.get("conclusion", "N/A"),
        limitation=sections.get("limitation", "N/A"),
    )

    # 如果所有段落都为空，使用 raw_text
    if all(not sections.get(k) for k in ["abstract", "introduction", "method", "conclusion", "limitation"]):
        raw = sections.get("raw_text", "")
        if raw:
            user_msg = prompt_cfg["user"].format(
                title=title,
                abstract="N/A",
                introduction=raw[:3000],
                method="N/A",
                conclusion=raw[-3000:] if len(raw) > 3000 else "N/A",
                limitation="N/A",
            )

    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=prompt_cfg["system"],
                messages=[{"role": "user", "content": user_msg}],
                timeout=60,
            )
            text = response.content[0].text.strip()

            # 提取 JSON（可能被包裹在 markdown 代码块中）
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)
            return result
        except Exception as e:
            if attempt < 2:
                wait = 2 ** attempt
                print(f"[extractor]   解析失败 {paper_id}，{wait}s 后重试: {e}")
                time.sleep(wait)
            else:
                print(f"[extractor]   解析最终失败 {paper_id}: {e}")
                return None


def save_analysis(conn, paper_id, analysis):
    """保存解析结果到数据库"""
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO paper_analysis
        (paper_id, research_problem, core_method, key_contribution,
         baselines_beaten, limitations, future_work_mentioned,
         sub_field_tags, novelty_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper_id,
        analysis.get("research_problem", ""),
        analysis.get("core_method", ""),
        analysis.get("key_contribution", ""),
        json.dumps(analysis.get("baselines_beaten", [])),
        json.dumps(analysis.get("limitations", [])),
        json.dumps(analysis.get("future_work_mentioned", [])),
        json.dumps(analysis.get("sub_field_tags", [])),
        analysis.get("novelty_score", 5),
    ))
    c.execute("UPDATE papers SET status = 'parsed' WHERE id = ?", (paper_id,))
    conn.commit()


def extract(conn=None, config=None, prompts=None, progress_callback=None):
    """
    执行完整结构化解析流程。

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

    def report(status, message, progress):
        if progress_callback:
            progress_callback("extractor", status, message, progress)
        print(f"[extractor] {message}")

    report("running", "开始结构化解析...", 0)

    client = get_anthropic_client(config)
    model = config["models"]["extraction"]
    prompt_cfg = prompts["paper_extraction"]

    # 查询已下载但未解析的论文
    papers = conn.execute("""
        SELECT p.id, p.title, ps.abstract, ps.introduction, ps.method,
               ps.conclusion, ps.limitation, ps.raw_text
        FROM papers p
        JOIN paper_sections ps ON p.id = ps.paper_id
        WHERE p.status = 'downloaded'
    """).fetchall()

    if not papers:
        report("done", "没有需要解析的论文", 100)
        return conn

    total = len(papers)
    success = 0

    for i, row in enumerate(papers):
        paper_id, title = row[0], row[1]
        sections = {
            "abstract": row[2] or "",
            "introduction": row[3] or "",
            "method": row[4] or "",
            "conclusion": row[5] or "",
            "limitation": row[6] or "",
            "raw_text": row[7] or "",
        }

        try:
            analysis = extract_paper(client, model, prompt_cfg, paper_id, title, sections)
            if analysis:
                save_analysis(conn, paper_id, analysis)
                success += 1
        except Exception as e:
            print(f"[extractor]   处理失败 {paper_id}: {e}")

        progress = int((i + 1) / total * 100)
        if (i + 1) % 5 == 0 or (i + 1) == total:
            report("running", f"已解析 {i + 1}/{total} 篇", progress)

        # 避免 API 速率限制
        time.sleep(0.5)

    report("done", f"✓ 完成 {success}/{total} 篇论文结构化解析", 100)
    return conn


if __name__ == "__main__":
    conn = init_db()
    extract(conn)
    conn.close()
