#!/usr/bin/env bash
# Paper Radar 启动脚本

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ─── 颜色 ───────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── 帮助信息 ────────────────────────────
usage() {
    echo -e "${CYAN}Paper Radar${NC} — 迭代式顶会论文追踪与研究洞察生成系统"
    echo ""
    echo "用法: ./start.sh [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  install       安装 Python + Node 依赖"
    echo "  run           运行完整 pipeline（默认）"
    echo "  web           启动 Web UI（后端 + 前端）"
    echo "  api           只启动后端 API"
    echo "  refine <id>   深化指定 Idea"
    echo ""
    echo "选项:"
    echo "  --topic <t>   指定研究主题"
    echo "  --months <n>  时间范围（月）"
    echo "  --papers <ids> 手动添加论文（arXiv ID，逗号分隔）"
    echo ""
    echo "示例:"
    echo "  ./start.sh install"
    echo "  ./start.sh run --topic 'offline reinforcement learning'"
    echo "  ./start.sh web"
    echo "  ./start.sh refine 1"
}

# ─── 环境检查 ─────────────────────────────
check_env() {
    # 检查环境变量或 config.yaml 中是否配置了 key
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        if grep -q 'anthropic_api_key: "sk-' "$ROOT/config.yaml" 2>/dev/null; then
            echo -e "${GREEN}[ok]${NC} ANTHROPIC_API_KEY 已在 config.yaml 中配置"
        else
            echo -e "${YELLOW}[warn]${NC} ANTHROPIC_API_KEY 未设置"
            echo "  请设置环境变量或在 config.yaml 中配置 anthropic_api_key"
            exit 1
        fi
    else
        echo -e "${GREEN}[ok]${NC} ANTHROPIC_API_KEY 已设置（环境变量）"
    fi

    if [ -z "$OPENAI_API_KEY" ]; then
        if grep -q 'openai_api_key: "sk-' "$ROOT/config.yaml" 2>/dev/null; then
            echo -e "${GREEN}[ok]${NC} OPENAI_API_KEY 已在 config.yaml 中配置"
        else
            echo -e "${YELLOW}[info]${NC} OPENAI_API_KEY 未设置，embedding 将使用本地模型"
        fi
    else
        echo -e "${GREEN}[ok]${NC} OPENAI_API_KEY 已设置（环境变量）"
    fi
}

# ─── 安装依赖 ─────────────────────────────
cmd_install() {
    echo -e "${CYAN}[1/2]${NC} 安装 Python 依赖..."
    pip install -r requirements.txt

    echo -e "${CYAN}[2/2]${NC} 安装前端依赖..."
    cd "$ROOT/web/frontend"
    npm install
    cd "$ROOT"

    echo -e "${GREEN}[done]${NC} 依赖安装完成"
}

# ─── 运行 Pipeline ────────────────────────
cmd_run() {
    check_env
    echo -e "${CYAN}[start]${NC} 启动 Pipeline..."
    python run.py "$@"
}

# ─── 启动 Web UI ──────────────────────────
cmd_web() {
    check_env
    echo -e "${CYAN}[start]${NC} 启动 Web UI..."

    # 启动后端
    echo -e "${GREEN}[api]${NC} 后端启动中 → http://localhost:8000"
    python web/app.py &
    API_PID=$!

    # 启动前端
    echo -e "${GREEN}[ui]${NC} 前端启动中 → http://localhost:3000"
    cd "$ROOT/web/frontend"
    npm run dev &
    UI_PID=$!
    cd "$ROOT"

    # 捕获退出信号，同时关闭两个进程
    trap "echo ''; echo -e '${YELLOW}[stop]${NC} 正在关闭...'; kill $API_PID $UI_PID 2>/dev/null; exit 0" INT TERM

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "  后端 API:  http://localhost:8000"
    echo -e "  前端 UI:   http://localhost:3000"
    echo -e "  按 Ctrl+C 停止"
    echo -e "${GREEN}========================================${NC}"

    wait
}

# ─── 只启动 API ───────────────────────────
cmd_api() {
    check_env
    echo -e "${GREEN}[api]${NC} 后端启动中 → http://localhost:8000"
    python web/app.py
}

# ─── 主入口 ───────────────────────────────
CMD="${1:-run}"

case "$CMD" in
    install)
        cmd_install
        ;;
    run)
        shift 2>/dev/null || true
        cmd_run "$@"
        ;;
    web)
        cmd_web
        ;;
    api)
        cmd_api
        ;;
    refine)
        shift
        if [ -z "$1" ]; then
            echo -e "${RED}[error]${NC} 请指定 Idea ID: ./start.sh refine <id>"
            exit 1
        fi
        check_env
        python run.py --refine "$1"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo -e "${RED}[error]${NC} 未知命令: $CMD"
        usage
        exit 1
        ;;
esac
