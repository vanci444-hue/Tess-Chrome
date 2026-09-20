#!/bin/bash
# Finder 双击入口：以脚本所在目录启动，不依赖当前终端路径。
TESS_ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
"$TESS_ROOT/scripts/run-demo.sh"
TESS_RESULT=$?
if [ "$TESS_RESULT" -ne 0 ]; then
  echo '启动未完成，请根据上面的提示处理。按回车关闭。'
  read -r
fi
exit "$TESS_RESULT"
