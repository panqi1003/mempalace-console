"""UI 冒烟（确定性演示数据）：9 视图渲染 + 关键交互回归。

与 interaction_smoke 的区别：
- interaction_smoke 针对真实宫殿（本地开发用）
- 本脚本在浏览器层拦截全部 /api/*，用**虚构演示数据**驱动真实前端渲染，
  因此可在任何环境（含 CI）确定性运行，且不涉及任何真实记忆数据。

覆盖断言：
  1) 9 视图渲染：英文标题 + 内容标记 + 零控制台错误 + 无"加载失败"提示
  2) 知识图谱：全貌适配 / 提及边计数 / formatter 契约 / 画布尺寸 / 间距分布 /
     布局顺序 / 连线三级亮色
  3) 搜索：命中结果 + 点开抽屉详情面板
  4) Diary：首屏 ≤20 条 + 「加载更多」生效
  5) 体检：问题清单 + Composition 卡（type 口径）
  6) 总览：逻辑条目口径说明（卡片 tooltip）

用法：.venv\\Scripts\\python.exe tests\\ui_smoke.py [--url ...]
依赖：playwright + 本机 Edge/Chrome，或 playwright install chromium；需服务已在运行。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import sys
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

TODAY = date.today()
TIERS = {"hub": "ok", "stdio": "untried", "cli": "ok"}

failures: list[str] = []
passed: list[str] = []


def ok(name: str) -> None:
    passed.append(name)
    print(f"[OK] {name}")


def fail(name: str, detail: str) -> None:
    failures.append(f"{name}: {detail}")
    print(f"[FAIL] {name} -> {detail}")


# ---------------- 虚构演示数据 ----------------
def iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def ts(days_ago: int, hh: int = 9, mm: int = 10) -> str:
    return f"{iso(TODAY - timedelta(days=days_ago))}T{hh:02d}:{mm:02d}:00"


def fake_id(room: str, wing: str, idx: int, days_ago: int) -> str:
    h = hashlib.sha1(f"{wing}-{room}-{idx}".encode()).hexdigest()[:12]
    stamp = (TODAY - timedelta(days=days_ago)).strftime("%Y%m%d_%H%M%S")
    return f"{room}_{wing}_{stamp}_{h}"


WING_ROOMS = {
    "platform": {"diary": 76, "backend": 30, "lessons": 18, "decisions": 14, "incidents": 12, "db": 18},
    "mobile-app": {"diary": 42, "testing": 26, "releases": 28},
    "docs": {"diary": 12, "onboarding": 16, "api-reference": 12, "changelog": 8},
}
BY_ROOM: dict[str, int] = {}
for _rooms in WING_ROOMS.values():
    for _r, _c in _rooms.items():
        BY_ROOM[_r] = BY_ROOM.get(_r, 0) + _c
BY_WING = {w: sum(rs.values()) for w, rs in WING_ROOMS.items()}
SCAN_TOTAL = sum(BY_ROOM.values())
PHYSICAL_TOTAL = SCAN_TOTAL + 5

ROOM_TOPIC = {
    "diary": "daily-log", "backend": "performance", "lessons": "retro",
    "decisions": "adr", "incidents": "postmortem", "db": "migration",
    "testing": "flaky-tests", "releases": "v2.4", "onboarding": "setup",
    "api-reference": "openapi", "changelog": "v2.4.1",
}
PREVIEW = {
    "diary": "SESSION:{date}|{topic}|Reviewed the navigation redesign; aligned token naming with the new spacing scale.",
    "backend": "note|{topic}|Switched list endpoints to keyset pagination; removed the full-table sort.",
    "lessons": "retro|{topic}|Lesson: gate migrations behind a feature flag — the rollback path saved a release cycle.",
    "decisions": "adr|{topic}|ADR-014: keep the API read-only by default; mutations stay behind a writer service.",
    "incidents": "postmortem|{topic}|25-minute elevated latency after a cache stampede; added jittered TTLs.",
    "db": "migration|{topic}|Backfill ran in 3 batches; row counts verified against the manifest.",
    "testing": "note|{topic}|Quarantined two flaky suites; root cause was a shared fixture clock.",
    "releases": "checklist|{topic}|Release 2.4: staged rollout 10%→25%→100%, error budget checked between steps.",
    "onboarding": "guide|{topic}|New contributors: local setup, test-pyramid overview, design decisions.",
    "api-reference": "doc|{topic}|OpenAPI: documented pagination cursors and error envelope examples.",
    "changelog": "log|{topic}|2.4.1 fixes a cursor edge case in the drawer listing API.",
}

STATUS = {
    "total_drawers": PHYSICAL_TOTAL,
    "wings": {w: c + 1 for w, c in BY_WING.items()},
    "rooms": dict(BY_ROOM),
    "backend": "chroma",
    "library_versions": {"serving": {"mempalace": "3.10.0", "chromadb": "1.5.9"}},
    "sqlite_integrity": {"checked": True, "ok": True, "error_count": 0},
}

PER_DAY: dict[str, dict] = {}
for _off, _cnt in {
    6: {"platform": 9, "mobile-app": 4}, 5: {"platform": 14, "docs": 3},
    4: {"platform": 11, "mobile-app": 8}, 3: {"platform": 6},
    2: {"platform": 18, "mobile-app": 12, "docs": 4}, 1: {"platform": 15, "mobile-app": 9},
    0: {"platform": 12, "mobile-app": 5},
}.items():
    PER_DAY[iso(TODAY - timedelta(days=_off))] = _cnt

LAST_BY_ROOM = {"diary": ts(0, 14, 5), "lessons": ts(1, 18, 30), "decisions": ts(1, 11, 0)}

GRAPH_STATS = {
    "total_rooms": 11, "total_room_instances": 13, "tunnel_rooms": 1,
    "passive_tunnel_rooms": 1, "explicit_tunnels": 1, "total_edges": 3,
    "total_connections": 3,
    "rooms_per_wing": {w: len(rs) for w, rs in WING_ROOMS.items()},
    "top_tunnels": [{"room": "diary", "wings": ["platform", "mobile-app", "docs"], "count": BY_ROOM["diary"]}],
}
TUNNELS = [{"source_wing": "platform", "source_room": "db", "target_wing": "mobile-app",
            "target_room": "testing", "label": "schema sync"}]
HALLWAYS = [{"a": "diary", "b": "testing", "wing": "mobile-app"}]
TRAVERSE = {"rooms": [
    {"room": "diary", "count": BY_ROOM["diary"], "wings": ["platform", "mobile-app", "docs"], "hop": 0, "halls": []},
    {"room": "backend", "count": 30, "wings": ["platform"], "hop": 1, "halls": [], "connected_via": ["platform"]},
    {"room": "testing", "count": 26, "wings": ["mobile-app"], "hop": 1, "halls": [], "connected_via": ["mobile-app"]},
]}

KG_STATS = {
    "entities": 46, "triples": 68, "current_facts": 64, "expired_facts": 4,
    "relationship_types": ["purpose", "status", "owner", "depends_on", "version"],
}
KG_FACTS = [
    {"subject": "platform", "predicate": "purpose", "object": "Core API gateway serving web and mobile clients", "current": True, "valid_from": iso(TODAY - timedelta(days=2)), "valid_to": None},
    {"subject": "v2.4-release", "predicate": "status", "object": "Staged rollout complete: 10% → 25% → 100%", "current": True, "valid_from": iso(TODAY - timedelta(days=4)), "valid_to": None},
    {"subject": "deploy-pipeline", "predicate": "deployed_in", "object": "staging cluster; production window Fri 10:00 UTC", "current": True, "valid_from": iso(TODAY - timedelta(days=6)), "valid_to": None},
    {"subject": "auth-service", "predicate": "version", "object": "2.0.10 (rolling upgrade finished)", "current": True, "valid_from": iso(TODAY - timedelta(days=8)), "valid_to": None},
    {"subject": "docs", "predicate": "purpose", "object": "Public developer documentation and API reference", "current": True, "valid_from": iso(TODAY - timedelta(days=11)), "valid_to": None},
    {"subject": "mobile-app", "predicate": "owner", "object": "mobile-team (on-call rotates weekly)", "current": True, "valid_from": iso(TODAY - timedelta(days=13)), "valid_to": None},
    {"subject": "sandbox", "predicate": "purpose", "object": "Throwaway experiments; safe to wipe on Fridays", "current": True, "valid_from": None, "valid_to": None},
    {"subject": "invoice-service", "predicate": "depends_on", "object": "platform (payment webhooks), db (ledger replica)", "current": True, "valid_from": iso(TODAY - timedelta(days=17)), "valid_to": None},
    {"subject": "legacy-billing", "predicate": "status", "object": "Deprecated — migrated to invoice-service", "current": False, "valid_from": iso(TODAY - timedelta(days=40)), "valid_to": iso(TODAY - timedelta(days=12))},
    {"subject": "platform", "predicate": "owner", "object": "platform-team (superseded by on-call rotation)", "current": False, "valid_from": iso(TODAY - timedelta(days=30)), "valid_to": iso(TODAY - timedelta(days=7))},
    {"subject": "mobile-app", "predicate": "depends_on", "object": "platform", "current": True, "valid_from": iso(TODAY - timedelta(days=9)), "valid_to": None},
    {"subject": "docs", "predicate": "verified_by", "object": "deploy-pipeline", "current": True, "valid_from": iso(TODAY - timedelta(days=15)), "valid_to": None},
    {"subject": "feature-flags", "predicate": "purpose", "object": "Gate rollout of mobile-app releases; owned by platform-team", "current": True, "valid_from": iso(TODAY - timedelta(days=19)), "valid_to": None},
]

DIARY_AGENTS = ["assistant", "code-reviewer"]
DIARY_ENTRIES = [
    {"entry": f"SESSION:{iso(TODAY - timedelta(days=i // 3))}|design-system|Rolled out the spacing scale to dialogs and popovers; audited 42 components.",
     "topic": ["design-system", "release", "incident", "refactor", "review"][i % 5],
     "timestamp": ts(i // 3, 9 + (i % 8), (i * 7) % 60),
     "agent_name": DIARY_AGENTS[i % 4 // 2]}
    for i in range(26)
]
for _i in range(0, 26, 5):
    DIARY_ENTRIES[_i]["entry"] += (
        " Also walked the contributor checklist: setup script detects a missing CLI, the test pyramid section "
        "links the three smoke suites, and design decisions are linked from the footer so reviewers can find the why."
    )

SEARCH_HITS = [
    {"drawer_id": fake_id("incidents", "platform", 1, 3), "wing": "platform", "room": "incidents", "similarity": 0.84,
     "metadata": {"filed_at": ts(3, 10, 30), "source_file": "docs/runbooks/deploy.md"},
     "text": "Runbook: platform deploy — freeze merges, build the image, canary 10% for 15 minutes, watch the error budget."},
    {"drawer_id": fake_id("releases", "mobile-app", 2, 4), "wing": "mobile-app", "room": "releases", "similarity": 0.79,
     "metadata": {"filed_at": ts(4, 16, 5), "source_file": "docs/releases/2.4.md"},
     "text": "Release 2.4 checklist: staged rollout 10% → 25% → 100%, verify crash-free rate between steps."},
    {"drawer_id": fake_id("decisions", "platform", 3, 6), "wing": "platform", "room": "decisions", "similarity": 0.76,
     "metadata": {"filed_at": ts(6, 11, 40), "source_file": "docs/adr/adr-014.md"},
     "text": "ADR-014: keep the deployment API read-only by default; mutations stay behind a writer service."},
]

DRAWER_DETAIL = {
    "content": "Runbook: platform deployment\n\n1) Freeze merges on the release branch.\n2) Build and sign the image.\n3) Canary 10% for 15 minutes.\n4) Promote to 25%, then 100%.",
    "metadata": {"wing": "platform", "room": "incidents", "type": "how-to", "filed_at": ts(3, 10, 30)},
}

AUDIT = {
    "total": SCAN_TOTAL, "no_wing": 0, "unknown_wing": 0, "no_room": 0,
    "no_source": 0, "no_source_mined": 0, "no_source_curated": 0,
    "empty_preview": 1,
    "by_ingest": {"unknown": SCAN_TOTAL},
    "by_type": {"diary_entry": 130, "note": 120, "how-to": 62},
    "composition": {"field": "type", "counts": {"diary_entry": 130, "note": 120, "how-to": 62}},
    "dup_exact_pairs": 2, "dup_semantic_sample": [],
    "issue_samples": {"no_wing": [], "unknown_wing": [], "no_source": [],
                      "empty_preview": [fake_id("backend", "platform", 9, 9)],
                      "dup_pairs": [{"a": fake_id("diary", "mobile-app", 21, 4), "b": fake_id("diary", "mobile-app", 22, 4)}]},
    "kg": {"expired": 4, "current": 64},
    "elapsed_s": 2.4,
}

HEALTH = {
    "repair_status": "PALACE OK",
    "hub_log_tail": "line1\nline2",
    "backups": [{"name": "chroma_demo.sqlite3", "size_bytes": 1000, "mtime_iso": ts(2, 3)}],
    "palace": {"size_bytes": 3145728, "path": "/demo/palace/chroma.sqlite3", "mtime_iso": ts(0, 1)},
}


def drawers_rows(wing, room, offset, limit):
    scope = []
    for w, rooms in WING_ROOMS.items():
        if wing and w != wing:
            continue
        for r, cnt in rooms.items():
            if room and r != room:
                continue
            scope.append((w, r, cnt))
    total = sum(c for _, _, c in scope)
    rows = []
    for w, r, cnt in scope:
        for i in range(cnt):
            days_ago = i + 1
            text = f"{['Quick update:', 'Deep dive:', 'Field notes:'][i % 3]} " + PREVIEW[r].format(
                date=iso(TODAY - timedelta(days=days_ago)), topic=ROOM_TOPIC[r])
            rows.append({"drawer_id": fake_id(r, w, i, days_ago), "wing": w, "room": r,
                         "content_preview": text,
                         "metadata": {"filed_at": ts(days_ago, 8 + (i % 9), (i * 13) % 60),
                                      "topic": ROOM_TOPIC[r],
                                      "type": "diary_entry" if r == "diary" else "note",
                                      "agent": "assistant"}})
    rows.sort(key=lambda x: x["metadata"]["filed_at"], reverse=True)
    return {"drawers": rows[offset:offset + limit] if (offset or limit) else rows, "total": total}


def api_response(path: str, q: dict):
    data = {}
    if path == "/api/overview":
        data = STATUS
    elif path == "/api/activity":
        data = {"days": int(q.get("days", 30)), "per_day": dict(sorted(PER_DAY.items())),
                "last_by_room": LAST_BY_ROOM, "scan_total": SCAN_TOTAL,
                "by_wing": BY_WING, "by_room": dict(sorted(BY_ROOM.items(), key=lambda kv: -kv[1]))}
    elif path == "/api/taxonomy":
        data = {w: dict(rs) for w, rs in WING_ROOMS.items()}
    elif path == "/api/drawers":
        data = DRAWER_DETAIL if q.get("drawer_id") else drawers_rows(
            q.get("wing"), q.get("room"), int(q.get("offset", 0)), int(q.get("limit", 20)))
    elif path.startswith("/api/drawer/"):
        data = DRAWER_DETAIL
    elif path == "/api/search":
        data = {"hits": SEARCH_HITS}
    elif path == "/api/kg/stats":
        data = KG_STATS
    elif path == "/api/kg/timeline":
        data = {"timeline": KG_FACTS}
    elif path == "/api/kg/query":
        ent = q.get("entity", "")
        data = {"facts": [f for f in KG_FACTS if f["subject"] == ent] or KG_FACTS[:3]}
    elif path == "/api/graph/stats":
        data = GRAPH_STATS
    elif path == "/api/graph/tunnels":
        data = {"tunnels": TUNNELS}
    elif path == "/api/graph/hallways":
        data = {"hallways": HALLWAYS}
    elif path == "/api/graph/traverse":
        data = TRAVERSE
    elif path == "/api/diary/agents":
        data = DIARY_AGENTS
    elif path == "/api/diary":
        data = {"entries": DIARY_ENTRIES}
    elif path == "/api/audit":
        data = AUDIT
    elif path == "/api/events":
        data = []
    elif path == "/api/wakeup":
        data = {"text": "wake-up --wing platform"}
    elif path == "/api/health/summary":
        data = HEALTH
    return {"data": data, "tiers": TIERS}


# ---------------- 断言 ----------------
async def launch_browser(pw):
    for path in EDGE_CANDIDATES:
        if os.path.exists(path):
            return await pw.chromium.launch(headless=True, executable_path=path)
    try:
        return await pw.chromium.launch(headless=True, channel="msedge")
    except Exception:
        return await pw.chromium.launch(headless=True)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    url = args.url.rstrip("/")

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        page = await browser.new_page(viewport={"width": 1440, "height": 960}, locale="en-US")
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        async def route_handler(route, request):
            u = urlparse(request.url)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            import json as _json
            await route.fulfill(status=200, content_type="application/json; charset=utf-8",
                                body=_json.dumps(api_response(u.path, q), ensure_ascii=False))

        await page.route(re.compile(r"/api/"), route_handler)

        # --- 1) 9 视图渲染 ---
        views = {
            "overview": ["Overview", "7-day write activity", "Runtime environment"],
            "structure": ["Structure", "Full wing → room → drawer navigation"],
            "search": ["Search"],
            "kg": ["Knowledge Graph", "Fact timeline", "Entity facts"],
            "graph": ["Palace Map", "Cross-wing graph"],
            "diary": ["Diary", "Load more"],
            "events": ["Coordination"],
            "health": ["Operations"],
            "audit": ["Memory Audit", "Run audit"],
        }
        for view, markers in views.items():
            errors.clear()
            await page.goto(f"{url}/#/{view}", wait_until="domcontentloaded")
            try:
                await page.wait_for_selector(f"#view-{view} .view-title", state="visible", timeout=30000)
            except Exception:
                fail(f"视图 {view}", "标题 30s 未出现")
                continue
            await page.wait_for_timeout(1800)
            body = await page.locator("body").inner_text()
            missing = [m for m in markers if m not in body]
            errs = list(dict.fromkeys(errors))
            if "加载失败" in body or "不可用：" in body:
                fail(f"视图 {view}", "出现加载失败提示")
            elif missing:
                fail(f"视图 {view}", f"缺少标记 {missing}")
            elif errs:
                fail(f"视图 {view}", f"控制台错误 {errs[0][:120]}")
            else:
                ok(f"视图 {view} 渲染（{len(markers)} 标记）")

        # --- 2) 知识图谱：适配/提及/formatter/画布/间距/布局/连线 ---
        await page.goto(f"{url}/#/kg", wait_until="domcontentloaded")
        await page.wait_for_selector("#view-kg .view-title", state="visible", timeout=30000)
        await page.wait_for_timeout(1500)
        await page.locator("#kg-timeline .kg-entity").first.click()

        fit = {"outside": -1}
        for _ in range(12):
            fit = await page.evaluate(
                """() => {
                    const inst = window.echarts && window.echarts.getInstanceByDom(document.querySelector('#kg-chart'));
                    if (!inst) return { outside: -1 };
                    const d = inst.getModel().getSeriesByIndex(0).getData();
                    const cw = inst.getWidth(), ch = inst.getHeight();
                    let out = 0;
                    for (let i = 0; i < d.count(); i++) {
                        const l = d.getItemLayout(i);
                        if (!l) continue;
                        const p = inst.convertToPixel({ seriesIndex: 0 }, [l[0], l[1]]);
                        if (p && (p[0] < -3 || p[0] > cw + 3 || p[1] < -3 || p[1] > ch + 3)) out += 1;
                    }
                    return { outside: out, nodes: d.count() };
                }"""
            )
            if fit.get("outside") == 0:
                break
            await page.wait_for_timeout(1000)
        if fit.get("outside") == 0:
            ok(f"KG 全貌适配（{fit['nodes']} 节点全在画布内）")
        else:
            fail("KG 全貌适配", str(fit))

        kg = await page.evaluate(
            """() => {
                const inst = window.echarts.getInstanceByDom(document.querySelector('#kg-chart'));
                const series = inst.getOption().series[0];
                const links = series.links || [];
                const cs = getComputedStyle(document.documentElement);
                const tok = (n) => cs.getPropertyValue(n).trim();
                const STRONG = tok('--ink-300'), MENTION = tok('--ink-400'), EXPIRED = tok('--ink-500');
                const bad = [];
                let solid = 0, dashed = 0, expired = 0;
                for (const l of links) {
                    const ls = l.lineStyle || {};
                    const c = String(ls.color || ''), op = Number(ls.opacity ?? 1);
                    if (l.mention) { dashed += 1; if (c !== MENTION || op < 0.5) bad.push(['mention', c, op]); }
                    else if (op >= 0.8) { solid += 1; if (c !== STRONG) bad.push(['solid', c, op]); }
                    else { expired += 1; if (c !== EXPIRED || op > 0.6) bad.push(['expired', c, op]); }
                }
                const f = series.label?.formatter;
                const fmt = typeof f === 'function'
                    ? { long: String(f({ name: 'very-long-entity-name-abcdef' })), short: String(f({ name: 'alpha-service' })) }
                    : null;
                const d = inst.getModel().getSeriesByIndex(0).getData();
                const pts = [];
                for (let i = 0; i < d.count(); i++) {
                    const l = d.getItemLayout(i);
                    if (!l) continue;
                    const p = inst.convertToPixel({ seriesIndex: 0 }, [l[0], l[1]]);
                    if (p) pts.push(p);
                }
                const gaps = [];
                let mind = Infinity;
                for (let i = 0; i < pts.length; i++)
                    for (let j = i + 1; j < pts.length; j++) {
                        const dd = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]);
                        gaps.push(dd); if (dd < mind) mind = dd;
                    }
                gaps.sort((a, b) => a - b);
                const p10 = gaps.length ? Math.round(gaps[Math.floor(gaps.length * 0.1)]) : 0;
                const facts = null;
                return {
                    mentions: links.filter(l => l.mention).length,
                    solid, dashed, expired, bad: bad.slice(0, 3),
                    fmt, w: inst.getWidth(), h: inst.getHeight(),
                    minGap: Math.round(mind), p10,
                    order: (() => {
                        const factsCard = document.querySelector('#kg-facts-card');
                        return factsCard && factsCard.previousElementSibling ===
                            document.querySelector('#kg-chart').closest('.card');
                    })(),
                };
            }"""
        )
        if not kg["bad"]:
            ok(f"KG 连线三级亮色（实线 {kg['solid']} / 提及 {kg['dashed']} / 过期 {kg['expired']}）")
        else:
            fail("KG 连线颜色", str(kg["bad"]))
        if kg["fmt"] and len(kg["fmt"]["long"]) <= 16 and kg["fmt"]["long"].endswith("…") \
                and kg["fmt"]["short"] == "alpha-service":
            ok(f"KG 标签 formatter 契约（{kg['fmt']['long']}）")
        else:
            fail("KG formatter", str(kg["fmt"]))
        if kg["w"] >= 1000 and kg["h"] >= 600 and kg["p10"] >= 60:
            ok(f"KG 画布 {kg['w']}x{kg['h']} + 间距 p10={kg['p10']}px（最小 {kg['minGap']}）")
        else:
            fail("KG 画布/间距", str({k: kg[k] for k in ("w", "h", "p10", "minGap")}))
        if kg["order"]:
            ok("KG 布局：实体事实卡紧邻图谱")
        else:
            fail("KG 布局顺序", str(kg["order"]))
        mm = await page.evaluate(
            """async () => {
                const inst = window.echarts.getInstanceByDom(document.querySelector('#kg-chart'));
                const rendered = (inst.getOption().series[0].links || []).filter(l => l.mention).length;
                const tl = await (await fetch('/api/kg/timeline')).json();
                const facts = Array.isArray(tl.data) ? tl.data : (tl.data.timeline || []);
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
        if mm["rendered"] == mm["expected"] and mm["rendered"] > 0:
            ok(f"KG 提及边与数据一致（{mm['rendered']} 条）")
        else:
            fail("KG 提及边", str(mm))

        # --- 3) 搜索 + 抽屉面板 ---
        await page.goto(f"{url}/#/search", wait_until="domcontentloaded")
        await page.wait_for_selector("#view-search .view-title", state="visible", timeout=30000)
        await page.fill("#search-input", "deployment")
        await page.press("#search-input", "Enter")
        await page.wait_for_timeout(2000)
        rows = page.locator("#search-results .vlist-row")
        if await rows.count() > 0:
            ok(f"搜索命中渲染（{await rows.count()} 条）")
            await rows.first.click()
            await page.wait_for_timeout(1200)
            if await page.locator("#drawer-panel.is-open").count() == 1:
                ok("搜索→抽屉详情面板打开")
            else:
                fail("抽屉面板", "未打开")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        else:
            fail("搜索", "无结果")

        # --- 4) Diary：首屏分页 ---
        await page.goto(f"{url}/#/diary", wait_until="domcontentloaded")
        await page.wait_for_selector("#view-diary .view-title", state="visible", timeout=30000)
        await page.wait_for_timeout(2500)
        cards = await page.locator("#diary-list .card").count()
        more = page.locator(".diary-more")
        if 0 < cards <= 20 and await more.count():
            await more.click()
            await page.wait_for_timeout(600)
            after = await page.locator("#diary-list .card").count()
            if after > cards:
                ok(f"Diary 分页（{cards} → {after}）")
            else:
                fail("Diary 加载更多", f"{cards} → {after}")
        else:
            fail("Diary 首屏", f"cards={cards} more={await more.count()}")

        # --- 5) 体检 ---
        await page.goto(f"{url}/#/audit", wait_until="domcontentloaded")
        await page.wait_for_selector("#audit-run", timeout=30000)
        await page.click("#audit-run")
        try:
            await page.wait_for_selector("#audit-copy", timeout=30000)
        except Exception:
            fail("体检", "结果未渲染")
        await page.wait_for_timeout(500)
        audit_text = await page.locator("#view-audit").inner_text()
        if "Composition (type)" in audit_text and "diary_entry" in audit_text:
            ok("体检：问题清单 + Composition(type)")
        else:
            fail("体检内容", audit_text[:120])

        # --- 6) 总览：口径说明 ---
        await page.goto(f"{url}/#/overview", wait_until="domcontentloaded")
        await page.wait_for_selector("#view-overview .stat-num", timeout=30000)
        await page.wait_for_timeout(1200)
        ov = await page.evaluate(
            """() => {
                const c = [...document.querySelectorAll('.card')].find(x =>
                    (x.querySelector('.stat-label')?.textContent || '').includes('Drawers'));
                return c ? { label: c.querySelector('.stat-label').textContent.trim(),
                             title: c.getAttribute('title') || '' } : null;
            }"""
        )
        if ov and "logical entries" in ov["label"] and "status" in ov["title"]:
            ok(f"总览口径说明（{ov['title'][:50]}）")
        else:
            fail("总览口径", str(ov))

        errs_all = list(dict.fromkeys(errors))
        if errs_all:
            fail("收尾控制台", f"{len(errs_all)} 条: {errs_all[0][:120]}")
        else:
            ok("全程无遗留控制台错误")

        await browser.close()

    print(f"\nRESULT: {'PASS' if not failures else f'FAIL ({len(failures)})'}")
    print(f"通过 {len(passed)} 项")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
