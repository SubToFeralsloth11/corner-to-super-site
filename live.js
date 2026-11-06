// Live review-loop page. Reads live.json straight from the repo's raw URL (updates within a
// minute or so of a push, without waiting for a Pages build), falling back to the Pages copy.
"use strict";
const RAW = "https://raw.githubusercontent.com/SubToFeralsloth11/corner-to-super-site/main/live.json";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
const when = (iso) => iso ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
const ago = (iso) => {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso)) / 1000);
  if (s < 60) return s + "s ago";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  return Math.round(s / 3600 * 10) / 10 + " h ago";
};
const card = (k, v) => `<div class="card"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
let data = null;

async function load() {
  for (const url of [RAW + "?t=" + Date.now(), "live.json?t=" + Date.now()]) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) return r.json();
    } catch (e) { /* try the next source */ }
  }
  throw new Error("live.json unavailable");
}

function render() {
  const d = data, s = d.status || {};
  const all = d.rounds.flatMap((r) => r.findings);
  const fixed = all.filter((f) => f.status === "fixed").length;
  const open = all.filter((f) => f.status === "open" || f.status === "wip").length;
  $("#fresh").innerHTML = `<span class="live-dot"></span>Last update ${esc(when(d.updated))} (${ago(d.updated)})`;
  $("#statuscards").innerHTML = [
    card("State", esc(s.state || "-")),
    card("Cycle / round", esc((s.cycle ? "Cycle " + s.cycle + " / " : "") + (s.round || "-"))),
    card("Area", esc(s.area || "-")),
    card("Doing now", esc(s.activity || "-") + `<div class="muted" style="font-size:.7em">${ago(s.since)}</div>`),
    card("Findings", `${all.length} <span class="muted" style="font-size:.7em">${fixed} fixed, ${open} open</span><div class="bar"><span style="width:${all.length ? fixed / all.length * 100 : 0}%"></span></div>`),
    card("Game commits", esc(d.game?.total_commits ?? "-")),
  ].join("");
  const ag = Object.entries(d.agents || {});
  $("#agents").innerHTML = ag.length ? "<table><tr><th>Agent</th><th>State</th><th>Task</th><th>Since</th></tr>" +
    ag.map(([n, a]) => `<tr><td>${esc(n)}</td><td>${esc(a.state)}</td><td>${esc(a.task)}</td><td>${ago(a.t)}</td></tr>`).join("") + "</table>" : "<p class='muted'>None.</p>";

  const hide = $("#hideClosed").checked, sev = $("#sevFilter").value;
  $("#rounds").innerHTML = d.rounds.slice().reverse().map((r, i) => {
    const fs = r.findings.filter((f) => (!hide || f.status === "open" || f.status === "wip") && (!sev || f.sev === sev))
      .sort((a, b) => a.sev.localeCompare(b.sev));
    const done = r.findings.filter((f) => f.status !== "open" && f.status !== "wip").length;
    return `<details class="round" ${i === 0 ? "open" : ""}><summary>${esc(r.id)}: ${esc(r.area)} &middot; ${done}/${r.findings.length} closed
      <span class="muted">(${when(r.started)}${r.finished ? " to " + when(r.finished) : ", in progress"})</span></summary>
      ${fs.map((f) => `<div class="finding"><span class="pill ${esc(f.sev)}">${esc(f.sev)}</span>
        <span class="pill st-${esc(f.status)}">${esc(f.status)}</span> <b>${esc(f.id)}</b> ${md(f.title)}
        ${f.file ? `<div><code>${esc(f.file)}</code></div>` : ""}
        ${f.detail ? `<div class="detail">${md(f.detail)}</div>` : ""}
        ${f.commit || f.note ? `<div class="detail">&rarr; ${f.commit ? "<code>" + esc(f.commit) + "</code> " : ""}${md(f.note)}</div>` : ""}
      </div>`).join("") || "<p class='muted'>Nothing to show.</p>"}</details>`;
  }).join("") || "<p class='muted'>No rounds yet.</p>";

  const kinds = [...new Set(d.log.map((l) => l.kind))];
  const kf = $("#kindFilter");
  if (kf.options.length - 1 !== kinds.length) {
    const cur = kf.value;
    kf.innerHTML = "<option value=''>Everything</option>" + kinds.map((k) => `<option>${esc(k)}</option>`).join("");
    kf.value = cur;
  }
  $("#logList").innerHTML = d.log.filter((l) => !kf.value || l.kind === kf.value).slice().reverse()
    .map((l) => `<li><time>${esc(when(l.t))}</time><span class="pill">${esc(l.kind)}</span> ${md(l.msg)}</li>`).join("");

  $("#testTable").innerHTML = d.tests.length ? "<table><tr><th>When</th><th>Passed</th><th>Failed</th><th>Note</th></tr>" +
    d.tests.slice().reverse().map((t) => `<tr><td>${esc(when(t.t))}</td><td>${t.passed}</td><td style="color:${t.failed ? "var(--red)" : "inherit"}">${t.failed}</td><td>${md(t.note)}</td></tr>`).join("") + "</table>" : "<p class='muted'>None yet.</p>";

  const g = d.game || {};
  $("#dirty").textContent = g.dirty?.length ? `Uncommitted changes in progress: ${g.dirty.join(", ")}` : "Working tree clean.";
  $("#commitList").innerHTML = (g.commits || []).map((c) => `<div class="commit"><code>${esc(c.sha)}</code> ${esc(c.subject)}
    <span class="muted">${esc(when(c.date))} &middot; ${esc(c.stat)}</span>${c.body ? `<pre>${esc(c.body)}</pre>` : ""}</div>`).join("");

  const m = d.machine || {};
  $("#machineCards").innerHTML = [
    card("Free memory", (m.mem_free_pct ?? "-") + "%"),
    card("Load (1/5/15 min)", esc((m.load || []).join(" / "))),
    card("Godot processes", esc(m.godot_procs ?? "-")),
    card("Sampled", esc(when(m.t))),
  ].join("");
}

async function tick() {
  try { data = await load(); render(); } catch (e) { $("#fresh").textContent = "Couldn't load live.json: " + e.message; }
}
for (const id of ["#hideClosed", "#sevFilter", "#kindFilter"]) document.addEventListener("DOMContentLoaded", () => $(id).addEventListener("change", () => data && render()));
tick();
setInterval(tick, 30000);
setInterval(() => data && ($("#fresh").innerHTML = `<span class="live-dot"></span>Last update ${esc(when(data.updated))} (${ago(data.updated)})`), 5000);
