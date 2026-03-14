"""
pipeline/embedder.py — 第四阶段：向量化与聚类

职责：
- 拼接 research_problem + core_method 作为向量化文本
- 调用 OpenAI embedding 或本地 sentence-transformers
- 存入 ChromaDB
- 用 UMAP 降维到 2D，用 HDBSCAN 聚类
- 对每个 cluster 调用 Claude Haiku 生成名称和摘要
"""

import json
import os
import time
from pathlib import Path

import numpy as np

from pipeline.collector import (
    ROOT, init_db, load_config, load_prompts, get_anthropic_client
)

VECTORS_DIR = ROOT / "storage" / "vectors"


def get_embeddings_openai(texts, config):
    """使用 OpenAI API 获取 embeddings"""
    import openai
    api_key = os.environ.get("OPENAI_API_KEY") or config.get("openai_api_key")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 未设置")
    client = openai.OpenAI(api_key=api_key)
    model = config["embedding"]["model"]

    embeddings = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(input=batch, model=model)
        embeddings.extend([d.embedding for d in response.data])

    return np.array(embeddings)


def get_embeddings_local(texts, config):
    """使用本地 sentence-transformers 获取 embeddings"""
    from sentence_transformers import SentenceTransformer
    model_name = config["embedding"]["local_model"]
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=True)
    return np.array(embeddings)


def get_embeddings(texts, config):
    """根据配置选择 embedding 方式"""
    provider = config["embedding"]["provider"]
    if provider == "openai":
        try:
            return get_embeddings_openai(texts, config)
        except Exception as e:
            print(f"[embedder] OpenAI embedding 失败，切换到本地模型: {e}")
            return get_embeddings_local(texts, config)
    else:
        return get_embeddings_local(texts, config)


def store_in_chromadb(paper_ids, texts, embeddings, topic):
    """存入 ChromaDB"""
    import chromadb
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTORS_DIR))

    collection_name = topic.replace(" ", "_").lower()[:63]
    # 如果集合已存在则删除重建
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.create_collection(name=collection_name)
    collection.add(
        ids=paper_ids,
        documents=texts,
        embeddings=embeddings.tolist(),
    )
    print(f"[embedder]   ChromaDB 已存储 {len(paper_ids)} 篇论文")
    return collection


def cluster_papers(embeddings, min_cluster_size=3):
    """UMAP 降维 + HDBSCAN 聚类"""
    import umap
    import hdbscan

    n_samples = len(embeddings)
    if n_samples < 5:
        # 样本太少，全部归为一类
        umap_coords = np.random.randn(n_samples, 2) * 0.1
        labels = np.zeros(n_samples, dtype=int)
        return umap_coords, labels

    # UMAP 降维
    n_neighbors = min(15, n_samples - 1)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=n_neighbors,
        min_dist=0.1,
        random_state=42,
    )
    umap_coords = reducer.fit_transform(embeddings)

    # HDBSCAN 聚类
    min_cs = min(min_cluster_size, max(2, n_samples // 5))
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cs,
        min_samples=1,
    )
    labels = clusterer.fit_predict(umap_coords)

    # 如果所有点都是噪声（-1），全部归为一类
    if all(l == -1 for l in labels):
        labels = np.zeros(n_samples, dtype=int)

    n_clusters = len(set(labels) - {-1})
    print(f"[embedder]   UMAP + HDBSCAN: {n_clusters} 个聚类")
    return umap_coords, labels


def name_clusters(conn, cluster_data, config, prompts):
    """对每个 cluster 调用 Claude Haiku 生成名称和摘要"""
    client = get_anthropic_client(config)
    model = config["models"]["extraction"]
    prompt_cfg = prompts["cluster_naming"]

    results = []
    for cluster_id, papers in cluster_data.items():
        if cluster_id == -1:  # 跳过噪声点
            continue

        papers_list = "\n".join(
            f"- Title: {p['title']} | Problem: {p.get('research_problem', 'N/A')}"
            for p in papers
        )

        user_msg = prompt_cfg["user"].format(papers_list=papers_list)

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
                result["cluster_id"] = cluster_id
                result["paper_count"] = len(papers)
                results.append(result)
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    # fallback 名称
                    results.append({
                        "cluster_id": cluster_id,
                        "name": f"Cluster {cluster_id}",
                        "summary": "Auto-generated cluster",
                        "core_methods": [],
                        "open_questions": [],
                        "paper_count": len(papers),
                    })

        time.sleep(0.5)

    return results


def save_clusters(conn, topic, cluster_results, paper_cluster_map, umap_coords):
    """保存聚类结果到数据库"""
    c = conn.cursor()

    # 清除旧的聚类数据
    c.execute("DELETE FROM paper_clusters WHERE paper_id IN (SELECT id FROM papers)")
    c.execute("DELETE FROM clusters WHERE topic = ?", (topic,))

    cluster_id_map = {}
    for cr in cluster_results:
        c.execute("""
            INSERT INTO clusters (topic, name, summary, core_methods, open_questions, paper_count, trend)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            topic,
            cr["name"],
            cr.get("summary", ""),
            json.dumps(cr.get("core_methods", [])),
            json.dumps(cr.get("open_questions", [])),
            cr["paper_count"],
            "stable",  # 趋势待 analyst 更新
        ))
        cluster_id_map[cr["cluster_id"]] = c.lastrowid

    # 保存论文-聚类关系
    for paper_id, cluster_label in paper_cluster_map.items():
        db_cluster_id = cluster_id_map.get(cluster_label)
        if db_cluster_id is None:
            # 噪声点归入最大的 cluster
            if cluster_id_map:
                db_cluster_id = list(cluster_id_map.values())[0]
            else:
                continue
        coords = umap_coords.get(paper_id, (0.0, 0.0))
        c.execute("""
            INSERT INTO paper_clusters (paper_id, cluster_id, umap_x, umap_y)
            VALUES (?, ?, ?, ?)
        """, (paper_id, db_cluster_id, float(coords[0]), float(coords[1])))

    conn.commit()
    print(f"[embedder]   已保存 {len(cluster_results)} 个聚类到数据库")


def embed(conn=None, config=None, prompts=None, progress_callback=None):
    """
    执行完整向量化与聚类流程。

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
            progress_callback("embedder", status, message, progress)
        print(f"[embedder] {message}")

    report("running", "开始向量化与聚类...", 0)

    # 读取已解析的论文
    papers = conn.execute("""
        SELECT p.id, p.title, pa.research_problem, pa.core_method
        FROM papers p
        JOIN paper_analysis pa ON p.id = pa.paper_id
        WHERE p.status = 'parsed'
    """).fetchall()

    if not papers:
        report("done", "没有需要向量化的论文", 100)
        return conn

    paper_ids = [p[0] for p in papers]
    titles = [p[1] for p in papers]
    texts = [
        f"{p[2] or ''} {p[3] or ''}"
        for p in papers
    ]

    # Step 1: 获取 embeddings
    report("running", f"正在向量化 {len(papers)} 篇论文...", 20)
    embeddings = get_embeddings(texts, config)

    # Step 2: 存入 ChromaDB
    report("running", "正在存入 ChromaDB...", 40)
    topic = config["topic"]
    store_in_chromadb(paper_ids, texts, embeddings, topic)

    # Step 3: UMAP + HDBSCAN
    report("running", "正在聚类...", 50)
    umap_coords, labels = cluster_papers(embeddings)

    # 构建聚类数据
    cluster_data = {}
    paper_cluster_map = {}
    umap_coords_map = {}
    for i, paper_id in enumerate(paper_ids):
        label = int(labels[i])
        paper_cluster_map[paper_id] = label
        umap_coords_map[paper_id] = (umap_coords[i][0], umap_coords[i][1])
        if label not in cluster_data:
            cluster_data[label] = []
        cluster_data[label].append({
            "paper_id": paper_id,
            "title": titles[i],
            "research_problem": papers[i][2],
        })

    # Step 4: Claude 命名
    report("running", "正在为聚类生成名称...", 70)
    cluster_results = name_clusters(conn, cluster_data, config, prompts)

    # Step 5: 保存结果
    report("running", "正在保存聚类结果...", 90)
    save_clusters(conn, topic, cluster_results, paper_cluster_map, umap_coords_map)

    # 更新论文状态
    for paper_id in paper_ids:
        conn.execute("UPDATE papers SET status = 'embedded' WHERE id = ?", (paper_id,))
    conn.commit()

    report("done", f"✓ 完成 {len(papers)} 篇论文向量化，{len(cluster_results)} 个聚类", 100)
    return conn


if __name__ == "__main__":
    conn = init_db()
    embed(conn)
    conn.close()
