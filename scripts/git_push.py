"""
scripts/git_push.py — 自动 git commit + push 到报告 repo

职责：
- 将生成的 Markdown 报告复制到报告 repo
- 更新报告 repo 的 README.md 索引
- git add → commit → push
"""

import shutil
from datetime import datetime
from pathlib import Path

import git


def push_report(config, report_path, topic):
    """
    将报告推送到 GitHub 报告 repo。

    Args:
        config: 配置字典
        report_path: 报告文件路径
        topic: 研究主题
    """
    repo_path = config.get("git", {}).get("reports_repo_path", "")
    if not repo_path:
        print("[git_push] reports_repo_path 为空，跳过 push")
        return

    repo_path = Path(repo_path)
    if not repo_path.exists():
        print(f"[git_push] 报告 repo 路径不存在: {repo_path}")
        return

    auto_push = config.get("git", {}).get("auto_push", True)

    # 创建主题子目录
    topic_dir = topic.replace(" ", "-").lower()
    dest_dir = repo_path / topic_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 复制报告
    dest_file = dest_dir / report_path.name
    shutil.copy2(str(report_path), str(dest_file))
    print(f"[git_push]   报告已复制到 {dest_file}")

    # 更新 README.md 索引
    readme_path = repo_path / "README.md"
    update_readme_index(readme_path, topic, report_path.name, topic_dir)

    # Git 操作
    try:
        repo = git.Repo(str(repo_path))

        repo.index.add([str(dest_file.relative_to(repo_path))])
        if readme_path.exists():
            repo.index.add([str(readme_path.relative_to(repo_path))])

        date = datetime.now().strftime("%Y-%m-%d")
        template = config.get("git", {}).get(
            "commit_message_template",
            "📄 Add {topic} report ({date})"
        )
        commit_msg = template.format(topic=topic, date=date)

        repo.index.commit(commit_msg)
        print(f"[git_push]   已提交: {commit_msg}")

        if auto_push:
            origin = repo.remote("origin")
            origin.push()
            print("[git_push] ✓ 已推送到远程仓库")
        else:
            print("[git_push]   auto_push 已关闭，跳过推送")

    except Exception as e:
        print(f"[git_push]   Git 操作失败: {e}")


def update_readme_index(readme_path, topic, filename, topic_dir):
    """更新报告 repo 的 README.md 索引"""
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
    else:
        content = "# Paper Radar Reports\n\n"

    # 查找或创建主题章节
    topic_header = f"## {topic}"
    link = f"- [{filename}]({topic_dir}/{filename})"

    if topic_header in content:
        # 在该章节下追加链接
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip() == topic_header:
                # 找到下一个空行或下一个 ## 标题
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("## ") or (lines[j].strip() == "" and j > i + 1):
                        insert_idx = j
                        break
                if insert_idx is None:
                    insert_idx = len(lines)
                break

        if insert_idx and link not in content:
            lines.insert(insert_idx, link)
            content = "\n".join(lines)
    else:
        content += f"\n{topic_header}\n\n{link}\n"

    readme_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    from pipeline.collector import load_config
    config = load_config()
    print("[git_push] 测试模式 — 请通过 pipeline 调用")
