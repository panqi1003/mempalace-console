"""持久 stdio 会话：复用子进程、超时、失败重拉。用假进程测生命周期逻辑。"""

import json
import queue
import time

import pytest

from server.reader import ReaderUnavailable, _StdioSession


class FakeStdin:
    def __init__(self, proc):
        self._proc = proc

    def write(self, text):
        self._proc.written.append(text)

    def flush(self):
        pass


class FakeStdout:
    """按预置脚本逐行产出；queue 为空时阻塞（模拟真实流）。"""

    def __init__(self):
        self.lines = queue.Queue()

    def push(self, payload):
        self.lines.put(json.dumps(payload) + "\n")

    def close(self):
        self.lines.put("")

    def __iter__(self):
        while True:
            line = self.lines.get()
            if not line:
                return
            yield line


class FakeProc:
    instances = []

    def __init__(self, script=None):
        self.written = []
        self.stdin = FakeStdin(self)
        self.stdout = FakeStdout()
        self._alive = True
        FakeProc.instances.append(self)
        if script:
            script(self)

    def poll(self):
        return None if self._alive else 1

    def kill(self):
        self._alive = False
        self.stdout.close()


def responder(proc):
    """收到 tools/call 后回复结果（简单按写入行同步响应）。"""

    def on_write(text):
        try:
            msg = json.loads(text.strip().splitlines()[0])
        except (ValueError, IndexError):
            return
        if msg.get("method") == "tools/call":
            proc.stdout.push(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": {"content": [{"type": "text", "text": '{"ok": true}'}]},
                }
            )
        elif msg.get("method") == "initialize":
            proc.stdout.push({"jsonrpc": "2.0", "id": msg["id"], "result": {}})

    original = proc.stdin.write

    def write(text):
        original(text)
        on_write(text)

    proc.stdin.write = write


def test_reuses_single_process_across_calls():
    FakeProc.instances = []

    def spawn():
        return FakeProc(script=responder)

    session = _StdioSession(spawn=spawn, timeout=2.0)
    r1 = session.call("mempalace_status", {})
    r2 = session.call("mempalace_kg_stats", {})
    assert r1 == {"ok": True} and r2 == {"ok": True}
    assert len(FakeProc.instances) == 1  # 只 spawn 一次


def test_initializes_once_then_calls():
    FakeProc.instances = []

    def spawn():
        return FakeProc(script=responder)

    session = _StdioSession(spawn=spawn, timeout=2.0)
    session.call("mempalace_status", {})
    session.call("mempalace_status", {})
    written = "".join(FakeProc.instances[0].written)
    assert written.count('"initialize"') == 1
    assert written.count("notifications/initialized") == 1
    assert written.count("tools/call") == 2


def test_timeout_raises_and_kills():
    def spawn():
        return FakeProc()  # 永不响应

    session = _StdioSession(spawn=spawn, timeout=0.2)
    t0 = time.monotonic()
    with pytest.raises(ReaderUnavailable):
        session.call("mempalace_status", {})
    assert time.monotonic() - t0 < 2.0
    assert FakeProc.instances[-1].poll() is not None  # 已被 kill


def test_respawns_after_death():
    procs = []

    def spawn():
        p = FakeProc(script=responder)
        procs.append(p)
        return p

    session = _StdioSession(spawn=spawn, timeout=2.0)
    session.call("mempalace_status", {})
    procs[0].kill()  # 进程死亡
    r = session.call("mempalace_status", {})
    assert r == {"ok": True}
    assert len(procs) == 2  # 重新 spawn


def test_error_response_propagates_tool_error():
    from server.reader import ReaderToolError

    def spawn():
        def script(proc):
            def on_write(text):
                try:
                    msg = json.loads(text.strip().splitlines()[0])
                except (ValueError, IndexError):
                    return
                if msg.get("method") == "tools/call":
                    proc.stdout.push(
                        {
                            "jsonrpc": "2.0",
                            "id": msg["id"],
                            "error": {"code": -32602, "message": "bad"},
                        }
                    )
                elif msg.get("method") == "initialize":
                    proc.stdout.push({"jsonrpc": "2.0", "id": msg["id"], "result": {}})

            original = proc.stdin.write

            def write(text):
                original(text)
                on_write(text)

            proc.stdin.write = write

        return FakeProc(script=script)

    session = _StdioSession(spawn=spawn, timeout=2.0)
    with pytest.raises(ReaderToolError):
        session.call("mempalace_status", {})
