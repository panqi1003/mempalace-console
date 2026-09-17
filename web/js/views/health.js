/* 运维健康：repair-status / hub.log 尾部与错误计数 / 备份表（新鲜度警报）/ 宫殿体积 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import { api, esc, viewHead, fmtBytes, daysSince, timeShort } from "./_shared.js";

function sourceChip(source) {
  if (source === "custom") return `<span class="chip">${t("he.srcCustom")}</span>`;
  if (source === "official-dir") return `<span class="chip is-ok">${t("he.srcOfficialDir")}</span>`;
  if (source === "official-file") return `<span class="chip is-ok">${t("he.srcOfficialFile")}</span>`;
  return `<span class="chip">—</span>`;
}

function backupRows(backups) {
  if (!backups.length) {
    return `<div class="muted" style="font-size:13px">${t("he.noBackups")}</div>`;
  }
  const last = backups[0];
  const age = daysSince(last.mtime_iso);
  let freshness;
  if (age === null) {
    freshness = `<div class="alert is-warn">${t("he.backupUnknownTime", { iso: esc(last.mtime_iso) })}</div>`;
  } else if (age > 7) {
    freshness = `<div class="alert is-warn">${t("he.backupOld", { days: age, iso: esc(last.mtime_iso) })}</div>`;
  } else {
    freshness = `<div class="alert is-ok">${t("he.backupRecent", { days: age, iso: esc(last.mtime_iso) })}</div>`;
  }
  return (
    freshness +
    `<table class="tbl">
    <tr><th>${t("he.thFile")}</th><th>${t("he.thSize")}</th><th>${t("he.thSource")}</th><th>${t("he.thTime")}</th></tr>
    ${backups
      .slice(0, 10)
      .map(
        (b) => `<tr><td class="mono" style="font-size:12px">${esc(b.name)}</td>
        <td class="mono">${b.is_dir ? t("he.dir") : b.size_bytes == null ? "—" : esc(String(b.size_bytes))}</td>
        <td>${sourceChip(b.source)}</td>
        <td class="mono muted" style="font-size:11px">${timeShort(b.mtime_iso)}</td></tr>`
      )
      .join("")}
  </table>`
  );
}

function logScan(logText) {
  const lines = String(logText || "").split("\n");
  const errors = lines.filter((l) => /\berror\b/i.test(l)).length;
  return { errors };
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("he.title"), t("he.sub"))}
    <div class="grid grid-3" id="health-cards">
      <div class="card"><div class="stat-num" id="h-size">…</div><div class="stat-label">${t("he.size")}</div></div>
      <div class="card"><div class="stat-num" id="h-backup-count">…</div><div class="stat-label">${t("he.backupCount")}</div></div>
      <div class="card" id="h-log-err-card"><div class="stat-num" id="h-log-err">…</div><div class="stat-label">${t("he.logErrors")}</div></div>
    </div>
    <div class="grid grid-2 mt-4" style="align-items:start">
      <div class="card"><h3 class="card-title">${t("he.repairCard")}</h3><pre class="code" id="h-repair"></pre></div>
      <div class="card"><h3 class="card-title">${t("he.backupCard")}</h3><div id="h-backup-list"></div></div>
    </div>
    <div class="card mt-4" id="h-log-card">
      <h3 class="card-title">${t("he.logCard")}</h3>
      <pre class="code" id="h-log"></pre>
    </div>`;

  const body = await api("/api/health/summary");
  const size = body.palace || {};
  container.querySelector("#h-size").textContent =
    size.size_bytes !== undefined ? fmtBytes(size.size_bytes) : "—";
  container.querySelector("#h-backup-count").textContent = String(
    (body.backups || []).length
  );
  if (body.hub_log_configured) {
    const scan = logScan(body.hub_log_tail);
    const errEl = container.querySelector("#h-log-err");
    errEl.textContent = String(scan.errors);
    errEl.style.color = scan.errors > 0 ? "var(--err)" : "var(--ok)";
    container.querySelector("#h-log").textContent = body.hub_log_tail || t("he.emptyLog");
  } else {
    container.querySelector("#h-log-err-card")?.remove();
    container.querySelector("#h-log-card")?.remove();
  }

  container.querySelector("#h-repair").textContent = body.repair_status || "";
  container.querySelector("#h-backup-list").innerHTML = backupRows(
    body.backups || []
  );
}

registerView("health", render);
