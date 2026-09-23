"""uvicorn 启动入口。"""

from __future__ import annotations

import sys

import uvicorn

from . import config
from .app import create_app

app = create_app()


def _harden_stdout() -> None:
    """受限输出环境（如 Windows cp1252 管道）下避免打印崩溃：错误策略降级为 replace。

    不改编码：中文终端（GBK/UTF-8）照常显示中文；编码能力不足的流把无法编码的
    字符替换为 '?'，不再抛 UnicodeEncodeError。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _banner(port: int) -> None:
    line = "=" * 58
    print(line)
    print("  MemPalace 可视化管理台（只读）")
    print(f"  访问地址   http://127.0.0.1:{port}")
    print("  停止服务   按 Ctrl+C（或关闭本窗口）")
    print("  远程访问   用 SSH 隧道：ssh -L %d:127.0.0.1:%d 用户@主机" % (port, port))
    print("             （本工具无鉴权，请勿绑定 0.0.0.0）")
    if port != 8766:
        print(f"  端口来源   配置覆盖（MEMPALACE_VIZ_PORT / mempalace_viz.json）")
    print(line)


def main() -> None:
    _harden_stdout()
    port = config.VIZ_PORT
    _banner(port)
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    except SystemExit:
        print()
        print(f"[错误] 端口 {port} 绑定失败——可能已被其他程序占用。")
        print("  换端口：设置环境变量 MEMPALACE_VIZ_PORT=8767，或修改 mempalace_viz.json 的 port")
        raise


if __name__ == "__main__":
    main()
