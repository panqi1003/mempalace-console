"""浏览器冒烟测试：用 Playwright + 本机 Edge 逐视图渲染、抓控制台错误、截图。

用法（需要 playwright 与本机 Edge/Chrome）：
    .venv\\Scripts\\python.exe tests\\browser_smoke.py [--headed] [--url http://127.0.0.1:8766]
产物：docs/screenshots/<view>.png，控制台错误汇总打印。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from playwright.async_api import async_playwright

VIEWS = [
    ("overview", None),
    ("structure", "click-room"),
    ("search", "search-query"),
    ("kg", None),
    ("graph", None),
    ("diary", None),
    ("events", None),
    ("health", None),
    ("audit", "run-audit"),
]

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


async def launch_browser(pw, headed: bool):
    """跨平台启动链：本机 Edge（Windows 标准路径）→ msedge channel（覆盖 mac/非标准安装）→
    Playwright 自带 chromium（需先 playwright install chromium）。任何系统都能跑冒烟。"""
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return await pw.chromium.launch(headless=not headed, executable_path=path)
    try:
        return await pw.chromium.launch(headless=not headed, channel="msedge")
    except Exception:
        return await pw.chromium.launch(headless=not headed)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--out", default="docs/screenshots")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    failures: list[str] = []

    async with async_playwright() as pw:
        browser = await launch_browser(pw, args.headed)
        page = await browser.new_page(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )

        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        for view, action in VIEWS:
            console_errors.clear()
            page_errors.clear()
            await page.goto(f"{args.url}/#/{view}", wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            if action == "click-room":
                room = page.locator("[data-room]").first
                if await room.count():
                    await room.click()
                    await page.wait_for_timeout(1200)
                else:
                    failures.append(f"{view}: 未找到房间节点")
            elif action == "search-query":
                query = page.locator("#search-input")
                if await query.count():
                    await query.fill("diary")
                    await query.press("Enter")
                    await page.wait_for_timeout(2500)
                else:
                    failures.append(f"{view}: 未找到搜索输入框（视图可能渲染失败）")
            elif action == "run-audit":
                btn = page.locator("#audit-run")
                if await btn.count():
                    await btn.click()
                    try:
                        await page.wait_for_selector("#audit-findings .alert, #audit-findings table", timeout=60000)
                    except Exception:
                        failures.append(f"{view}: 体检结果 60s 未出现")
                    await page.wait_for_timeout(800)
                else:
                    failures.append(f"{view}: 未找到运行体检按钮")

            await page.wait_for_timeout(400)
            shot = os.path.join(args.out, f"{view}.png")
            await page.screenshot(path=shot)

            # 页面内错误提示（被视图捕获渲染的异常）也算失败
            body_text = await page.locator("body").inner_text()
            if "加载失败" in body_text or "不可用：" in body_text:
                failures.append(f"{view}: 页面内出现加载失败提示")
                print(f"    [页面内错误] {view} 含'加载失败/不可用'提示")

            errs = list(dict.fromkeys(console_errors + page_errors))
            status = "OK" if not errs else f"ERRORS({len(errs)})"
            print(f"[{status}] {view} -> {shot}")
            for e in errs[:6]:
                print(f"    console/pageerror: {e[:220]}")
            if errs:
                failures.append(f"{view}: {errs[0][:120]}")

        await browser.close()

    print("\nRESULT:", "PASS" if not failures else f"FAIL ({len(failures)})")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
