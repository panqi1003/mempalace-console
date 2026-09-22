/* 总览：大数字卡、7 日写入活动、wing/room 分布、版本与完整性 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import {
  api,
  esc,
  num,
  statCard,
  card,
  viewHead,
  chip,
  wingColor,
  stallAlerts,
  dayBars,
} from "./_shared.js";

function statusBar(perDay) {
  const { html, allZero } = dayBars(perDay, 7);
  const warn = allZero
    ? `<div class="alert is-warn">${t("ov.noWrite7")}</div>`
    : "";
  return warn + html;
}

function distBars(counts, colorFn) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map(([, c]) => c), 1);
  return entries
    .slice(0, 12)
    .map(
      ([k, c]) => `<div class="row" style="gap:8px;margin-bottom:6px">
        <span class="mono" style="width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(k)}">${esc(k)}</span>
        <div class="bar grow"><i style="width:${(c / max) * 100}%;background:${colorFn(k)}"></i></div>
        <span class="mono muted" style="width:56px;text-align:right">${num(c)}</span>
      </div>`
    )
    .join("");
}

function integrityInfo(it) {
  if (!it || !it.checked) return { value: "—", sub: t("ov.integrityUnchecked") };
  if (it.ok) return { value: "OK", sub: t("ov.integrityOk") };
  return { value: "FAIL", sub: t("ov.integrityErrors", { n: Number(it.error_count ?? 0) }) };
}

async function render(container) {
  const [statusBody, activityBody] = await Promise.all([
    api("/api/overview"),
    api("/api/activity", { days: 7 }),
  ]);
  const s = statusBody.data || {};
  const activity = activityBody.data || {};
  const physicalTotal = s.total_drawers;
  const totalDrawers = activity.scan_total ?? physicalTotal;
  const wings = activity.by_wing || s.wings || {};
  const rooms = activity.by_room || s.rooms || {};
  const wingCount = Object.keys(wings).length;
  const roomCount = Object.keys(rooms).length;
  const integrity = integrityInfo(s.sqlite_integrity);
  const serving = (s.library_versions && s.library_versions.serving) || {};
  const lastByRoom = activity.last_by_room || {};
  const merged = Boolean(physicalTotal && totalDrawers && physicalTotal !== totalDrawers);
  const drawersSub = merged ? t("ov.statDrawersSubMerged") : t("ov.statDrawersSub");
  const drawersTip = merged ? t("ov.statDrawersTip", { n: num(physicalTotal) }) : "";

  const stall = stallAlerts(lastByRoom);

  container.innerHTML = `
    ${viewHead(t("ov.title"), t("ov.sub"))}
    ${stall}
    <div class="grid grid-4">
      ${statCard(num(totalDrawers), t("ov.statDrawers"), drawersSub, drawersTip)}
      ${statCard(wingCount, t("ov.statWings"), t("ov.statWingsSub"))}
      ${statCard(roomCount, t("ov.statRooms"), t("ov.statRoomsSub"))}
      ${statCard(integrity.value, t("ov.statIntegrity"), integrity.sub)}
    </div>

    ${card(t("ov.activity7"), statusBar(activity.per_day))}

    <div class="grid grid-2 mt-4" style="align-items:start">
      ${card(t("ov.wingDist"), distBars(wings, wingColor))}
      ${card(t("ov.roomDist"), distBars(rooms, () => "var(--accent)"))}
    </div>

    <div class="card mt-4">
      <h3 class="card-title">${t("ov.env")}</h3>
      <table class="tbl">
        <tr><th>${t("ov.envBackend")}</th><td class="mono">${esc(s.backend || "-")}</td></tr>
        <tr><th>mempalace</th><td class="mono">${esc(serving.mempalace || "-")}</td></tr>
        <tr><th>chromadb</th><td class="mono">${esc(serving.chromadb || "-")}</td></tr>
        <tr><th>${t("ov.envTiers")}</th><td>${Object.entries(statusBody.tiers || {})
          .map(([k, v]) => chip(`${k}=${v}`, v === "ok" ? "is-ok" : v === "fail" ? "is-err" : ""))
          .join(" ")}</td></tr>
      </table>
    </div>`;
}

registerView("overview", render);
