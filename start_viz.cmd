@echo off
chcp 65001 >nul
rem MemPalace viz launcher (read-only).
rem Server runs in a minimized window titled mempalace-viz.
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not defined MEMPALACE_VIZ_PORT set MEMPALACE_VIZ_PORT=8766
if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到 .venv
  echo 请先运行: python -m venv .venv
  echo 然后运行: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
start "mempalace-viz" /min cmd /c ".venv\Scripts\python.exe -m server.main"
rem wait for bind (~3s) before opening the browser
ping -n 4 127.0.0.1 >nul
start "" http://127.0.0.1:%MEMPALACE_VIZ_PORT%
echo 服务运行中: http://127.0.0.1:%MEMPALACE_VIZ_PORT%
echo 访问不了时先在服务器本地打开上述地址确认；远程需用端口转发或 SSH 隧道
echo 停止服务: 关闭最小化的 mempalace-viz 窗口
pause
