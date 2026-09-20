#!/bin/bash
# 前台运行；Ctrl+C 只结束本脚本启动的服务，不杀占用端口的其它进程。
set -euo pipefail
TESS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TESS_ROOT"
if [ ! -x .venv/bin/python ] || [ ! -f frontend/dist/manifest.json ]; then
  echo '尚未完成构建，开始安装项目内依赖并构建插件。'
  "$TESS_ROOT/scripts/build-demo.sh"
fi
[ -f backend/.env ] || cp backend/.env.example backend/.env
export PYTHONPATH="$TESS_ROOT:$TESS_ROOT/backend"
# 只打印非敏感运行配置，拒绝来源 ID 不一致和被占用的端口。
TESS_BIND="$(.venv/bin/python - <<'PY'
import json, socket, sys
from pathlib import Path
from src.config.settings import settings
expected='chrome-extension://'+json.loads(Path('frontend/extension-identity.json').read_text())['id']
if settings.allowed_extension_origin != expected:
    sys.exit('backend/.env 的 ALLOWED_EXTENSION_ORIGIN 与正式插件不一致，应为 '+expected)
if settings.report_origin != f'http://127.0.0.1:{settings.port}' or settings.host != '127.0.0.1':
    sys.exit('演示启动器要求 HOST=127.0.0.1，REPORT_ORIGIN=http://127.0.0.1:PORT；请保持前端后端端口一致。')
if settings.port != 8099:
    sys.exit('正式插件默认连接 8099，请将 PORT 设为 8099 后重试。')
with socket.socket() as sock:
    try: sock.bind((settings.host,settings.port))
    except OSError: sys.exit(f'端口 {settings.port} 已被占用。若 Tess 已启动可直接使用；本脚本不会结束其他进程。')
print(settings.host,settings.port)
PY
)"
read -r TESS_HOST TESS_PORT <<< "$TESS_BIND"
printf 'Tess 本机服务：http://%s:%s\n' "$TESS_HOST" "$TESS_PORT"
echo 'Chrome 打开 Tesla 中国 Model Y 配置器，点击 Tess 扩展。'
echo '缺少 API 配置时可以建档、抓取官网和查看旧报告；语音/Agent/地图会明确提示缺配置。'
echo '保持此窗口开启；Ctrl+C 停止本机服务。'
exec .venv/bin/python -m uvicorn src.main:app --host "$TESS_HOST" --port "$TESS_PORT" --log-level warning
