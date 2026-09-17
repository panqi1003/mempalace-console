#!/usr/bin/env bash
# MemPalace 可视化管理台启动器（只读，macOS/Linux）
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1
if [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/Scripts/python.exe" ]; then
  echo "[错误] 未找到 .venv。请先运行: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
PY=".venv/bin/python"; [ -x "$PY" ] || PY=".venv/Scripts/python.exe"
PORT="${MEMPALACE_VIZ_PORT:-8766}"
URL="http://127.0.0.1:${PORT}"
echo "============================================================"
echo "  MemPalace 可视化管理台（只读）"
echo "  访问地址   ${URL}"
echo "  停止服务   按 Ctrl+C"
echo "  远程访问   用 SSH 隧道：ssh -L ${PORT}:127.0.0.1:${PORT} 用户@主机"
echo "             （本工具无鉴权，请勿绑定 0.0.0.0）"
echo "============================================================"
# 等服务真正开始监听再打开浏览器（最多 20 秒），避免竞态
(
  for _ in $(seq 1 40); do
    if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then break; fi
    sleep 0.5
  done
  open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
) &
exec "$PY" -m server.main "$@"
