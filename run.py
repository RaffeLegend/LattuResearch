"""
run.py — Paper Radar 一键入口

用法:
  python run.py                              # 使用 config.yaml 默认配置运行完整 pipeline
  python run.py --topic "offline RL"         # 指定主题
  python run.py --papers 2401.12345,2402.00001  # 手动添加论文
  python run.py --refine 1                   # 深化指定 Idea
"""

import argparse
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipeline.collector import load_config, load_prompts, init_db, collect
from pipeline.downloader import download
from pipeline.extractor import extract
from pipeline.embedder import embed
from pipeline.analyst import analyze
from pipeline.refiner import refine


def run_full_pipeline(config, prompts, manual_ids=None):
    """运行完整 pipeline"""
    print("=" * 60)
    print(f"  Paper Radar — {config['topic']}")
    print(f"  时间范围: {config.get('time_range_months', 6)} 个月")
    print("=" * 60)

    # 初始化数据库
    conn = init_db()

    try:
        # Stage 1: 采集
        print("\n" + "─" * 40)
        print("  Stage 1/5: 论文采集")
        print("─" * 40)
        collect(config=config, prompts=prompts, manual_ids=manual_ids, conn=conn)

        # Stage 2: 下载
        print("\n" + "─" * 40)
        print("  Stage 2/5: PDF 下载与段落提取")
        print("─" * 40)
        download(conn=conn)

        # Stage 3: 结构化解析
        print("\n" + "─" * 40)
        print("  Stage 3/5: Claude 结构化解析")
        print("─" * 40)
        extract(conn=conn, config=config, prompts=prompts)

        # Stage 4: 向量化与聚类
        print("\n" + "─" * 40)
        print("  Stage 4/5: 向量化与聚类")
        print("─" * 40)
        embed(conn=conn, config=config, prompts=prompts)

        # Stage 5: 趋势分析与报告
        print("\n" + "─" * 40)
        print("  Stage 5/5: 趋势分析与报告生成")
        print("─" * 40)
        analyze(conn=conn, config=config, prompts=prompts)

        print("\n" + "=" * 60)
        print("  Pipeline 完成！")
        print("=" * 60)

    finally:
        conn.close()


def run_refine(config, prompts, idea_id):
    """运行 Idea 深化流程"""
    print("=" * 60)
    print(f"  Paper Radar — Idea 深化 #{idea_id}")
    print("=" * 60)

    conn = init_db()
    try:
        refine(idea_id=idea_id, conn=conn, config=config, prompts=prompts)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Paper Radar — 迭代式顶会论文追踪与研究洞察生成系统"
    )
    parser.add_argument(
        "--topic", type=str, default=None,
        help="研究主题（覆盖 config.yaml 中的 topic）"
    )
    parser.add_argument(
        "--papers", type=str, default=None,
        help="手动指定 arXiv ID（逗号分隔，如 2401.12345,2402.00001）"
    )
    parser.add_argument(
        "--refine", type=int, default=None,
        help="深化指定 Idea（传入 idea_id）"
    )
    parser.add_argument(
        "--months", type=int, default=None,
        help="时间范围（月数，覆盖 config.yaml）"
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config()
    prompts = load_prompts()

    # 覆盖配置
    if args.topic:
        config["topic"] = args.topic
    if args.months:
        config["time_range_months"] = args.months

    # 分支逻辑
    if args.refine is not None:
        run_refine(config, prompts, args.refine)
    else:
        manual_ids = args.papers.split(",") if args.papers else None
        run_full_pipeline(config, prompts, manual_ids=manual_ids)


if __name__ == "__main__":
    main()
