/* 宫殿导航图：wing 规模图 + tunnels/hallways 列表 + room traverse 探索 */

import { registerView } from "../app.js";
import { t } from "../i18n.js";
import {
  api,
  esc,
  num,
  card,
  viewHead,
  chip,
  wingColor,
  cssColor,
} from "./_shared.js";

let chart = null;
let resizeHandler = null;

function tunnelsTable(tunnels) {
  if (!tunnels.length) return `<div class="alert is-warn">${t("gr.noTunnelsShort")}</div>`;
  return `<table class="tbl">
    <tr><th>${t("gr.thSource")}</th><th>${t("gr.thTarget")}</th><th>${t("gr.thLabel")}</th></tr>
    ${tunnels
      .map(
        (t) => `<tr>
        <td class="mono" style="font-size:12px">${esc(
          t.source_wing || ""
        )} / ${esc(t.source_room || "")}</td>
        <td class="mono" style="font-size:12px">${esc(
          t.target_wing || ""
        )} / ${esc(t.target_room || "")}</td>
        <td class="muted" style="font-size:12px">${esc(t.label || "")}</td>
      </tr>`
      )
      .join("")}
  </table>`;
}

function walkHtml(rooms, totalRooms) {
  if (!rooms.length) return `<div class="muted" style="font-size:13px">${t("gr.noLinkRows")}</div>`;
  const converged = totalRooms > 0 && rooms.length >= totalRooms;
  const note = converged
    ? `<div class="alert is-warn" style="font-size:12px;margin-bottom:8px">${t("gr.convergeNote")}</div>`
    : "";
  return (
    note +
    `<table class="tbl">
    <tr><th>${t("gr.thRoom")}</th><th>${t("gr.thCount")}</th><th>${t("gr.thWing")}</th><th>${t("gr.thHow")}</th></tr>
    ${rooms
      .map((r) => {
        const wings = (r.wings || [r.wing]).filter(Boolean);
        const halls = r.halls || [];
        let how;
        if (r.hop === 0) {
          how = `<span class="chip">${t("gr.start")}</span>`;
        } else if (halls.length) {
          how = halls.map((h) => chip(h, "is-ok")).join(" ");
        } else if (r.connected_via && r.connected_via.length) {
          how = `<span class="muted" style="font-size:12px">${t("gr.sameWing", { wings: esc(r.connected_via.join("、")) })}</span>`;
        } else {
          how = `<span class="muted" style="font-size:12px">—</span>`;
        }
        return `<tr>
        <td class="mono" style="font-size:12px">${esc(r.room || "")}</td>
        <td class="mono">${num(r.count ?? 0)}</td>
        <td>${wings.map((w) => chip(w)).join(" ")}</td>
        <td>${how}</td>
      </tr>`;
      })
      .join("")}
  </table>`
  );
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("gr.title"), t("gr.sub"))}
    <div class="card mb-4">
      <h3 class="card-title">${t("ui.introTitle")}</h3>
      <div class="muted" style="font-size:13px;line-height:1.9">
        ${t("gr.intro")}
      </div>
    </div>
    <div class="grid grid-3">
      <div class="card"><div class="stat-num" id="g-rooms">…</div><div class="stat-label">${t("gr.statRooms")}</div></div>
      <div class="card"><div class="stat-num" id="g-tunnel-rooms">…</div><div class="stat-label">${t("gr.statTunnelRooms")}</div></div>
      <div class="card"><div class="stat-num" id="g-edges">…</div><div class="stat-label">${t("gr.statEdges")}</div></div>
    </div>
    <div class="grid grid-2 mt-4">
      <div class="card">
        <h3 class="card-title">${t("gr.chartTitle")}</h3>
        <div id="g-chart" style="height:400px"></div>
      </div>
      <div class="card">
        <h3 class="card-title">${t("gr.traverseTitle")}</h3>
        <div class="row mb-4">
          <select id="tr-room" style="flex:1;min-width:0"><option value="">${t("gr.loadingRooms")}</option></select>
          <select id="tr-hops" aria-label="${t("gr.hopsAria")}">
            <option value="1">${t("gr.hopSingle")}</option>
            <option value="2" selected>${t("gr.hopMany", { n: 2 })}</option>
            <option value="3">${t("gr.hopMany", { n: 3 })}</option>
            <option value="4">${t("gr.hopMany", { n: 4 })}</option>
            <option value="5">${t("gr.hopMany", { n: 5 })}</option>
          </select>
          <button id="tr-go" class="btn-primary">${t("gr.go")}</button>
        </div>
        <div id="tr-result" style="max-height:340px;overflow-y:auto">
          <div class="muted" style="font-size:13px">${t("gr.pickHint")}</div>
        </div>
      </div>
    </div>
    <div class="grid grid-2 mt-4">
      <div class="card"><h3 class="card-title">${t("gr.tunnelsCard")}</h3><div id="g-tunnels"></div></div>
      <div class="card"><h3 class="card-title">${t("gr.hallwaysCard")}</h3><div id="g-hallways"></div></div>
    </div>`;

  const stats = (await api("/api/graph/stats")).data || {};
  container.querySelector("#g-rooms").textContent = num(stats.total_rooms);
  container.querySelector("#g-tunnel-rooms").textContent = num(stats.tunnel_rooms);
  container.querySelector("#g-edges").textContent = num(stats.total_edges);

  const [tunnelsBody, hallwaysBody, taxBody] = await Promise.all([
    api("/api/graph/tunnels"),
    api("/api/graph/hallways"),
    api("/api/taxonomy").catch(() => ({ data: {} })),
  ]);
  const tunnels = tunnelsBody.data.tunnels || tunnelsBody.data || [];
  const hallways = hallwaysBody.data.hallways || hallwaysBody.data || [];
  const tunnelList = Array.isArray(tunnels) ? tunnels : tunnels.tunnels || [];
  container.querySelector("#g-tunnels").innerHTML = tunnelList.length
    ? tunnelsTable(tunnelList)
    : `<div class="muted" style="font-size:13px">${t("gr.noTunnels")}</div>`;
  const hw = Array.isArray(hallways) ? hallways : [];
  container.querySelector("#g-hallways").innerHTML = hw.length
    ? `<table class="tbl"><tr><th>${t("gr.thRoomA")}</th><th>${t("gr.thRoomB")}</th><th>wing</th></tr>
      ${hw.slice(0, 40).map((h) => `<tr><td class="mono" style="font-size:12px">${esc(h.a || h.room_a || h.room || "")}</td><td class="mono" style="font-size:12px">${esc(h.b || h.room_b || "")}</td><td>${chip(h.wing || "?")}</td></tr>`).join("")}</table>`
    : `<div class="muted" style="font-size:13px">${t("gr.noHallways")}</div>`;

  /* 房间下拉：从你自己宫殿的 taxonomy 生成，带条目数，不用记名字 */
  const tax = taxBody.data || {};
  const roomCounts = new Map();
  for (const rooms of Object.values(tax)) {
    for (const [room, c] of Object.entries(rooms || {})) {
      roomCounts.set(room, (roomCounts.get(room) || 0) + (Number(c) || 0));
    }
  }
  const roomOptions = [...roomCounts.entries()].sort((a, b) => b[1] - a[1]);
  const trSelect = container.querySelector("#tr-room");
  if (roomOptions.length) {
    trSelect.innerHTML = roomOptions
      .map(([room, c]) => `<option value="${esc(room)}">${esc(t("gr.roomOption", { room, n: num(c) }))}</option>`)
      .join("");
  } else {
    trSelect.innerHTML = `<option value="">${t("gr.noRooms")}</option>`;
  }

  const wingSizes = stats.rooms_per_wing || {};
  const gNodes = Object.entries(wingSizes).map(([w, c]) => ({
    name: w,
    value: c,
    symbolSize: 30 + Math.sqrt(c) * 8,
    itemStyle: { color: cssColor(wingColor(w)) },
  }));
  const topTunnels = stats.top_tunnels || [];
  const gEdges = topTunnels
    .filter((t) => Array.isArray(t.wings) && t.wings.length >= 2)
    .map((t) => ({
      source: t.wings[0],
      target: t.wings[1],
      roomName: t.room || "",
      count: t.count || 0,
      lineStyle: {
        width: Math.max(1, Math.min(8, (t.count || 0) / 4)),
        color: cssColor("var(--ink-400)"),
        opacity: 0.7,
      },
    }));
  const chartDom = container.querySelector("#g-chart");
  if (chart && !chart.isDisposed()) chart.dispose();
  chart = echarts.init(chartDom);
  chart.setOption({
    backgroundColor: "transparent",
    tooltip: {
      formatter: (p) => {
        if (p.dataType === "edge") {
          const d = p.data || {};
          return `${esc(String(d.source))} ↔ ${esc(String(d.target))}<br>${t("gr.tooltipShared", { room: esc(String(d.roomName || "?")) })}`;
        }
        return t("gr.tooltipRooms", { wing: esc(String(p.name ?? "")), n: esc(String(p.value ?? "")) });
      },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        roam: true,
        force: { repulsion: 600, gravity: 0.12, edgeLength: 160 },
        label: {
          show: true,
          color: cssColor("var(--ink-000)"),
          fontSize: 12,
          fontFamily: "monospace",
          textBorderColor: cssColor("var(--bg-deep)"),
          textBorderWidth: 3,
        },
        labelLayout: { hideOverlap: true },
        data: gNodes,
        links: gEdges,
      },
    ],
  });
  if (resizeHandler) window.removeEventListener("resize", resizeHandler);
  resizeHandler = () => {
    if (chart && !chart.isDisposed()) chart.resize();
  };
  window.addEventListener("resize", resizeHandler);

  const go = container.querySelector("#tr-go");
  const holder = container.querySelector("#tr-result");
  go.addEventListener("click", async () => {
    const room = container.querySelector("#tr-room").value.trim();
    if (!room) {
      holder.innerHTML = `<div class="alert is-warn">${t("gr.pickRoomFirst")}</div>`;
      return;
    }
    holder.innerHTML = `<div class="skeleton" style="height:80px"></div>`;
    try {
      const body = await api("/api/graph/traverse", {
        room,
        hops: container.querySelector("#tr-hops").value,
      });
      const data = body.data || {};
      const raw = data.rooms ?? data;
      const list = Array.isArray(raw) ? raw : Object.values(raw || {});
      if (!list.length) {
        holder.innerHTML = `<div class="muted" style="font-size:13px">${t("gr.noRelated", {
          room: esc(room),
          hops: container.querySelector("#tr-hops").value,
        })}</div>`;
        return;
      }
      holder.innerHTML = `<div class="muted mb-4" style="font-size:12px">${t("gr.related", {
        room: esc(room),
        n: list.length,
      })}</div>${walkHtml(list, stats.total_rooms)}`;
    } catch (err) {
      holder.innerHTML = `<div class="alert is-err">${esc(err.message)}</div>`;
    }
  });
}

registerView("graph", render);
