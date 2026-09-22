"""交互冒烟：真实点击/输入流验证前端逻辑与移动端适配。

用法：.venv\\Scripts\\python.exe tests\\interaction_smoke.py [--url ...] [--headed]
依赖：playwright + 本机 Edge/Chrome；需服务已在运行。
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
        page = await browser.new_page(
            viewport={"width": 1440, "height": 960}, locale="zh-CN"
        )
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        async def goto(view):
            await page.goto(f"{args.url}/#/{view}", wait_until="domcontentloaded")
            await page.wait_for_timeout(900)

        # --- 1. 顶栏全局搜索：输入+回车 → 跳转搜索页并出结果 ---
        await goto("overview")
        await page.fill("#global-search", "diary")
        await page.press("#global-search", "Enter")
        await page.wait_for_timeout(2500)
        try:
            assert "#/search" in page.url, f"未跳转搜索页: {page.url}"
            rows = page.locator("#search-results .vlist-row")
            assert await rows.count() > 0, "全局搜索无结果"
            ok("顶栏全局搜索→跳转+出结果")
        except Exception as e:
            fail("顶栏全局搜索", str(e))

        # --- 2. 点搜索结果 → 详情面板打开 ---
        try:
            await page.locator("#search-results .vlist-row").first.click()
            await page.wait_for_timeout(1500)
            assert await page.locator("#drawer-panel.is-open").count() == 1, "面板未打开"
            title = (await page.locator("#drawer-title").inner_text()).strip()
            assert len(title) > 3, "面板标题异常"
            ok(f"搜索结果→详情面板（{title[:30]}）")
        except Exception as e:
            fail("详情面板打开", str(e))

        # --- 3. Esc 关闭面板 ---
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            assert await page.locator("#drawer-panel.is-open").count() == 0, "Esc 未关闭"
            ok("Esc 关闭详情面板")
        except Exception as e:
            fail("Esc 关闭面板", str(e))

        # --- 4. 结构页：点 room → 列表；首页上一页禁用；点行开详情 ---
        await goto("structure")
        try:
            room_link = page.locator("[data-room]").first
            room_name = (await room_link.inner_text()).strip().split("\n")[0].strip()
            await room_link.click()
            await page.wait_for_timeout(1500)
            rows = page.locator("#structure-list .vlist-row")
            assert await rows.count() > 0, "room 列表为空"
            prev = page.locator("#pg-prev")
            assert await prev.is_disabled(), "首页上一页未禁用"
            flt = await page.locator("#structure-filter").inner_text()
            assert room_name in flt, f"room 过滤未生效：filter='{flt}' room='{room_name}'"
            ok(f"结构页 room 列表+分页边界+过滤（{room_name}）")
        except Exception as e:
            fail("结构页列表/分页", str(e)[:140])

        # --- 5. 分页下一页（若可用）切换正常 ---
        try:
            next_btn = page.locator("#pg-next")
            if await next_btn.count() and not await next_btn.is_disabled():
                await next_btn.click()
                await page.wait_for_timeout(1200)
                text = await page.locator("#structure-list .row").first.inner_text()
                assert "显示" in text or "共" in text, "分页后计数行缺失"
                ok("结构页翻页")
            else:
                ok("结构页翻页（单页数据，跳过）")
        except Exception as e:
            fail("结构页翻页", str(e))

        # --- 6. KG 时间线：点实体 → 事实表出现 + 图谱自动适配全貌 ---
        await goto("kg")
        try:
            ent = page.locator("#kg-timeline .kg-entity").first
            await ent.click()
            await page.wait_for_timeout(2000)
            facts = page.locator("#kg-facts table")
            assert await facts.count() > 0, "facts 表未渲染"
            fit = {"outside": -1, "nodes": 0}
            for _ in range(12):  # 轮询等自动适配生效（布局稳定+适配约需数秒）
                fit = await page.evaluate(
                    """() => {
                        const inst = window.echarts && window.echarts.getInstanceByDom(
                            document.querySelector('#kg-chart'));
                        if (!inst) return { outside: -1, nodes: 0 };
                        const d = inst.getModel().getSeriesByIndex(0).getData();
                        const cw = inst.getWidth(), ch = inst.getHeight();
                        let out = 0;
                        for (let i = 0; i < d.count(); i++) {
                            const l = d.getItemLayout(i);
                            if (!l) continue;
                            const p = inst.convertToPixel({ seriesIndex: 0 }, [l[0], l[1]]);
                            if (!p) continue;
                            if (p[0] < -3 || p[0] > cw + 3 || p[1] < -3 || p[1] > ch + 3) out += 1;
                        }
                        return { outside: out, nodes: d.count() };
                    }"""
                )
                if fit.get("outside") == 0:
                    break
                await page.wait_for_timeout(1000)
            assert fit.get("outside") == 0, f"图谱未适配全貌: {fit} 有节点渲染在画布外"
            ok(f"KG 时间线→实体事实 + 全貌适配（{fit['nodes']} 节点全部渲染在画布内）")
            mm = await page.evaluate(
                """async () => {
                    const inst = window.echarts && window.echarts.getInstanceByDom(
                        document.querySelector('#kg-chart'));
                    if (!inst) return { rendered: -1, expected: -1 };
                    const links = inst.getOption().series[0].links || [];
                    const rendered = links.filter(l => l.mention).length;
                    const tl = await (await fetch('/api/kg/timeline')).json();
                    const facts = Array.isArray(tl.data) ? tl.data
                        : (tl.data.timeline || tl.data.facts || []);
                    const subjects = new Set(facts.map(f => f.subject).filter(Boolean));
                    const pairs = new Set();
                    const escRe = (s) => s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
                    for (const f of facts) {
                        const text = String(f.object || '');
                        if (!f.subject || text.length < 10) continue;
                        for (const ent of subjects) {
                            if (ent === f.subject || ent === text.trim() || ent.length < 5) continue;
                            const re = new RegExp(`(?<![A-Za-z0-9_])${escRe(ent)}(?![A-Za-z0-9_])`, 'i');
                            if (re.test(text)) pairs.add(`${f.subject} ${ent}`);
                        }
                    }
                    return { rendered, expected: pairs.size };
                }"""
            )
            assert mm["rendered"] == mm["expected"], (
                f"提及边不一致: 渲染 {mm['rendered']} vs 期望 {mm['expected']}"
            )
            ok(f"KG 提及边与数据一致（{mm['rendered']} 条虚线提及边）")
        except Exception as e:
            fail("KG 实体事实", str(e)[:140])

        # --- 6c. KG 标签 formatter 契约：ECharts 以 params 对象调用，必须返回字符串 ---
        try:
            fmt = await page.evaluate(
                """() => {
                    const inst = window.echarts && window.echarts.getInstanceByDom(
                        document.querySelector('#kg-chart'));
                    if (!inst) return { err: 'no instance' };
                    const f = inst.getOption().series[0]?.label?.formatter;
                    if (typeof f !== 'function') return { err: 'no formatter' };
                    const long = f({ name: 'very-long-entity-name-abcdef' });
                    const short = f({ name: 'alpha-service' });
                    return {
                        longType: typeof long, long: String(long),
                        shortType: typeof short, short: String(short),
                    };
                }"""
            )
            assert fmt.get("longType") == "string" and fmt.get("shortType") == "string", (
                f"formatter 必须返回字符串（ECharts params 对象契约）: {fmt}"
            )
            assert len(fmt["long"]) <= 16 and fmt["long"].endswith("…"), f"长名未截断: {fmt['long']!r}"
            assert fmt["short"] == "alpha-service", f"短名被改动: {fmt['short']!r}"
            ok(f"KG 标签 formatter 契约（长名截断 {fmt['long']!r}，短名保持）")
        except Exception as e:
            fail("KG 标签 formatter", str(e)[:140])

        # --- 6d. KG 连线可见性契约：实线用亮色 / 虚线提及可见 / 过期用暗色 ---
        try:
            edge = await page.evaluate(
                """() => {
                    const inst = window.echarts && window.echarts.getInstanceByDom(
                        document.querySelector('#kg-chart'));
                    if (!inst) return { err: 'no instance' };
                    const links = inst.getOption().series[0].links || [];
                    const cs = getComputedStyle(document.documentElement);
                    const tok = (n) => cs.getPropertyValue(n).trim();
                    const STRONG = tok('--ink-300');
                    const MENTION = tok('--ink-400');
                    const EXPIRED = tok('--ink-500');
                    const bad = [];
                    let solid = 0, dashed = 0, expired = 0;
                    for (const l of links) {
                        const ls = l.lineStyle || {};
                        const c = String(ls.color || '');
                        const op = Number(ls.opacity ?? 1);
                        if (l.mention) {
                            dashed += 1;
                            if (c !== MENTION || op < 0.5) bad.push(['mention', c, op]);
                        } else if (op >= 0.8) {
                            solid += 1;
                            if (c !== STRONG) bad.push(['solid', c, op]);
                        } else {
                            expired += 1;
                            if (c !== EXPIRED || op > 0.6) bad.push(['expired', c, op]);
                        }
                    }
                    return { total: links.length, solid, dashed, expired, bad: bad.slice(0, 4) };
                }"""
            )
            assert not edge.get("bad"), f"连线颜色契约不符（实线应 {edge}）"
            ok(f"KG 连线可见性（实线 {edge['solid']} 亮色 / 虚提及 {edge['dashed']} / 过期 {edge['expired']}）")
        except Exception as e:
            fail("KG 连线可见性", str(e)[:140])

        # --- 6e. KG 画布尺寸与节点间距 ---
        try:
            g = await page.evaluate(
                """() => {
                    const el = document.querySelector('#kg-chart');
                    const inst = window.echarts && window.echarts.getInstanceByDom(el);
                    if (!inst) return { err: 'no instance' };
                    const d = inst.getModel().getSeriesByIndex(0).getData();
                    const pts = [];
                    for (let i = 0; i < d.count(); i++) {
                        const l = d.getItemLayout(i);
                        if (!l) continue;
                        const p = inst.convertToPixel({ seriesIndex: 0 }, [l[0], l[1]]);
                        if (p) pts.push(p);
                    }
                    let mind = Infinity;
                    const gaps = [];
                    for (let i = 0; i < pts.length; i++)
                        for (let j = i + 1; j < pts.length; j++) {
                            const dd = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
                            gaps.push(dd);
                            if (dd < mind) mind = dd;
                        }
                    gaps.sort((a, b) => a - b);
                    const p10 = gaps.length
                        ? Math.round(gaps[Math.floor(gaps.length * 0.1)])
                        : 0;
                    return { w: inst.getWidth(), h: inst.getHeight(), nodes: pts.length,
                             minGap: Math.round(mind), p10 };
                }"""
            )
            assert g.get("w", 0) >= 1000, f"画布未加宽: {g}"
            assert g.get("h", 0) >= 600, f"画布未加高: {g}"
            assert g.get("p10", 0) >= 60, f"节点间距分布过挤（p10 应≥60px）: {g}"
            ok(f"KG 画布 {g['w']}x{g['h']} + 间距 p10={g['p10']}px / 最小 {g['minGap']}px（{g['nodes']} 节点）")
        except Exception as e:
            fail("KG 画布/间距", str(e)[:140])

        # --- 6b. 宫殿导航图：traverse（下拉选房 + 数组渲染回归） ---
        await goto("graph")
        try:
            sel = page.locator("#tr-room")
            values = await sel.locator("option").evaluate_all(
                "els => els.map(e => e.value).filter(Boolean)"
            )
            assert values, "房间下拉未加载"
            pick = "diary" if "diary" in values else values[0]
            await sel.select_option(pick)
            await page.click("#tr-go")
            await page.wait_for_timeout(3000)
            text = await page.locator("#tr-result").inner_text()
            assert ("关联到" in text) or ("没有找到" in text), f"traverse 结果异常: {text[:80]}"
            if "关联到" in text:
                assert await page.locator("#tr-result table").count() > 0, "列表未渲染表格"
            ok(f"导航图 traverse 下拉选房（{pick}）")
        except Exception as e:
            fail("导航图 traverse", str(e)[:140])

        # --- 7. Diary：预设加载 + 展开按钮（空宫殿自动跳过断言） ---
        await goto("diary")
        try:
            await page.wait_for_timeout(1500)
            entries = page.locator("#diary-list .card")
            n = await entries.count()
            if n == 0:
                ok("Diary（无条目，跳过内容断言）")
            else:
                exp = page.locator(".diary-expand").first
                if await exp.count():
                    await exp.click()
                    await page.wait_for_timeout(300)
                ok(f"Diary 加载（{n} 条）")
        except Exception as e:
            fail("Diary", str(e))

        # --- 8. 协调域：坏 artifact id → 明确错误提示 ---
        await goto("events")
        try:
            await page.fill("#art-id", "not-exist-id-123")
            await page.click("#art-go")
            await page.wait_for_timeout(2000)
            text = await page.locator("#art-view").inner_text()
            assert ("失败" in text) or ("error" in text.lower()) or ("无" in text), f"未见错误提示: {text[:80]}"
            ok("artifact 坏 id 错误提示")
        except Exception as e:
            fail("artifact 错误提示", str(e))

        # --- 9. 体检：运行 → 摘要行 → 自测判定 ---
        await goto("audit")
        try:
            await page.click("#audit-run")
            await page.wait_for_selector("#audit-copy", timeout=90000)
            summary = await page.locator("#audit-findings").inner_text()
            assert "共" in summary and "扫描耗时" in summary, "摘要行缺失"
            ok("体检运行+摘要行")
        except Exception as e:
            fail("体检运行", str(e)[:120])
        try:
            self_q = page.locator(".self-q")
            if await self_q.count() == 0:
                ok("检索自测（无可选房间，跳过）")
            else:
                await self_q.first.click()
                await page.wait_for_timeout(4000)
                verdict = await page.locator("#self-out").inner_text()
                assert ("✅" in verdict) or ("❌" in verdict), f"无自动判定: {verdict[:80]}"
                ok("检索自测自动判定")
        except Exception as e:
            fail("自测自动判定", str(e))
        try:
            chip = await page.locator("#health-chip").inner_text()
            assert "未运行" not in chip and "体检" in chip, f"chip 未更新: {chip}"
            ok(f"顶栏体检 chip 即时更新（{chip}）")
        except Exception as e:
            fail("顶栏 chip 更新", str(e))

        # --- 10. 快速连切全部视图两轮，无 JS 错误 ---
        try:
            for _ in range(2):
                for v in ["overview", "structure", "search", "kg", "graph", "diary", "events", "health", "audit"]:
                    await page.goto(f"{args.url}/#/{v}", wait_until="domcontentloaded")
                    await page.wait_for_timeout(180)
            assert not errors, f"存在 JS 错误: {errors[:2]}"
            ok("快速连切 9 视图×2 无 JS 错误")
        except Exception as e:
            fail("快速连切", str(e))

        # --- 11. 移动端 375px：无横向滚动 ---
        mob = await browser.new_page(
            viewport={"width": 375, "height": 812}, locale="zh-CN"
        )
        mob_errors: list[str] = []
        mob.on("pageerror", lambda e: mob_errors.append(str(e)))
        try:
            for v in ["overview", "structure", "audit"]:
                await mob.goto(f"{args.url}/#/{v}", wait_until="domcontentloaded")
                await mob.wait_for_timeout(1200)
                sw = await mob.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)")
                assert sw <= 376, f"{v} 横向溢出 scrollWidth={sw}"
            assert not mob_errors, f"移动端 JS 错误: {mob_errors[:2]}"
            ok("移动端 375px 无横向溢出（3 视图）")
        except Exception as e:
            fail("移动端适配", str(e))
        await mob.screenshot(path=os.path.join(args.out, "mobile-overview.png"))

        await browser.close()

    print(f"\nRESULT: {'PASS' if not failures else f'FAIL ({len(failures)})'}")
    print(f"通过 {len(passed)} 项")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
