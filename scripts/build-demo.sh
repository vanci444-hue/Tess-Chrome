#!/bin/bash
# 依赖全部安装在项目内；不改系统 Python，也不安装外部 pycore 包。
set -euo pipefail
TESS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TESS_ROOT"
command -v node >/dev/null || { echo '需要 Node.js 24，请先安装后重试。'; exit 1; }
command -v npm >/dev/null || { echo '未找到 npm。'; exit 1; }
node -e 'if(Number(process.versions.node.split(".")[0])<24)process.exit(1)' || { echo '需要 Node.js 24 或更新版本。'; exit 1; }
if [ ! -x .venv/bin/python ]; then
  TESS_PYTHON="$(command -v python3.12 || true)"
  [ -n "$TESS_PYTHON" ] || { echo '需要 Python 3.12，请先安装后重试。'; exit 1; }
  "$TESS_PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install -r backend/requirements.txt
[ -f backend/.env ] || cp backend/.env.example backend/.env
cd frontend
npm ci
# 正式安装包必须使用实际后端，不能把契约 Mock 编译成默认环境。
VITE_CONTRACT_MOCK=false npm run build
printf '\n构建完成。Chrome 开发者模式 → 加载已解压的扩展 → %s/frontend/dist\n' "$TESS_ROOT"
echo '之后运行 scripts/run-demo.sh 或双击 启动Tess.command。'
