"""只读访问配置：路径动态解析（跨平台）、白名单、hub 发现（对齐官方机制）。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

MCP_TIMEOUT_S = 10.0
CLI_TIMEOUT_S = 30.0
STDIO_TIMEOUT_S = 60.0  # 持久 stdio 单次调用上限（含嵌入模型冷加载余量）

# mempalace 3.7.1 只读工具白名单（写工具见 mcp_server.py _MUTATING_TOOLS，一律不接入）
READONLY_TOOLS: frozenset[str] = frozenset(
    {
        "mempalace_status",
        "mempalace_list_wings",
        "mempalace_list_rooms",
        "mempalace_get_taxonomy",
        "mempalace_get_aaak_spec",
        "mempalace_kg_query",
        "mempalace_kg_timeline",
        "mempalace_kg_stats",
        "mempalace_traverse",
        "mempalace_find_tunnels",
        "mempalace_graph_stats",
        "mempalace_mesh_peers",
        "mempalace_list_tunnels",
        "mempalace_list_hallways",
        "mempalace_follow_tunnels",
        "mempalace_search",
        "mempalace_check_duplicate",
        "mempalace_get_drawer",
        "mempalace_list_drawers",
        "mempalace_diary_read",
        "mempalace_memories_filed_away",
        "mempalace_event_list",
        "mempalace_artifact_get",
    }
)


class ReadOnlyViolation(Exception):
    """尝试调用白名单外的工具（含一切写工具）。"""


def assert_readonly(tool: str) -> None:
    if tool not in READONLY_TOOLS:
        raise ReadOnlyViolation(f"tool not allowed (read-only viewer): {tool}")


def dotmempalace(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".mempalace"


def default_palace(home: Path | None = None) -> str:
    """官方解析链：MEMPALACE_PALACE > ~/.mempalace/config.json 的 palace_path > ~/.mempalace/palace。"""
    env = os.environ.get("MEMPALACE_PALACE") or os.environ.get("MEMPALACE_PALACE_PATH")
    if env:
        return env
    try:
        data = json.loads(
            (dotmempalace(home) / "config.json").read_text(encoding="utf-8")
        )
        if isinstance(data, dict):
            p = str(data.get("palace_path") or "").strip()
            if p:
                return p
    except (OSError, ValueError, TypeError):
        pass
    return str(dotmempalace(home) / "palace")


def find_exe(names: list[str], env_var: str) -> str | None:
    """env 覆盖（须存在）> shutil.which。找不到返回 None。"""
    env_val = os.environ.get(env_var)
    if env_val and Path(env_val).exists():
        return env_val
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


VIZ_CONFIG_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "mempalace_viz.json",
    Path.home() / ".mempalace-console" / "config.json",
    Path.home() / ".mempalace-viz" / "config.json",  # 兼容旧路径
]


def _load_optional_json_paths(paths) -> dict:
    for p in paths:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _resolve_exe(opt_val, names, env_var):
    """可选配置显式指定 > env 指定的存在文件 > which。都不行则 None。"""
    if opt_val and Path(opt_val).exists():
        return str(opt_val)
    return find_exe(names, env_var)


def _as_port(value, fallback: int = 8766) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return port if 1 <= port <= 65535 else fallback


def load_settings(home: Path | None = None) -> dict:
    opt = _load_optional_json_paths(VIZ_CONFIG_CANDIDATES)
    return {
        "palace": opt.get("palace") or default_palace(home),
        "mempalace_exe": _resolve_exe(
            opt.get("mempalace_exe"), ["mempalace", "mempalace.exe"], "MEMPALACE_EXE"
        ),
        "mempalace_mcp_exe": _resolve_exe(
            opt.get("mempalace_mcp_exe"),
            ["mempalace-mcp", "mempalace-mcp.exe"],
            "MEMPALACE_MCP_EXE",
        ),
        "hub_log": opt.get("hub_log"),
        "backup_dir": opt.get("backup_dir"),
        "port": _as_port(opt.get("port") or os.environ.get("MEMPALACE_VIZ_PORT")),
    }


def hub_state_dir(palace: str) -> Path:
    canonical = os.path.abspath(os.path.realpath(os.path.expanduser(palace)))
    key = hashlib.sha256(os.path.normcase(canonical).encode("utf-8")).hexdigest()[:24]
    return Path.home() / ".mempalace" / "server" / key


def _pid_alive(pid: int) -> bool:
    """与官方 server_registry._pid_alive 同逻辑。

    Windows 上绝不能用 os.kill(pid, 0)——Windows 的 os.kill 对非 CTRL 信号
    会直接调用 TerminateProcess 终止目标进程（等于把 hub 杀了）。
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def discover_hub(palace: str) -> tuple[str, dict] | None:
    """读取官方 serverinfo.json/token；不存活或字段缺失则返回 None。"""
    state = hub_state_dir(palace)
    info_path = state / "serverinfo.json"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict):
        return None
    recorded = str(info.get("palace_path", ""))
    if recorded and os.path.normcase(recorded) != os.path.normcase(
        os.path.abspath(os.path.realpath(os.path.expanduser(palace)))
    ):
        return None
    pid = info.get("pid")
    if isinstance(pid, int) and not _pid_alive(pid):
        return None
    host, port, scheme = info.get("host"), info.get("port"), info.get("scheme", "http")
    if not host or not isinstance(port, int):
        return None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    try:
        token = (state / "token").read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return f"{scheme}://{host}:{port}", headers


SETTINGS = load_settings()
PALACE = SETTINGS["palace"]
VIZ_PORT = SETTINGS["port"]
MEMPALACE_EXE = SETTINGS["mempalace_exe"]
MEMPALACE_MCP_EXE = SETTINGS["mempalace_mcp_exe"]
BACKUP_DIR = SETTINGS.get("backup_dir")
HUB_LOG = SETTINGS.get("hub_log")
