"""main.py 启动健壮性：受限输出环境（如 Windows cp1252 管道）下 banner 打印不得崩溃。

背景：CI 的 Windows runner 以 cp1252 重定向 stdout，print 中文横幅会抛
UnicodeEncodeError 把服务整个带崩。修复方式：启动时把 stdout/stderr 的错误
策略降级为 replace（不改编码，中文终端照常显示）。
"""

import io
import sys


def test_harden_stdout_survives_cp1252_pipe():
    from server.main import _harden_stdout

    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stream, io.StringIO()
    try:
        _harden_stdout()
        print("MemPalace 可视化管理台（只读）")
        sys.stdout.flush()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    assert b"MemPalace" in buf.getvalue()
