# AGENTS.md — 给 AI 编码助手的安装配置指南

> 本文件面向 AI coding agent。用户让你"配置/安装 mempalace-viz"时，按下列步骤执行，不跳步、不猜路径。

## 项目是什么

MemPalace 本地记忆宫殿的**只读**可视化管理台：FastAPI 后端 + 原生前端（无构建链），21 个 `/api/*` 只读端点，9 个视图（总览/结构/搜索/KG/导航图/Diary/协调域/运维/记忆体检）。

**只读红线（不可破坏）**：不得新增任何写工具调用（delete/update/mine/sweep/sync/compress/diary_write 等）。只读工具白名单在 `server/config.py` 的 `READONLY_TOOLS`。

## 前置检查（先做，不要跳过）

```bash
python --version          # 0) Python 3.10+（3.13 已验证）
mempalace status          # 1) mempalace CLI 是否可用（不在 PATH 时见"可选配置"）
mempalace --version       # 2) 版本（>=3.7 即可，3.10 已验证）
```

宫殿路径自动解析链：`MEMPALACE_PALACE` 环境变量 > `~/.mempalace/config.json` 的 `palace_path` > `~/.mempalace/palace`。若用户是老安装（`~/.mempalace`）或新安装（`~/.config/mempalace`），前者已覆盖；新安装用户请确认实际宫殿路径，必要时写入可选配置。

## 安装（跨平台）

```bash
# Windows（PowerShell/cmd）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# macOS / Linux
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

可选（仅用于跑浏览器冒烟测试）：
`.venv/bin/pip install playwright`（Windows 对应 `.venv\Scripts\pip`）。
浏览器启动链：本机 Edge（Windows 标准路径）→ msedge channel → Playwright 自带 chromium；无 Edge 的机器先执行 `playwright install chromium` 即可。

## 可选配置 `mempalace_viz.json`（项目根，已 gitignore）

仅当以下任一情况出现时创建（否则**不要创建**，默认解析已可用）：

| 字段 | 何时需要 |
|---|---|
| `palace` | 宫殿不在默认解析链位置 |
| `mempalace_exe` | `mempalace` 不在 PATH（如 uv tool 安装目录未加入 PATH） |
| `mempalace_mcp_exe` | 同上（hub 不可用时降级用；路径通常与 CLI 同目录的 `mempalace-mcp`） |
| `hub_log` | 用户跑了本地 hub 且想看日志卡片 |
| `backup_dir` | 用户有备份目录想看备份新鲜度 |
| `port` | 默认 8766 被占用时换端口 |

模板见 `mempalace_viz.example.json`。另外 `MEMPALACE_EXE` / `MEMPALACE_MCP_EXE` / `MEMPALACE_VIZ_PORT` 环境变量可覆盖同名项。

## 启动与验证（必须看到验证输出才算完成）

```bash
# 启动（Windows 双击 start_viz.cmd；或手动）
.venv\Scripts\python.exe -m server.main        # Windows
.venv/bin/python -m server.main                # mac/Linux

# 验证 1：接口连通（另开终端）
curl -s http://127.0.0.1:8766/api/overview     # 期望：含 "total_drawers" 的 JSON

# 验证 2：单元测试全绿（当前 51 项）
.venv\Scripts\python.exe -m pytest             # Windows
.venv/bin/python -m pytest                     # mac/Linux

# 验证 3（可选，需 playwright + 本机浏览器）：9 视图无控制台错误
.venv\Scripts\python.exe tests\browser_smoke.py     # Windows
.venv/bin/python tests/browser_smoke.py             # mac/Linux

# 验证 4（可选）：交互流（全局搜索/详情面板/分页/移动端 375px 等 14 项）
.venv\Scripts\python.exe tests\interaction_smoke.py

# 验证 5（可选）：中英文切换（en/zh 默认检测 + 手动切换 + 刷新持久 + 9 视图英文标题，6 项）
.venv\Scripts\python.exe tests\i18n_smoke.py
```

## 常见问题

- **界面语言**：默认按浏览器语言判定——含中文（zh*）显示中文，其余（含识别不到）显示英文；右上角「中文 / EN」可手动切换并记住（localStorage `mempalace_viz_lang`）。后端少量用户可见文案随请求头 `Accept-Language` 切换（缺省中文）。给非中文用户部署时无需任何配置。
- **页面提示 "palace unreachable"**：mempalace CLI 找不到或宫殿路径不对 → 检查前置检查步骤（Python 版本 / CLI 可用性 / 版本），必要时写 `mempalace_exe` / `palace`。
- **hub 卡片显示 hub=fail 但其它正常**：hub 未运行属正常（3.10 的 hub 空闲 8 小时会自退），工具自动降级 stdio，仅首次查语义类请求稍慢。不必强行为用户启动 hub。
- **备份卡片为空**：MemPalace 不做定期备份，只有运行 `mempalace repair` / `migrate` 时才生成备份。可视化会自动发现官方位置（宫殿旁的 `<palace>.backup` 目录、宫殿内的 `chroma.sqlite3.max-seq-id-backup-*` 文件）；用户自有备份目录可在 `mempalace_viz.json` 里用 `backup_dir` 指定。
- **hub.log 卡片不出现**：这是可选功能（仅当用户自建了把日志落盘的本地 hub 时才需要），未配置 `hub_log` 时相关卡片自动隐藏，属正常。
- **空宫殿跑冒烟**：`tests/interaction_smoke.py` 在宫殿无数据时，Diary / 检索自测等步骤会自动跳过内容断言（标注"跳过"），不算失败。
- **端口被占用**：改 `mempalace_viz.json` 的 `port` 或设 `MEMPALACE_VIZ_PORT`。
- **不要把服务绑定到 0.0.0.0**：默认仅 127.0.0.1。远程访问请用 SSH 隧道（`ssh -L 8766:127.0.0.1:8766 user@host`），本工具无鉴权。
