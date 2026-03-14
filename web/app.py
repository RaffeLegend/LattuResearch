"""
web/app.py — FastAPI 后端

职责：
- 提供 REST API 接口
- SSE 推送 pipeline 实时进度
- 为 React 前端服务
"""

import asyncio
import json
import shutil
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.collector import (
    DB_PATH, init_db, load_config, load_prompts, collect, add_manual_papers
)
from pipeline.downloader import download
from pipeline.extractor import extract
from pipeline.embedder import embed
from pipeline.analyst import analyze
from pipeline.refiner import refine

app = FastAPI(title="Paper Radar API")

# CORS
config = load_config()
cors_origins = config.get("web", {}).get("cors_origins", ["http://localhost:3000"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局进度队列
progress_queues: list[asyncio.Queue] = []
pipeline_lock = threading.Lock()


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def broadcast_progress(step, status, message, progress):
    """广播进度到所有 SSE 客户端"""
    event = {
        "step": step,
        "status": status,
        "message": message,
        "progress": progress,
    }
    for q in progress_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ─── Request Models ──────────────────────────────

class RunRequest(BaseModel):
    topic: str
    time_range_months: int = 6

class UploadRequest(BaseModel):
    arxiv_ids: list[str]

class RefineRequest(BaseModel):
    idea_id: int


# ─── API Endpoints ───────────────────────────────

@app.post("/api/run")
async def api_run(req: RunRequest):
    """触发完整 pipeline"""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中")

    def run_pipeline():
        try:
            cfg = load_config()
            cfg["topic"] = req.topic
            cfg["time_range_months"] = req.time_range_months
            prompts = load_prompts()
            conn = init_db()

            collect(config=cfg, prompts=prompts, conn=conn, progress_callback=broadcast_progress)
            download(conn=conn, progress_callback=broadcast_progress)
            extract(conn=conn, config=cfg, prompts=prompts, progress_callback=broadcast_progress)
            embed(conn=conn, config=cfg, prompts=prompts, progress_callback=broadcast_progress)
            analyze(conn=conn, config=cfg, prompts=prompts, progress_callback=broadcast_progress)

            conn.close()
        except Exception as e:
            broadcast_progress("error", "error", str(e), 0)
        finally:
            pipeline_lock.release()

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return {"status": "started", "topic": req.topic}


@app.post("/api/upload")
async def api_upload(
    arxiv_ids: str = None,
    files: list[UploadFile] = File(default=None),
):
    """手动添加论文"""
    conn = init_db()

    added = []

    # arXiv IDs
    if arxiv_ids:
        ids = [i.strip() for i in arxiv_ids.split(",") if i.strip()]
        result = add_manual_papers(ids, conn)
        if result:
            added.extend(list(result.keys()))

    # PDF 文件上传
    if files:
        pdf_dir = ROOT / "storage" / "pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.filename and f.filename.endswith(".pdf"):
                dest = pdf_dir / f.filename
                content = await f.read()
                dest.write_bytes(content)
                added.append(f.filename)

    conn.close()
    return {"status": "ok", "added": added}


@app.get("/api/progress")
async def api_progress():
    """SSE 接口，实时推送 pipeline 进度"""
    queue = asyncio.Queue(maxsize=100)
    progress_queues.append(queue)

    async def event_generator():
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                yield {"event": "progress", "data": json.dumps(event)}
        except asyncio.TimeoutError:
            yield {"event": "ping", "data": "{}"}
        except asyncio.CancelledError:
            pass
        finally:
            if queue in progress_queues:
                progress_queues.remove(queue)

    return EventSourceResponse(event_generator())


@app.get("/api/papers")
async def api_papers(topic: str = None, source: str = "all"):
    """返回论文列表"""
    conn = get_db()
    query = "SELECT * FROM papers WHERE 1=1"
    params = []

    if source == "auto":
        query += " AND source = 'auto'"
    elif source == "manual":
        query += " AND source = 'manual'"

    query += " ORDER BY citation_velocity DESC"
    papers = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(p) for p in papers]


@app.get("/api/clusters")
async def api_clusters(topic: str = None):
    """返回聚类结果"""
    conn = get_db()

    clusters = conn.execute("""
        SELECT c.*, GROUP_CONCAT(pc.paper_id) as paper_ids
        FROM clusters c
        LEFT JOIN paper_clusters pc ON c.id = pc.cluster_id
        WHERE (? IS NULL OR c.topic = ?)
        GROUP BY c.id
    """, (topic, topic)).fetchall()

    # 获取 UMAP 坐标
    coords = conn.execute("""
        SELECT pc.paper_id, pc.cluster_id, pc.umap_x, pc.umap_y,
               p.title, p.venue, p.passed_by
        FROM paper_clusters pc
        JOIN papers p ON pc.paper_id = p.id
    """).fetchall()

    conn.close()

    return {
        "clusters": [dict(c) for c in clusters],
        "points": [dict(c) for c in coords],
    }


@app.get("/api/report")
async def api_report(topic: str = None):
    """返回报告 JSON 数据"""
    conn = get_db()

    # 获取统计数据
    total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    venue_count = conn.execute("SELECT COUNT(*) FROM papers WHERE passed_by LIKE '%venue%'").fetchone()[0]
    velocity_count = conn.execute("SELECT COUNT(*) FROM papers WHERE passed_by LIKE '%velocity%'").fetchone()[0]
    manual_count = conn.execute("SELECT COUNT(*) FROM papers WHERE source = 'manual'").fetchone()[0]
    cluster_count = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]

    # 获取 ideas
    ideas = conn.execute("SELECT * FROM ideas ORDER BY id DESC").fetchall()
    conn.close()

    return {
        "stats": {
            "total_papers": total,
            "venue_papers": venue_count,
            "velocity_papers": velocity_count,
            "manual_papers": manual_count,
            "cluster_count": cluster_count,
        },
        "ideas": [dict(i) for i in ideas],
    }


@app.get("/api/report/md")
async def api_report_md(topic: str = None):
    """返回 Markdown 原文"""
    reports_dir = ROOT / "output" / "reports"
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail="No reports found")

    # 找最新的报告
    reports = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if topic:
        topic_prefix = topic.replace(" ", "-")
        reports = [r for r in reports if r.name.startswith(topic_prefix)]

    if not reports:
        raise HTTPException(status_code=404, detail="No report found for this topic")

    return PlainTextResponse(reports[0].read_text(encoding="utf-8"))


@app.get("/api/ideas")
async def api_ideas(topic: str = None):
    """返回 Idea 列表"""
    conn = get_db()
    if topic:
        ideas = conn.execute("SELECT * FROM ideas WHERE topic = ? ORDER BY id DESC", (topic,)).fetchall()
    else:
        ideas = conn.execute("SELECT * FROM ideas ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(i) for i in ideas]


@app.post("/api/refine")
async def api_refine(req: RefineRequest):
    """触发 Idea 深化"""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中")

    def run_refine():
        try:
            cfg = load_config()
            prompts = load_prompts()
            conn = init_db()
            refine(
                idea_id=req.idea_id,
                conn=conn,
                config=cfg,
                prompts=prompts,
                progress_callback=broadcast_progress,
            )
            conn.close()
        except Exception as e:
            broadcast_progress("refiner", "error", str(e), 0)
        finally:
            pipeline_lock.release()

    thread = threading.Thread(target=run_refine, daemon=True)
    thread.start()
    return {"status": "started", "idea_id": req.idea_id}


@app.get("/api/refinement/{idea_id}")
async def api_refinement(idea_id: int):
    """返回 Idea 深化报告"""
    conn = get_db()
    refinement = conn.execute(
        "SELECT * FROM idea_refinements WHERE idea_id = ? ORDER BY id DESC LIMIT 1",
        (idea_id,)
    ).fetchone()

    papers = conn.execute(
        "SELECT * FROM refinement_papers WHERE idea_id = ?",
        (idea_id,)
    ).fetchall()

    conn.close()

    if not refinement:
        raise HTTPException(status_code=404, detail="Refinement not found")

    return {
        "refinement": dict(refinement),
        "papers": [dict(p) for p in papers],
    }


if __name__ == "__main__":
    import uvicorn
    host = config.get("web", {}).get("host", "0.0.0.0")
    port = config.get("web", {}).get("port", 8000)
    uvicorn.run(app, host=host, port=port)
