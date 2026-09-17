"""i18n 冒烟：默认语言检测（zh/en）+ 手动切换 + 刷新持久。

用法：.venv\\Scripts\\python.exe tests\\i18n_smoke.py [--url ...] [--headed]
依赖：playwright + 本机 Edge/Chrome；需服务已在运行（且为新版代码）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from playwright.async_api import async_playwright

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

failures: list[str] = []
passed: list[str] = []


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


def ok(name):
    passed.append(name)
    print(f"[OK] {name}")


def fail(name, detail):
    failures.append(f"{name}: {detail}")
    print(f"[FAIL] {name} -> {detail}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--out", default="docs/screenshots")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    async with async_playwright() as pw:
        browser = await launch_browser(pw, args.headed)

        # --- 1. 英文环境（en-US）→ 默认英文 ---
        ctx_en = await browser.new_context(locale="en-US")
        page = await ctx_en.new_page()
        try:
            await page.goto(args.url, wait_until="domcontentloaded")
            await page.wait_for_selector("#lang-switch", timeout=8000)
            await page.wait_for_timeout(800)
            nav = await page.locator('[data-view="overview"]').inner_text()
            title = await page.locator("#view-overview .view-title").inner_text()
            lang_attr = await page.evaluate("document.documentElement.lang")
            pressed = await page.get_attribute('button[data-lang="en"]', "aria-pressed")
            assert "Overview" in nav, f"导航未英文: {nav!r}"
            assert title.strip() == "Overview", f"视图标题未英文: {title!r}"
            assert lang_attr.startswith("en"), f"html lang 未切换: {lang_attr!r}"
            assert pressed == "true", f"EN 按钮未选中: {pressed!r}"
            ok("en-US 环境默认英文（导航/标题/html lang/按钮态）")
        except Exception as e:
            fail("英文默认", str(e)[:140])

        # --- 2. 点「中文」→ 即时切中文 + 刷新后保持 ---
        try:
            await page.click('button[data-lang="zh"]')
            await page.wait_for_timeout(900)
            nav = await page.locator('[data-view="overview"]').inner_text()
            assert "总览" in nav, f"切换后导航未中文: {nav!r}"
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)
            nav = await page.locator('[data-view="overview"]').inner_text()
            lang_attr = await page.evaluate("document.documentElement.lang")
            assert "总览" in nav, f"刷新后未保持中文: {nav!r}"
            assert lang_attr.startswith("zh"), f"刷新后 html lang 异常: {lang_attr!r}"
            ok("英文环境手动切中文：即时生效 + 刷新保持")
        except Exception as e:
            fail("手动切中文持久化", str(e)[:140])
        await ctx_en.close()

        # --- 3. 中文环境（zh-CN）→ 默认中文 ---
        ctx_zh = await browser.new_context(locale="zh-CN")
        page2 = await ctx_zh.new_page()
        try:
            await page2.goto(args.url, wait_until="domcontentloaded")
            await page2.wait_for_selector("#lang-switch", timeout=8000)
            await page2.wait_for_timeout(800)
            nav = await page2.locator('[data-view="overview"]').inner_text()
            pressed = await page2.get_attribute('button[data-lang="zh"]', "aria-pressed")
            assert "总览" in nav, f"中文环境未默认中文: {nav!r}"
            assert pressed == "true", f"中文按钮未选中: {pressed!r}"
            ok("zh-CN 环境默认中文（识别国内）")
        except Exception as e:
            fail("中文默认", str(e)[:140])

        # --- 4. 中文环境手动选 EN → 刷新后仍英文（偏好优先于环境） ---
        try:
            await page2.click('button[data-lang="en"]')
            await page2.wait_for_timeout(900)
            await page2.reload(wait_until="domcontentloaded")
            await page2.wait_for_timeout(1200)
            nav = await page2.locator('[data-view="overview"]').inner_text()
            assert "Overview" in nav, f"偏好未覆盖环境: {nav!r}"
            ok("手动选 EN 优先于 zh-CN 环境（刷新保持）")
        except Exception as e:
            fail("偏好优先", str(e)[:140])
        await ctx_zh.close()

        # --- 5. 英文界面抽查二级文案（运维页/总览动态翻译）+ 存证截图 ---
        try:
            ctx_en2 = await browser.new_context(
                locale="en-US", viewport={"width": 1440, "height": 960}
            )
            page3 = await ctx_en2.new_page()
            await page3.goto(f"{args.url}/#/health", wait_until="domcontentloaded")
            await page3.wait_for_timeout(1800)
            body = await page3.locator("#view-health").inner_text()
            assert "Palace size" in body or "Backups" in body, f"运维页未翻译: {body[:120]!r}"
            assert "宫殿体积" not in body, "运维页残留中文"
            await page3.screenshot(path=os.path.join(args.out, "en-health.png"))
            await page3.goto(f"{args.url}/#/overview", wait_until="domcontentloaded")
            await page3.wait_for_timeout(1800)
            ov = await page3.locator("#view-overview").inner_text()
            assert "Overview" in ov, f"总览页未翻译: {ov[:120]!r}"
            await page3.screenshot(path=os.path.join(args.out, "en-overview.png"))
            await ctx_en2.close()
            ok("英文界面二级文案（运维页+总览抽查，已存截图）")
        except Exception as e:
            fail("英文二级文案", str(e)[:140])

        # --- 6. 九个视图英文标题全检（防漏翻） ---
        try:
            ctx_en3 = await browser.new_context(locale="en-US")
            page4 = await ctx_en3.new_page()
            errors4: list[str] = []
            page4.on("pageerror", lambda e: errors4.append(str(e)))
            expect = {
                "overview": "Overview",
                "structure": "Structure",
                "search": "Search",
                "kg": "Knowledge Graph",
                "graph": "Palace Map",
                "diary": "Diary",
                "events": "Coordination",
                "health": "Operations",
                "audit": "Memory Audit",
            }
            wrong = []
            for view, title in expect.items():
                await page4.goto(f"{args.url}/#/{view}", wait_until="domcontentloaded")
                await page4.wait_for_selector(f"#view-{view} .view-title", timeout=8000)
                got = (await page4.locator(f"#view-{view} .view-title").inner_text()).strip()
                if got != title:
                    wrong.append(f"{view}: {got!r} != {title!r}")
            assert not wrong, f"英文标题不符: {wrong}"
            assert not errors4, f"JS 错误: {errors4[:2]}"
            await ctx_en3.close()
            ok("9 视图英文标题全检（无 JS 错误）")
        except Exception as e:
            fail("英文标题全检", str(e)[:160])

        await browser.close()

    print(f"\nRESULT: {'PASS' if not failures else f'FAIL ({len(failures)})'}")
    print(f"通过 {len(passed)} 项")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
