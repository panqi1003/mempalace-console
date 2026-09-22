/* 记忆体检：问题清单（铁律渲染）+ 30 天热力 + wake-up 注入预览 + 检索自测 + 态势卡 */

import { registerView, auditChipText } from "../app.js";
import { t } from "../i18n.js";
import {
  api,
  esc,
  num,
  pct,
  card,
  viewHead,
  chip,
  wingColor,
  fmtBytes,
  timeShort,
  dayBars,
  openDrawerById,
} from "./_shared.js";

const LAST_KEY = "mempalace_viz_audit_last";

function loadLast() {
  try {
    return JSON.parse(localStorage.getItem(LAST_KEY) || "null");
  } catch {
    return null;
  }
}

function saveLast(summary) {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify(summary));
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略 */
  }
}

function issueRow(a, { title, count, level, impact, cause, samples = [] }) {
  const cls = level === "err" ? "is-err" : level === "warn" ? "is-warn" : "is-ok";
  const sampleHtml = samples.length
    ? `<div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">${samples
        .map((s) =>
          typeof s === "string"
            ? `<button type="button" class="chip sample-chip" data-id="${esc(
                s
              )}" style="cursor:pointer" title="${t("au.tipDrawer")}">${esc(
                String(s).slice(0, 34)
              )}</button>`
            : `<button type="button" class="chip sample-chip" data-id="${esc(
                s.a
              )}" style="cursor:pointer" title="${esc(s.a)} ↔ ${esc(
                s.b
              )}">${esc(String(s.a).slice(0, 36))}… ↔ ${esc(
                String(s.b).slice(0, 36)
              )}…</button>`
        )
        .join("")}</div>`
    : "";
  return `<div class="alert ${cls}" style="flex-direction:column;align-items:stretch">
    <div class="row" style="justify-content:space-between">
      <strong>${esc(title)}</strong>
      <span class="mono">${t("au.rowCount", { n: num(count), pct: esc(pct(count, a.total)) })}</span>
    </div>
    <div class="muted" style="color:inherit;opacity:.85;font-size:12px">${t("au.impact", { text: esc(impact) })}</div>
    ${sampleHtml}
    ${
      cause
        ? `<details style="margin-top:4px"><summary style="cursor:pointer;font-size:12px">${t("au.cause")}</summary>
      <div style="font-size:12px;margin-top:4px">${esc(cause)}</div></details>`
        : ""
    }
  </div>`;
}

function findingsHtml(a) {
  const smp = a.issue_samples || {};
  const red = [];
  const yellow = [];
  if (a.unknown_wing > 0)
    red.push({
      title: t("au.issUnknownWingTitle"),
      count: a.unknown_wing,
      impact: t("au.issUnknownWingImpact"),
      cause: t("au.issUnknownWingCause"),
      samples: smp.unknown_wing,
    });
  if (a.no_wing > 0)
    red.push({
      title: t("au.issNoWingTitle"),
      count: a.no_wing,
      impact: t("au.issNoWingImpact"),
      cause: t("au.issNoWingCause"),
      samples: smp.no_wing,
    });
  if (a.no_source_mined > 0)
    red.push({
      title: t("au.issNoSourceTitle"),
      count: a.no_source_mined,
      impact: t("au.issNoSourceImpact"),
      cause: t("au.issNoSourceCause"),
      samples: smp.no_source,
    });
  if (a.no_room > 0)
    yellow.push({
      title: t("au.issNoRoomTitle"),
      count: a.no_room,
      impact: t("au.issNoRoomImpact"),
      cause: t("au.issNoRoomCause"),
      samples: [],
    });
  if (a.empty_preview > 0)
    yellow.push({
      title: t("au.issEmptyTitle"),
      count: a.empty_preview,
      impact: t("au.issEmptyImpact"),
      cause: t("au.issEmptyCause"),
      samples: smp.empty_preview,
    });
  if (a.dup_exact_pairs > 0)
    yellow.push({
      title: t("au.issDupExactTitle"),
      count: a.dup_exact_pairs,
      impact: t("au.issDupExactImpact"),
      cause: t("au.issDupExactCause"),
      samples: smp.dup_pairs,
    });
  if ((a.dup_semantic_sample || []).length > 0)
    yellow.push({
      title: t("au.issDupSemanticTitle"),
      count: a.dup_semantic_sample.length,
      impact: t("au.issDupSemanticImpact"),
      cause: t("au.issDupSemanticCause", { n: 5 }),
      samples: a.dup_semantic_sample.map((d) => d.drawer_id),
    });
  if (a.kg && a.kg.expired > 0 && a.kg.current === 0)
    yellow.push({
      title: t("au.issKgTitle"),
      count: a.kg.expired,
      impact: t("au.issKgImpact"),
      cause: t("au.issKgCause"),
      samples: [],
    });

  const normal = [];
  if (a.unknown_wing === 0)
    normal.push(t("au.normUnknownWingZero"));
  if (a.no_wing === 0) normal.push(t("au.normNoWing"));
  if (a.no_source_mined === 0) normal.push(t("au.normSourceComplete"));
  if (a.no_source_curated > 0)
    normal.push(t("au.normCuratedNoSource", { n: num(a.no_source_curated) }));
  if (a.empty_preview === 0) normal.push(t("au.normNoEmpty"));
  if (a.dup_exact_pairs === 0) normal.push(t("au.normNoDup"));

  const parts = [];
  const totalIssues = red.length + yellow.length;
  parts.push(
    `<div class="row" style="justify-content:space-between;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:13px">${t("au.summary", {
        total: totalIssues,
        red: red.length,
        yellow: yellow.length,
        n: num(a.total),
        sec: a.elapsed_s ?? "?",
      })}</span>
      <button id="audit-copy" style="font-size:12px">${t("au.copy")}</button>
    </div>`
  );
  if (totalIssues === 0) {
    parts.push(
      `<div class="alert is-ok">${t("au.noIssues", { n: num(a.total) })}</div>`
    );
  } else {
    parts.push(
      `<h3 class="card-title" style="color:var(--fg)">${t("au.issueListTitle", { red: red.length, yellow: yellow.length })}</h3>`
    );
    for (const item of red) parts.push(issueRow(a, { ...item, level: "err" }));
    for (const item of yellow) parts.push(issueRow(a, { ...item, level: "warn" }));
  }
  parts.push(
    `<details class="mt-2"><summary class="muted" style="cursor:pointer;font-size:12px">${t("au.normalItems", { n: normal.length })}</summary>
     <ul style="font-size:12px;color:var(--fg-low);margin:6px 0 0 18px">
       ${normal.map((s) => `<li>${esc(s)}</li>`).join("") || "<li>—</li>"}
     </ul></details>`
  );
  return parts.join("");
}

function wireSampleChips(holder) {
  holder.querySelectorAll(".sample-chip").forEach((btn) => {
    btn.addEventListener("click", () => openDrawerById(btn.dataset.id));
  });
}

function reportText(a) {
  const lines = [t("au.reportHead", { time: new Date().toLocaleString() })];
  lines.push(
    t("au.reportLine1", {
      total: a.total,
      sec: a.elapsed_s,
      cur: a.kg?.current ?? "?",
      exp: a.kg?.expired ?? "?",
    })
  );
  lines.push(
    t("au.reportLine2", {
      a: a.unknown_wing,
      b: a.no_wing,
      c: a.no_source_mined,
      d: a.no_source_curated,
    })
  );
  lines.push(
    t("au.reportLine3", {
      a: a.empty_preview,
      b: a.dup_exact_pairs,
      c: (a.dup_semantic_sample || []).length,
    })
  );
  lines.push(t("au.reportLine4", { field: (a.composition || { field: "ingest_mode" }).field, json: JSON.stringify((a.composition || { counts: a.by_ingest }).counts) }));
  return lines.join("\n");
}

function heatmap(perDay) {
  const { html, allZero } = dayBars(perDay, 30);
  const warn = allZero
    ? `<div class="alert is-warn">${t("au.noWrite30")}</div>`
    : "";
  return (
    warn +
    `<div style="max-height:280px;overflow-y:auto;overscroll-behavior:contain">${html}</div>`
  );
}

function stallRow(lastByRoom) {
  const rows = ["diary", "lessons", "decisions"].map((room) => {
    const last = lastByRoom?.[room];
    if (!last)
      return `<span class="chip">${t("au.stallNoRecord", { room })}</span>`;
    const days = Math.floor((Date.now() - new Date(last).getTime()) / 86400000);
    const cls = days >= 3 ? "is-warn" : "is-ok";
    return `<span class="chip ${cls}">${t("au.stallChip", {
      room,
      date: esc(String(last).slice(0, 10)),
      days,
    })}</span>`;
  });
  return `<div class="row" style="gap:8px">${rows.join("")}</div>`;
}

function wakeUpHtml(text) {
  if (!text) return `<div class="alert is-warn">${t("au.emptyOutput")}</div>`;
  return `<pre class="code" style="max-height:420px">${esc(text)}</pre>`;
}

async function render(container) {
  container.innerHTML = `
    ${viewHead(t("au.title"), t("au.sub"))}
    <div class="card">
      <div class="row" style="justify-content:space-between">
        <div class="row">
          <button id="audit-run" class="btn-primary">${t("au.run")}</button>
          <span class="muted" style="font-size:12px">${t("au.runHint")}</span>
        </div>
        <span id="audit-last" class="muted" style="font-size:12px"></span>
        <span id="audit-state" class="muted" style="font-size:12px" aria-live="polite"></span>
      </div>
      <div id="audit-findings" class="mt-4">
        <div class="muted" style="font-size:13px">${t("au.startHint")}</div>
      </div>
    </div>

    <div class="grid grid-2 mt-4">
      <div class="card">
        <h3 class="card-title">${t("au.activityCard")}</h3>
        <div id="audit-activity"><div class="skeleton" style="height:80px"></div></div>
      </div>
      <div class="card">
        <h3 class="card-title">${t("au.ingestCardBase")}</h3>
        <div id="audit-ingest"><div class="skeleton" style="height:80px"></div></div>
      </div>
    </div>

    <div class="grid grid-2 mt-4">
      <div class="card">
        <h3 class="card-title">${t("au.wakeupCard")}</h3>
        <div class="row mb-4">
          <input id="wu-wing" name="wing" autocomplete="off" placeholder="${t("au.wingPh")}" style="flex:1;min-width:0">
          <button id="wu-go" class="btn-primary">${t("au.preview")}</button>
        </div>
        <div id="wu-out"><div class="muted" style="font-size:13px">${t("au.wakeupHint")}</div></div>
      </div>
      <div class="card">
        <h3 class="card-title">${t("au.selfCard")}</h3>
        <div id="self-tests" class="row" style="gap:8px;margin-bottom:10px"></div>
        <div id="self-out" class="muted" style="font-size:13px">${t("au.selfHint")}</div>
      </div>
    </div>`;

  const activityBody = await api("/api/activity", { days: 30 });
  const act = activityBody.data;
  container.querySelector("#audit-activity").innerHTML =
    heatmap(act.per_day) + `<div class="mt-2">${stallRow(act.last_by_room)}</div>`;

  /* 数据构成先给骨架，体检运行后填充 */
  const ingEl = container.querySelector("#audit-ingest");
  ingEl.innerHTML = `<div class="muted" style="font-size:13px">${t("au.ingestHint")}</div>`;

  async function runAudit() {
    const state = container.querySelector("#audit-state");
    const holder = container.querySelector("#audit-findings");
    const btn = container.querySelector("#audit-run");
    btn.disabled = true;
    const t0 = Date.now();
    const ticker = setInterval(() => {
      state.textContent = t("au.scanning", { sec: Math.round((Date.now() - t0) / 1000) });
    }, 1000);
    state.textContent = t("au.scanning", { sec: 0 });
    holder.innerHTML = `<div class="skeleton" style="height:80px"></div>`;
    try {
      const body = await api("/api/audit", { samples: 5 });
      const a = body.data;
      state.textContent = "";
      holder.innerHTML = findingsHtml(a);
      wireSampleChips(holder);
      const copyBtn = holder.querySelector("#audit-copy");
      if (copyBtn)
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(reportText(a));
            copyBtn.textContent = t("au.copied");
            setTimeout(() => (copyBtn.textContent = t("au.copy")), 1500);
          } catch {
            copyBtn.textContent = t("au.copyFail");
          }
        });
      const comp = a.composition || { field: "ingest_mode", counts: a.by_ingest };
      const ingTitle = ingEl.closest(".card")?.querySelector(".card-title");
      if (ingTitle) ingTitle.textContent = t("au.ingestCard", { field: comp.field });
      renderIngest(ingEl, comp.counts, a.total);
      const redCount = holder.querySelectorAll(".alert.is-err").length;
      const yellowCount = holder.querySelectorAll(".alert.is-warn").length;
      const summary = {
        ts: new Date().toISOString(),
        red: redCount,
        yellow: yellowCount,
        total: a.total,
      };
      saveLast(summary);
      renderLast();
      const chip = document.getElementById("health-chip");
      if (chip) chip.textContent = auditChipText();
    } catch (err) {
      state.textContent = "";
      holder.innerHTML = `<div class="alert is-err">${t("au.failed", { msg: esc(err.message) })}</div>`;
    } finally {
      clearInterval(ticker);
      btn.disabled = false;
    }
  }

  function renderLast() {
    const el = container.querySelector("#audit-last");
    const last = loadLast();
    if (!last || !el) return;
    const when = new Date(last.ts);
    el.textContent = t("au.lastAudit", {
      when: when.toLocaleString(),
      red: last.red,
      yellow: last.yellow,
      n: last.total,
    });
  }

  function renderIngest(el, byIngest, total) {
    const entries = Object.entries(byIngest || {}).sort((a, b) => b[1] - a[1]);
    el.innerHTML = entries
      .map(
        ([k, c]) => `<div class="row" style="gap:8px;margin-bottom:6px">
        <span class="mono" style="width:120px">${esc(k)}</span>
        <div class="bar grow"><i style="width:${(c / Math.max(total, 1)) * 100}%;background:${
          k === "convos"
            ? "var(--ink-400)"
            : "var(--accent)"
        }"></i></div>
        <span class="mono muted" style="width:100px;text-align:right">${num(c)} · ${pct(
          c,
          total
        )}</span>
      </div>`
      )
      .join("");
  }

  /* 检索自测：数据驱动——用你自己宫殿的房间名做查询，判定 top3 是否命中该房间 */
  let selfTests = [];
  try {
    const tax = (await api("/api/taxonomy")).data || {};
    const roomCounts = new Map();
    for (const rooms of Object.values(tax)) {
      for (const [room, c] of Object.entries(rooms || {})) {
        roomCounts.set(room, (roomCounts.get(room) || 0) + (c || 0));
      }
    }
    selfTests = [...roomCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([room]) => ({ q: room, expect: [room] }));
  } catch {
    selfTests = [];
  }
  const selfHolder = container.querySelector("#self-out");
  if (!selfTests.length) {
    container.querySelector("#self-tests").innerHTML = "";
    selfHolder.innerHTML = `<div class="alert is-warn">${t("au.selfNoTax")}</div>`;
  } else {
    selfHolder.innerHTML = `<div class="muted" style="font-size:12px">${t("au.selfHint2")}</div>`;
    container.querySelector("#self-tests").innerHTML = selfTests
      .map((t, i) => `<button class="self-q" data-i="${i}">${esc(t.q)}</button>`)
      .join("");
  }
  container.querySelectorAll(".self-q").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = selfTests[Number(btn.dataset.i)];
      selfHolder.innerHTML = `<div class="skeleton" style="height:80px"></div>`;
      try {
        const body = await api("/api/search", { q: item.q, limit: 3 });
        const hits =
          body.data?.hits || body.data?.results || (Array.isArray(body.data) ? body.data : []);
        const blob = hits
          .map((h) => String(h.text ?? h.content_preview ?? ""))
          .join(" ")
          .toLowerCase();
        const roomHit = hits.some(
          (h) => String(h.room || "") === item.expect[0]
        );
        const hit = roomHit || blob.includes(item.expect[0].toLowerCase());
        selfHolder.innerHTML = `
          <div class="alert ${
            hit ? "is-ok" : "is-warn"
          }" style="margin-bottom:8px;font-size:12px">
            ${hit ? t("au.selfHit") : t("au.selfMiss", { room: esc(item.expect[0]) })} · ${t("au.selfNote")}
          </div>
          <table class="tbl">
          <tr><th>sim</th><th>wing/room</th><th>${t("au.thContent")}</th></tr>
          ${hits
            .map(
              (h) => `<tr>
              <td class="mono">${Number(h.similarity ?? 0).toFixed(2)}</td>
              <td><span class="chip">${esc(h.wing || "?")}/${esc(h.room || "?")}</span></td>
              <td style="font-size:12px">${esc(
                String(h.text ?? h.content_preview ?? "").slice(0, 120)
              )}</td>
            </tr>`
            )
            .join("")}
        </table>`;
      } catch (err) {
        selfHolder.innerHTML = `<div class="alert is-err">${esc(err.message)}</div>`;
      }
    });
  });

  /* wake-up 预览 */
  container.querySelector("#wu-go").addEventListener("click", async () => {
    const wing = container.querySelector("#wu-wing").value.trim();
    const out = container.querySelector("#wu-out");
    if (!wing) return;
    out.innerHTML = `<div class="skeleton" style="height:120px"></div>`;
    try {
      const body = await api("/api/wakeup", { wing });
      out.innerHTML = wakeUpHtml(body.data.text);
    } catch (err) {
      out.innerHTML = `<div class="alert is-err">${esc(err.message)}</div>`;
    }
  });

  container.querySelector("#audit-run").addEventListener("click", runAudit);
  renderLast();
}

registerView("audit", render);
