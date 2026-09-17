/* MemPalace 可视化管理台 · 应用外壳：fetch 封装 / hash 路由 / 状态灯 / 骨架屏 / 详情面板 / 语言切换 */

import { t, getLang, setLang, applyStatic } from "./i18n.js";

export async function api(path, params = {}, opts = {}) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const resp = await fetch(url, {
    signal: opts.signal,
    headers: { "Accept-Language": getLang() === "zh" ? "zh-CN" : "en" },
  });
  let body = {};
  try {
    body = await resp.json();
  } catch {
    /* 非 JSON 响应保留空对象 */
  }
  if (!resp.ok) {
    const err = new Error(body?.error?.message || `HTTP ${resp.status}`);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

export function skeleton(el, rows = 4) {
  container_set(
    container_of(el),
    `<div class="card"><div class="skeleton" style="height:22px;width:38%"></div></div>
     <div class="grid grid-2 mt-4">
       ${Array.from({ length: rows }, () => `<div class="skeleton" style="height:88px"></div>`).join("")}
     </div>`
  );
}

function container_set(container, html) {
  container.innerHTML = html;
}

function container_of(el) {
  return el instanceof Element ? el : document.getElementById(el);
}

/* ---------- 详情侧滑面板 ---------- */
const panel = () => document.getElementById("drawer-panel");

export function openDrawer(title, bodyHtml) {
  const p = panel();
  if (!p) return;
  document.getElementById("drawer-title").textContent = title;
  document.getElementById("drawer-body").innerHTML = bodyHtml;
  p.classList.add("is-open");
  p.setAttribute("aria-hidden", "false");
  p.removeAttribute("inert");
}
export function closeDrawer() {
  const p = panel();
  if (!p) return;
  p.classList.remove("is-open");
  p.setAttribute("aria-hidden", "true");
  p.setAttribute("inert", "");
}
document.getElementById("drawer-close")?.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDrawer();
});
document.getElementById("skip-link")?.addEventListener("click", (e) => {
  e.preventDefault();
  const main = document.getElementById("main");
  if (main) {
    main.focus();
    main.scrollIntoView();
  }
});

/* ---------- 视图注册与路由 ---------- */
const views = {}; // name -> render(container)

export function registerView(name, render) {
  views[name] = render;
}

const ROUTES = [
  "overview",
  "structure",
  "search",
  "kg",
  "graph",
  "diary",
  "events",
  "health",
  "audit",
];

function currentRoute() {
  const h = location.hash.replace(/^#\//, "");
  return ROUTES.includes(h) ? h : "overview";
}

export async function navigate() {
  const name = currentRoute();
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("is-active"));
  const container = document.getElementById(`view-${name}`);
  container.classList.add("is-active");
  document.querySelectorAll("#rail a").forEach((a) => {
    a.classList.toggle("is-active", a.dataset.view === name);
  });
  const render = views[name];
  if (render) {
    container.innerHTML = `<div class="skeleton" style="height:24px;width:30%;margin-bottom:16px"></div><div class="skeleton" style="height:300px"></div>`;
    try {
      await render(container);
    } catch (err) {
      container.innerHTML = `<div class="alert is-err">${t("app.loadFailed", { msg: esc(err.message || err) })}</div>`;
    }
  }
}
window.addEventListener("hashchange", navigate);

/* ---------- 顶栏状态灯与全局搜索 ---------- */
async function refreshStatus() {
  const dot = document.getElementById("tier-dot");
  const chip = document.getElementById("health-chip");
  if (chip) chip.textContent = auditChipText();
  try {
    const body = await api("/api/overview");
    const tiers = body.tiers || {};
    let state = "err";
    if (tiers.hub === "ok") state = "ok";
    else if (tiers.stdio === "ok") state = "warn";
    if (!dot) return;
    dot.className = `tier-dot ${state === "ok" ? "is-ok" : state === "err" ? "is-err" : ""}`;
    const label = state === "ok" ? t("app.tierOk") : state === "warn" ? t("app.tierWarn") : t("app.tierErr");
    dot.title = label;
    dot.setAttribute("aria-label", label);
  } catch {
    if (!dot) return;
    dot.className = "tier-dot is-err";
    dot.title = t("app.tierAllDown");
    dot.setAttribute("aria-label", t("app.tierAllDown"));
  }
}

/* ---------- 顶栏状态灯与全局搜索 ---------- */
export const pending = { q: null };

export function auditChipText() {
  try {
    const raw = localStorage.getItem("mempalace_viz_audit_last");
    if (!raw) return t("app.chipRun");
    const last = JSON.parse(raw);
    const d = new Date(last.ts);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return t("app.chipCount", { red: last.red, yellow: last.yellow, time: `${hh}:${mm}` });
  } catch {
    return t("app.chipRun");
  }
}

document.getElementById("health-chip")?.addEventListener("click", () => {
  location.hash = "#/audit";
});

document.getElementById("global-search")?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const q = e.target.value.trim();
  if (!q) return;
  pending.q = q;
  e.target.value = "";
  if (location.hash === "#/search") {
    navigate();
  } else {
    location.hash = "#/search";
  }
});

/* ---------- 语言切换 ---------- */
function syncLangSwitch() {
  document.querySelectorAll("#lang-switch button[data-lang]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.lang === getLang()));
  });
}

document.querySelectorAll("#lang-switch button[data-lang]").forEach((b) => {
  b.addEventListener("click", () => {
    if (b.dataset.lang !== getLang()) setLang(b.dataset.lang);
  });
});

document.addEventListener("mviz:lang", async () => {
  applyStatic(document);
  syncLangSwitch();
  refreshStatus();
  await navigate();
});

/* ---------- 启动 ---------- */
applyStatic(document);
syncLangSwitch();
import("/web/js/views/index.js")
  .then(() => navigate())
  .catch((err) => {
    const el = document.getElementById("view-overview");
    if (el) {
      el.classList.add("is-active");
      el.innerHTML = `<div class="alert is-err">${t("app.viewFailed", { msg: esc(err.message || err) })}</div>`;
    }
  });
refreshStatus();
setInterval(refreshStatus, 30000);
