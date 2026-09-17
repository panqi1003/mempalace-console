"""只读 reader：hub → stdio → CLI 三级降级。传输函数可注入（测试）。"""

from __future__ import annotations

import atexit
import itertools
import json
import logging
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque

from . import config

logger = logging.getLogger(__name__)

_counter = itertools.count(1)


def _next_id() -> int:
    return next(_counter)


class ReaderUnavailable(Exception):
    """hub 与 stdio 都不可用。"""


class ReaderToolError(Exception):
    """MCP 层返回 error。"""

    def __init__(self, code: int, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _parse_mcp_response(payload: dict) -> dict:
    if "error" in payload:
        err = payload.get("error") or {}
        raise ReaderToolError(
            int(err.get("code", -32000)), str(err.get("message", "unknown"))
        )
    try:
        text = payload["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReaderToolError(-32000, f"malformed MCP result: {exc}") from exc
    return json.loads(text)


def _real_hub_transport(tool: str, args: dict) -> dict:
    target = config.discover_hub(config.PALACE)
    if target is None:
        raise ReaderUnavailable("hub serverinfo not found or stale")
    base_url, headers = target
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": tool, "arguments": args or {}},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/mcp", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=config.MCP_TIMEOUT_S) as resp:
        raw = resp.read()
    return _parse_mcp_response(json.loads(raw.decode("utf-8")))


def _real_stdio_transport(tool: str, args: dict) -> dict:
    """兼容入口：走持久 stdio 会话（复用子进程，避免反复冷加载嵌入模型）。"""
    return _STDIO.call(tool, args)


class _StdioSession:
    """持久 stdio 会话：一个 mempalace-mcp 子进程服务所有调用。

    - 首次调用 spawn + initialize，之后复用（模型只加载一次）
    - 调用级超时（STDIO_TIMEOUT_S）内未收到响应视为不可用，杀进程
    - 进程死亡后自动重拉；失败重试仅一次
    """

    def __init__(self, spawn=None, timeout: float | None = None):
        self._spawn = spawn or self._default_spawn
        self._timeout = timeout if timeout is not None else config.STDIO_TIMEOUT_S
        self._lock = threading.Lock()
        self._proc = None
        self._queue: queue.Queue | None = None
        self._initialized = False

    @staticmethod
    def _default_spawn():
        if not config.MEMPALACE_MCP_EXE:
            raise ReaderUnavailable(
                "mempalace-mcp not found (check PATH / MEMPALACE_MCP_EXE)"
            )
        return subprocess.Popen(
            [config.MEMPALACE_MCP_EXE, "--palace", config.PALACE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _ensure(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        self._proc = self._spawn()
        self._queue = queue.Queue()
        self._initialized = False
        proc = self._proc
        q = self._queue

        def reader():
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        q.put(json.loads(line))
                    except ValueError:
                        continue
            except Exception:
                pass
            q.put(None)

        threading.Thread(target=reader, name="stdio-reader", daemon=True).start()

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        self._queue = None
        self._initialized = False
        try:
            if proc is not None:
                proc.kill()
        except Exception:
            pass

    def shutdown(self) -> None:
        with self._lock:
            self._kill()

    def _send(self, payload: dict) -> None:
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def _read_until(self, expect_id) -> dict:
        deadline = time.monotonic() + self._timeout
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise ReaderUnavailable("stdio timed out")
            try:
                payload = self._queue.get(timeout=remain)
            except queue.Empty:
                raise ReaderUnavailable("stdio timed out")
            if payload is None:
                raise ReaderUnavailable("stdio closed")
            if payload.get("id") == expect_id:
                return payload

    def _call_locked(self, tool: str, args: dict) -> dict:
        self._ensure()
        if not self._initialized:
            init_id = _next_id()
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": init_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "mempalace-viz", "version": "0.1.0"},
                    },
                }
            )
            self._read_until(init_id)
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._initialized = True
        call_id = _next_id()
        self._send(
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": args or {}},
            }
        )
        return _parse_mcp_response(self._read_until(call_id))

    def call(self, tool: str, args: dict) -> dict:
        with self._lock:
            try:
                return self._call_locked(tool, args)
            except ReaderToolError:
                raise
            except Exception:
                self._kill()
            try:
                return self._call_locked(tool, args)
            except ReaderToolError:
                raise
            except Exception as exc:
                self._kill()
                raise ReaderUnavailable(f"stdio failed: {exc}") from exc


_STDIO = _StdioSession()
atexit.register(_STDIO.shutdown)


def _real_cli_transport(argv: list[str]) -> str:
    if not config.MEMPALACE_EXE:
        raise ReaderUnavailable("mempalace CLI not found (check PATH / MEMPALACE_EXE)")
    try:
        result = subprocess.run(
            [config.MEMPALACE_EXE, "--palace", config.PALACE, *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.CLI_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReaderUnavailable(
            f"CLI timed out after {config.CLI_TIMEOUT_S}s: {' '.join(argv)}"
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise ReaderUnavailable(f"CLI exited {result.returncode}: {detail}")
    return result.stdout + (("\n" + result.stderr) if result.stderr else "")


class ReadOnlyReader:
    def __init__(self, transports: dict | None = None):
        self._tiers = {"hub": "untried", "stdio": "untried", "cli": "untried"}
        self._transports = transports or {}

    def _hub(self):
        if "hub" in self._transports:
            return self._transports["hub"]
        return _real_hub_transport

    def _stdio(self):
        if "stdio" in self._transports:
            return self._transports["stdio"]
        return _real_stdio_transport

    def call(self, tool: str, args: dict | None = None) -> dict:
        config.assert_readonly(tool)
        args = args or {}
        hub_exc: Exception | None = None
        try:
            result = self._hub()(tool, args)
            self._tiers["hub"] = "ok"
            return result
        except ReaderToolError:
            self._tiers["hub"] = "ok"
            raise
        except Exception as exc:
            hub_exc = exc
            self._tiers["hub"] = "fail"
            logger.warning("hub tier failed (%s: %s); falling back to stdio", tool, exc)
        try:
            result = self._stdio()(tool, args)  # type: ignore[operator]
            self._tiers["stdio"] = "ok"
            return result
        except ReaderToolError:
            self._tiers["stdio"] = "ok"
            raise
        except Exception as exc:
            self._tiers["stdio"] = "fail"
            logger.warning("stdio tier failed (%s: %s)", tool, exc)
            raise ReaderUnavailable(
                f"hub failed: {hub_exc}; stdio failed: {exc}"
            ) from exc

    def cli_text(self, argv: list[str]) -> str:
        fn = self._transports.get("cli", _real_cli_transport)
        try:
            out = fn(argv)
        except ReaderUnavailable:
            self._tiers["cli"] = "fail"
            raise
        self._tiers["cli"] = "ok"
        return out

    def tier_status(self) -> dict[str, str]:
        return dict(self._tiers)

    # ---- 业务方法（全部走只读白名单） ----
    def overview(self):
        return self.call("mempalace_status")

    def taxonomy(self):
        """归一化：3.10 返回 {"taxonomy": {wing: {room: n}}}；3.7.x 直接平铺。"""
        data = self.call("mempalace_get_taxonomy")
        if isinstance(data, dict) and set(data.keys()) == {"taxonomy"}:
            inner = data.get("taxonomy")
            if isinstance(inner, dict):
                return inner
        return data

    def wings(self):
        return self.call("mempalace_list_wings")

    def rooms(self, wing):
        return self.call("mempalace_list_rooms", {"wing": wing})

    def drawers(self, wing=None, room=None, offset=0, limit=20):
        args = {"offset": offset, "limit": limit}
        if wing:
            args["wing"] = wing
        if room:
            args["room"] = room
        return self.call("mempalace_list_drawers", args)

    def drawer(self, drawer_id):
        return self.call("mempalace_get_drawer", {"drawer_id": drawer_id})

    def search(self, query, wing=None, room=None, limit=10):
        args = {"query": query, "limit": limit}
        if wing:
            args["wing"] = wing
        if room:
            args["room"] = room
        return self.call("mempalace_search", args)

    def kg_stats(self):
        return self.call("mempalace_kg_stats")

    def kg_query(self, entity):
        return self.call("mempalace_kg_query", {"entity": entity})

    def kg_timeline(self, entity=None):
        args = {"entity": entity} if entity else {}
        return self.call("mempalace_kg_timeline", args)

    def graph_stats(self):
        return self.call("mempalace_graph_stats")

    def tunnels(self):
        return self.call("mempalace_list_tunnels")

    def find_tunnels(self, wing_a, wing_b):
        return self.call("mempalace_find_tunnels", {"wing_a": wing_a, "wing_b": wing_b})

    def traverse(self, start_room, max_hops=2):
        return self.call(
            "mempalace_traverse", {"start_room": start_room, "max_hops": max_hops}
        )

    def hallways(self, wing=None):
        args = {"wing": wing} if wing else {}
        return self.call("mempalace_list_hallways", args)

    def diary(self, agent_name, last_n=20):
        return self.call(
            "mempalace_diary_read", {"agent_name": agent_name, "last_n": last_n}
        )

    def events(self, limit=50):
        return self.call("mempalace_event_list", {"limit": limit})

    def artifact(self, artifact_id):
        return self.call("mempalace_artifact_get", {"artifact_id": artifact_id})

    # ---- 运维健康（只读文件/CLI） ----
    def repair_status_text(self):
        return self.cli_text(["repair-status"])

    def hub_log_tail(self, lines=50, lang="zh"):
        """可选功能：未配置 hub_log 时返回空串（由 /api/health/summary 的标志位决定 UI 隐藏）。"""
        log_path = config.HUB_LOG
        if not log_path:
            return ""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                content = deque(fh, maxlen=max(int(lines), 1))
        except OSError as exc:
            return f"hub.log 不可读：{exc}" if lang != "en" else f"hub.log unreadable: {exc}"
        return "".join(content)

    def backups(self):
        """备份发现：① 可选的自定义目录 ② 官方约定（<palace>.backup 目录 + 宫内 max-seq-id 文件）。"""
        import os
        from datetime import datetime
        from glob import glob

        items: list[dict] = []

        def _stat_item(path: str, source: str, *, is_dir: bool = False) -> None:
            try:
                stat = os.stat(path)
            except OSError:
                return
            items.append(
                {
                    "name": os.path.basename(path),
                    "path": path,
                    "is_dir": is_dir,
                    "size_bytes": None if is_dir else stat.st_size,
                    "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(
                        timespec="seconds"
                    ),
                    "source": source,
                }
            )

        # ① 自定义备份目录（mempalace_viz.json 的 backup_dir，可选）
        if config.BACKUP_DIR:
            try:
                for name in os.listdir(config.BACKUP_DIR):
                    if name.endswith(".sqlite3"):
                        _stat_item(os.path.join(config.BACKUP_DIR, name), "custom")
            except OSError:
                pass

        # ② 官方目录级备份：<palace>.backup（mempalace repair/migrate 生成）
        palace = str(config.PALACE).rstrip("\\/")
        dir_backup = palace + ".backup"
        if os.path.isdir(dir_backup):
            _stat_item(dir_backup, "official-dir", is_dir=True)

        # ③ 官方文件级备份：宫内 chroma.sqlite3.max-seq-id-backup-<时间戳>
        for path in glob(os.path.join(palace, "chroma.sqlite3.max-seq-id-backup-*")):
            _stat_item(path, "official-file")

        items.sort(key=lambda item: item["mtime_iso"], reverse=True)
        return items

    # ---- 记忆体检（全部只读） ----
    def _page_drawers(self):
        """全量翻页 list_drawers 的生成器（limit=100/页）。"""
        offset = 0
        while True:
            page = self.call("mempalace_list_drawers", {"offset": offset, "limit": 100})
            drawers = page.get("drawers") or []
            if not drawers:
                return
            yield from drawers
            if len(drawers) < 100:
                return
            offset += 100

    def activity(self, days=30):
        from datetime import date, timedelta

        start_day = str(date.today() - timedelta(days=days))
        per_day: dict = {}
        last_by_room: dict = {}
        for d in self._page_drawers():
            filed = ((d.get("metadata") or {}).get("filed_at")) or d.get("filed_at")
            if not filed:
                continue
            day = str(filed)[:10]
            if day < start_day:
                continue
            wing = d.get("wing") or "unknown"
            per_day.setdefault(day, {}).setdefault(wing, 0)
            per_day[day][wing] += 1
            room = d.get("room") or (d.get("metadata") or {}).get("room")
            if room in ("diary", "lessons", "decisions"):
                prev = last_by_room.get(room)
                if not prev or str(filed) > prev:
                    last_by_room[room] = str(filed)
        return {
            "days": days,
            "per_day": {k: dict(v) for k, v in sorted(per_day.items())},
            "last_by_room": last_by_room,
        }

    def audit(self, sample_size=5):
        """全量元数据扫描。mined 内容缺 source_file 属真问题；精选条目缺源属正常。"""
        import time as _time

        t0 = _time.monotonic()
        kg = self.kg_stats()
        mined_modes = {"convos", "project", "extract", "sweep"}
        stats = {
            "total": 0,
            "no_wing": 0,
            "no_room": 0,
            "no_source": 0,
            "no_source_mined": 0,
            "no_source_curated": 0,
            "unknown_wing": 0,
            "empty_preview": 0,
            "by_ingest": {},
            "dup_exact_pairs": 0,
            "dup_semantic_sample": [],
            "issue_samples": {
                "no_wing": [],
                "unknown_wing": [],
                "no_source": [],
                "empty_preview": [],
                "dup_pairs": [],
            },
            "kg": {
                "expired": kg.get("expired_facts", 0),
                "current": kg.get("current_facts", 0),
            },
        }
        cap = 5

        def _sample(category, value):
            if len(stats["issue_samples"][category]) < cap:
                stats["issue_samples"][category].append(value)

        seen: dict = {}
        sampled = 0
        for d in self._page_drawers():
            stats["total"] += 1
            drawer_id = d.get("drawer_id")
            wing = d.get("wing")
            room = d.get("room")
            md = d.get("metadata") or {}
            src = md.get("source_file") or d.get("source_file")
            preview = (d.get("content_preview") or "").strip()
            ingest = md.get("ingest_mode") or "unknown"
            if not wing:
                stats["no_wing"] += 1
                _sample("no_wing", drawer_id)
            elif wing == "unknown":
                stats["unknown_wing"] += 1
                _sample("unknown_wing", drawer_id)
            if not room:
                stats["no_room"] += 1
            if not src:
                stats["no_source"] += 1
                _sample("no_source", drawer_id)
                if ingest in mined_modes:
                    stats["no_source_mined"] += 1
                else:
                    stats["no_source_curated"] += 1
            if not preview:
                stats["empty_preview"] += 1
                _sample("empty_preview", drawer_id)
            stats["by_ingest"][ingest] = stats["by_ingest"].get(ingest, 0) + 1
            if preview:
                key = preview[:200]
                if key in seen:
                    stats["dup_exact_pairs"] += 1
                    _sample("dup_pairs", {"a": seen[key], "b": drawer_id})
                else:
                    seen[key] = drawer_id
            if sample_size and sampled < sample_size and preview:
                sampled += 1
                if len(stats["dup_semantic_sample"]) < cap:
                    try:
                        dup = self.call(
                            "mempalace_check_duplicate",
                            {"content": preview[:400], "threshold": 0.92},
                        )
                        matches = dup.get("matches") or []
                        self_hit = any(
                            m.get("drawer_id") == drawer_id
                            or m.get("id") == drawer_id
                            for m in matches
                        )
                        if len(matches) > (1 if self_hit else 0):
                            stats["dup_semantic_sample"].append(
                                {"drawer_id": drawer_id, "matches": len(matches)}
                            )
                    except ReaderToolError:
                        pass
        stats["elapsed_s"] = round(_time.monotonic() - t0, 1)
        return stats

    def wakeup(self, wing):
        return self.cli_text(["wake-up", "--wing", wing])

    def palace_size(self, lang="zh"):
        """宫殿数据文件大小：兼容 chroma（默认）与 sqlite_exact（3.10 可选后端）。"""
        import os
        from datetime import datetime

        for name in ("chroma.sqlite3", "sqlite_exact.sqlite3"):
            path = os.path.join(config.PALACE, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            return {
                "path": path,
                "size_bytes": stat.st_size,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            }
        message = (
            "未找到数据库文件（尝试 chroma.sqlite3 / sqlite_exact.sqlite3）"
            if lang != "en"
            else "database file not found (tried chroma.sqlite3 / sqlite_exact.sqlite3)"
        )
        return {
            "path": config.PALACE,
            "error": message,
        }
