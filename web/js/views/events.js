/* 协调域：logstream 事件表（新→旧、类型色标）+ artifact 查看器 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, card, viewHead, chip, timeShort } from "./_shared.js";

let autoTimer = null;

function typeChip(t) {
  const cls = /task\.request|task\.reply|patch\.ready/.test(t || "")
    ? "is-ok"
    : /fail|block/.test(t || "")
    ? "is-err"
    : "";
  return `<span class="chip ${cls}">${esc(t || "?")}</span>`;
}

function eventsTable(events) {
  if (!events.length) {
    return `<div class="muted" style="font-size:13px">${t("ev.empty")}</div>`;
  }
  const sorted = [...events].sort(
    (a, b) => String(b.created_at || b.id || "").localeCompare(String(a.created_at || a.id || ""))
  );
  return `<table class="tbl">
    <tr><th>${t("ev.thTime")}</th><th>${t("ev.thType")}</th><th>${t("ev.thStream")}</th><th>${t("ev.thFromTo")}</th><th>${t("ev.thSummary")}</th></tr>
    ${sorted
      .slice(0, 80)
      .map(
        (e) => `<tr>
        <td class="mono muted" style="font-size:11px;white-space:nowrap">${timeShort(e.created_at)}</td>
        <td>${typeChip(e.type)}</td>
        <td class="mono muted" style="font-size:11px">${esc(e.stream || "")}/${esc(e.room || "")}</td>
        <td class="mono" style="font-size:11px">${esc(e.from_agent || "")} → ${esc(e.to_agent || "*")}</td>
        <td class="muted" style="font-size:12px">${esc(
          String(e.body || e.preview || "").slice(0, 120)
        )}</td>
      </tr>`
      )
      .join("")}
  </table>`;
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("ev.title"), t("ev.sub"))}
    <div class="card mb-4">
      <h3 class="card-title">${t("ui.introTitle")}</h3>
      <div class="muted" style="font-size:13px;line-height:1.9">
        ${t("ev.intro")}
      </div>
    </div>
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <div class="row">
          <button id="ev-refresh">${t("ev.refresh")}</button>
          <label class="row" style="gap:6px;font-size:13px;color:var(--fg-mid)">
            <input type="checkbox" id="ev-auto" style="width:auto"> ${t("ev.auto")}
          </label>
        </div>
        <div class="row">
          <input id="art-id" name="artifact_id" autocomplete="off" placeholder="${t("ev.artPh")}" style="width:220px">
          <button id="art-go">${t("ev.view")}</button>
        </div>
      </div>
    </div>
    <div class="card mt-4"><h3 class="card-title">${t("ev.streamCard")}</h3><div id="ev-list"></div></div>
    <div class="card mt-4"><h3 class="card-title">${t("ev.artCard")}</h3><div id="art-view"><div class="muted" style="font-size:13px">${t("ev.artHint")}</div></div></div>`;

  const list = container.querySelector("#ev-list");
  const auto = container.querySelector("#ev-auto");

  async function refresh() {
    list.innerHTML = `<div class="skeleton" style="height:120px"></div>`;
    try {
      const body = await api("/api/events", { limit: 100 });
      const data = body.data || {};
      const events = data.events || data.results || (Array.isArray(data) ? data : []);
      list.innerHTML = eventsTable(events);
    } catch (err) {
      list.innerHTML = `<div class="alert is-err">${t("app.loadFailed", { msg: esc(err.message) })}</div>`;
    }
  }

  container.querySelector("#ev-refresh").addEventListener("click", refresh);
  if (autoTimer) {
    clearInterval(autoTimer);
    autoTimer = null;
  }
  auto.addEventListener("change", () => {
    if (autoTimer) clearInterval(autoTimer);
    autoTimer = auto.checked ? setInterval(refresh, 10000) : null;
  });

  container.querySelector("#art-go").addEventListener("click", async () => {
    const id = container.querySelector("#art-id").value.trim();
    const holder = container.querySelector("#art-view");
    if (!id) return;
    holder.innerHTML = `<div class="skeleton" style="height:80px"></div>`;
    try {
      const body = await api(`/api/artifact/${encodeURIComponent(id)}`);
      const a = body.data || {};
      holder.innerHTML = `
        <dl class="drawer-meta">
          <dt>id</dt><dd>${esc(a.id || id)}</dd>
          <dt>kind</dt><dd>${esc(a.kind || "-")}</dd>
          <dt>created_by</dd><dd>${esc(a.created_by || "-")}</dd>
          <dt>sha256</dt><dd>${esc(String(a.sha256 || "").slice(0, 24))}${String(a.sha256 || "").length > 24 ? "…" : ""}</dd>
        </dl>
        <pre class="code">${esc(a.content ?? JSON.stringify(a, null, 2))}</pre>`;
    } catch (err) {
      holder.innerHTML = `<div class="alert is-err">${t("app.loadFailed", { msg: esc(err.message) })}</div>`;
    }
  });

  await refresh();
}

registerView("events", render);
