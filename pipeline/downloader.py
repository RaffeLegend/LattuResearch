"""
pipeline/downloader.py — 第二阶段：PDF 下载与段落提取

职责：
- 下载 PDF 到 storage/pdfs/
- 用 pymupdf 提取关键段落（Abstract, Introduction, Method, Conclusion, Limitations）
- fallback：全文前1/4+后1/4
- 将提取结果存入 paper_sections 表
"""

import sqlite3
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # pymupdf
import requests

from pipeline.collector import DB_PATH, ROOT, init_db

PDF_DIR = ROOT / "storage" / "pdfs"

# 段落识别关键词
SECTION_KEYWORDS = {
    "abstract": ["abstract"],
    "introduction": ["introduction"],
    "method": ["method", "methodology", "approach", "proposed method", "our method", "our approach"],
    "conclusion": ["conclusion", "conclusions", "concluding remarks"],
    "limitation": ["limitation", "limitations", "future work", "future directions"],
}


def download_pdf(paper_id, pdf_url):
    """下载单篇论文 PDF"""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = PDF_DIR / f"{paper_id.replace('/', '_')}.pdf"

    if pdf_path.exists():
        return pdf_path

    try:
        resp = requests.get(pdf_url, timeout=120)
        resp.raise_for_status()
        pdf_path.write_bytes(resp.content)
        return pdf_path
    except Exception as e:
        print(f"[downloader]   PDF 下载失败 {paper_id}: {e}")
        return None


def extract_sections_structured(pdf_path):
    """通过字体大小和关键词识别章节标题，提取关键段落"""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return None

    # 收集所有文本块及其字体大小
    blocks = []
    for page in doc:
        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 只处理文本块
                continue
            for line in block.get("lines", []):
                line_text = ""
                font_sizes = []
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                    font_sizes.append(span.get("size", 10))
                if line_text.strip():
                    avg_size = statistics.mean(font_sizes) if font_sizes else 10
                    blocks.append({"text": line_text.strip(), "size": avg_size})

    doc.close()

    if not blocks:
        return None

    # 计算正文平均字体大小（取中位数更鲁棒）
    all_sizes = [b["size"] for b in blocks]
    body_size = statistics.median(all_sizes)
    title_threshold = body_size * 1.2

    # 识别章节标题及其位置
    sections_found = {}
    current_section = None
    current_text = []

    for block in blocks:
        text = block["text"]
        size = block["size"]

        # 检测是否是标题行
        is_title = size >= title_threshold or (
            len(text.split()) <= 6 and text.strip().rstrip(".").lower() in _flatten_keywords()
        )

        if is_title:
            # 保存之前的章节内容
            if current_section and current_text:
                section_key = _match_section(current_section)
                if section_key and section_key not in sections_found:
                    sections_found[section_key] = "\n".join(current_text)

            # 开始新的章节
            current_section = text
            current_text = []
        else:
            current_text.append(text)

    # 保存最后一个章节
    if current_section and current_text:
        section_key = _match_section(current_section)
        if section_key and section_key not in sections_found:
            sections_found[section_key] = "\n".join(current_text)

    # Introduction 只取前两段
    if "introduction" in sections_found:
        paragraphs = sections_found["introduction"].split("\n\n")
        sections_found["introduction"] = "\n\n".join(paragraphs[:2])

    return sections_found if sections_found else None


def _flatten_keywords():
    """扁平化所有关键词"""
    all_kw = []
    for kws in SECTION_KEYWORDS.values():
        all_kw.extend(kws)
    return all_kw


def _match_section(title_text):
    """匹配标题文本到章节类型"""
    title_lower = title_text.strip().lower()
    # 移除编号（如 "1.", "1 ", "I.", "II."）
    import re
    title_lower = re.sub(r'^[\dIVXivx]+[\.\s]+', '', title_lower).strip()

    for section_key, keywords in SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return section_key
    return None


def extract_sections_fallback(pdf_path):
    """Fallback：将全文按 token 分块，取前1/4和后1/4"""
    try:
        doc = fitz.open(str(pdf_path))
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"
        doc.close()

        if not full_text.strip():
            return None

        words = full_text.split()
        quarter = len(words) // 4
        raw_text = " ".join(words[:quarter]) + "\n...\n" + " ".join(words[-quarter:])

        return {"raw_text": raw_text}
    except Exception:
        return None


def process_paper(paper_id, pdf_url, conn):
    """处理单篇论文：下载 + 提取段落"""
    pdf_path = download_pdf(paper_id, pdf_url)
    if not pdf_path:
        return False

    # 尝试结构化提取
    sections = extract_sections_structured(pdf_path)
    extraction_method = "structured"

    if not sections:
        sections = extract_sections_fallback(pdf_path)
        extraction_method = "fallback"

    if not sections:
        return False

    # 写入数据库
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO paper_sections
        (paper_id, abstract, introduction, method, conclusion, limitation, raw_text, extraction_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper_id,
        sections.get("abstract", ""),
        sections.get("introduction", ""),
        sections.get("method", ""),
        sections.get("conclusion", ""),
        sections.get("limitation", ""),
        sections.get("raw_text", ""),
        extraction_method,
    ))
    c.execute("UPDATE papers SET status = 'downloaded' WHERE id = ?", (paper_id,))
    conn.commit()
    return True


def download(conn=None, progress_callback=None):
    """
    执行完整下载和段落提取流程。

    Args:
        conn: SQLite 连接
        progress_callback: 进度回调函数 (step, status, message, progress)
    """
    if conn is None:
        conn = init_db()

    def report(status, message, progress):
        if progress_callback:
            progress_callback("downloader", status, message, progress)
        print(f"[downloader] {message}")

    report("running", "开始下载 PDF...", 0)

    papers = conn.execute(
        "SELECT id, pdf_url FROM papers WHERE status = 'collected'"
    ).fetchall()

    if not papers:
        report("done", "没有需要下载的论文", 100)
        return conn

    total = len(papers)
    success = 0

    for i, (paper_id, pdf_url) in enumerate(papers):
        try:
            if process_paper(paper_id, pdf_url, conn):
                success += 1
        except Exception as e:
            print(f"[downloader]   处理失败 {paper_id}: {e}")

        progress = int((i + 1) / total * 100)
        if (i + 1) % 5 == 0 or (i + 1) == total:
            report("running", f"已处理 {i + 1}/{total} 篇", progress)

    report("done", f"✓ 完成 {success}/{total} 篇论文下载与段落提取", 100)
    return conn


if __name__ == "__main__":
    conn = init_db()
    download(conn)
    conn.close()
