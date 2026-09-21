/* 视图共享工具：数字格式化、chip、卡片、wing 颜色、详情面板打开 */

import { api, esc, openDrawer } from "../app.js";
import { t } from "../i18n.js";

export { api, esc };

const NF = new Intl.NumberFormat();

export function num(n) {
  return NF.format(Number(n ?? 0));
}

export function pct(part, total) {
  const p = Number(part) || 0;
  const t = Number(total) || 0;
  if (!t) return "0%";
  return ((p / t) * 100).toFixed(1) + "%";
}

export function chip(label, cls = "") {
  return `<span class="chip ${cls}">${esc(label)}</span>`;
}

export function statCard(value, label, sub = "") {
  return `<div class="card">
    <div class="stat-num">${esc(value)}</div>
    <div class="stat-label">${esc(label)}${sub ? ` · ${esc(sub)}` : ""}</div>
  </div>`;
}

export function card(title, bodyHtml) {
  return `<div class="card"><h3 class="card-title">${esc(title)}</h3>${bodyHtml}</div>`;
}

export function viewHead(title, sub) {
  return `<div class="view-head"><h2 class="view-title">${esc(title)}</h2><span class="view-sub">${esc(sub || "")}</span></div>`;
}

export function fmtBytes(n) {
  const units = ["B", "KB", "MB", "GB"];
  let v = Number(n ?? 0);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function daysSince(iso) {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!t) return null;
  return Math.floor((Date.now() - t) / 86400000);
}

export function timeShort(iso) {
  return esc(String(iso ?? "").replace("T", " ").slice(0, 19));
}

/* 任意 wing 的稳定配色：按名字哈希映射到 5 色板（不依赖具体项目名） */
const WING_PALETTE = [
  "--wing-1",
  "--wing-2",
  "--wing-3",
  "--wing-4",
  "--wing-5",
];

export function wingColor(wing) {
  const s = String(wing || "unknown");
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) >>> 0;
  }
  return `var(${WING_PALETTE[h % WING_PALETTE.length]})`;
}

/* ECharts canvas 不解析 CSS 变量，需取实际色值 */
export function cssColor(varExpr) {
  const name = String(varExpr).replace(/^var\((--[^),\s]+).*$/, "$1");
  if (!name.startsWith("--")) return varExpr;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || varExpr;
}

export function drawerMetaHtml(md) {
  const rows = Object.entries(md || {})
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .slice(0, 14)
    .map(
      ([k, v]) =>
        `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`
    );
  return `<dl class="drawer-meta">${rows.join("")}</dl>`;
}

/* drawer 详情：全文 + 元数据；失败给出明确提示；token 防止过期响应覆盖新选择 */
let drawerToken = 0;

export async function openDrawerById(drawerId) {
  const token = ++drawerToken;
  openDrawer(drawerId, `<div class="skeleton" style="height:120px"></div>`);
  try {
    const body = await api(`/api/drawer/${encodeURIComponent(drawerId)}`);
    if (token !== drawerToken) return;
    const d = body.data || {};
    const content =
      d.content ?? d.content_text ?? d.document ?? JSON.stringify(d, null, 2);
    const el = document.getElementById("drawer-body");
    if (el) {
      el.innerHTML = `
      ${drawerMetaHtml(d.metadata || d)}
      <pre class="code">${esc(content)}</pre>`;
    }
  } catch (err) {
    if (token !== drawerToken) return;
    const el = document.getElementById("drawer-body");
    if (el) {
      el.innerHTML = `<div class="alert is-err">${t("drawer.loadFailed", { msg: esc(err.message) })}</div>`;
    }
  }
}

/* 三通道静默提醒（供总览与体检共用）：列出全部 ≥3 天无新条目的通道 */
export function stallAlerts(lastByRoom) {
  const items = [];
  for (const room of ["diary", "lessons", "decisions"]) {
    const last = lastByRoom?.[room];
    const days = daysSince(last);
    if (!last || days === null || days < 3) {
      continue;
    }
    items.push(t("sh.stallItem", { room, days, last: timeShort(last) }));
  }
  if (!items.length) {
    return "";
  }
  return `<div class="alert is-warn">${t("sh.stall", { items: items.join(" · ") })}</div>`;
}

/* 本地日期串（避免 toISOString 的 UTC 偏移：filed_at 为本地时间） */
function localDateStr(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

/* 按天横条（含空白日）：每行 = 日期 + 堆叠条（宽=当日总量占窗口峰值比）+ 总数 */
export function dayBars(perDay, daysCount) {
  const days = [];
  for (let i = daysCount - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days.push(localDateStr(d));
  }
  const totals = days.map((d) =>
    Object.values(perDay?.[d] || {}).reduce((a, b) => a + b, 0)
  );
  const max = Math.max(...totals, 1);
  const allZero = totals.every((t) => t === 0);
  const rows = days
    .map((day, idx) => {
      const byWing = perDay?.[day] || {};
      const segs = Object.entries(byWing)
        .sort((a, b) => b[1] - a[1])
        .map(
          ([w, c]) =>
            `<i style="width:${(c / max) * 100}%;background:${wingColor(w)}" title="${esc(
              day
            )} · ${esc(w)}: ${c}"></i>`
        )
        .join("");
      return `<div class="row" style="gap:8px;margin-bottom:3px;flex-wrap:nowrap">
        <span class="mono muted" style="width:74px;font-size:11px;flex-shrink:0">${esc(
          day.slice(5)
        )}</span>
        <div style="flex:1;height:14px;background:var(--surface-2);border-radius:4px;overflow:hidden;display:flex">${segs}</div>
        <span class="mono" style="width:42px;text-align:right;font-size:11px;flex-shrink:0">${
          totals[idx] || 0
        }</span>
      </div>`;
    })
    .join("");
  return { html: rows, allZero };
}
