/* 閲覧専用。書込みは既存CLIだけが行う。 */
"use strict";
const M = window.ExplorerModel;
const $ = id => document.getElementById(id);
const state = {data: null, selected: null, version: null, relation: null, collapsed: new Set(),
  rows: new Map(), disconnected: false, highlights: new Map(), highlightTimes: new Map(), latestDiff: null, observed: null,
  mode: "LIVE", generation: 0, replay: null, event: null, relationVersion: null};
const labels = {draft: "草稿", proposed: "提案", accepted: "採択", rejected: "不採用", retired: "終了", superseded: "置換済み",
  active: "有効な関係", candidate: "候補", confirmed: "確定", current: "記録した版は一致", changed: "根拠版が変更", untracked: "対象版は未追跡", not_applicable: "版比較の対象外"};
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, className) {
  const node = el("button", text, className); node.type = "button"; node.addEventListener("click", action); return node;
}
function badge(text) { return el("span", text, "badge"); }
function select(id, version = null) {
  state.selected = id; state.version = version; state.relation = null; state.event = null; state.latestDiff = null;
  if (nodeById(id)?.kind === "scope") {
    for (const group of M.groups(state.data)) if (group.id === id) {
      state.collapsed.delete(id); group.ancestors.forEach(parent=>state.collapsed.delete(parent));
    }
  }
  renderRows(); renderDetails();
  if (nodeById(id)?.kind === "scope") {
    [...$("rows").querySelectorAll(".scope-row")].find(row=>row.dataset.scopeId === id)?.scrollIntoView({block:"nearest"});
  }
}
function selectRelation(id, version = null) {
  state.relation = id; state.relationVersion = version; state.event = null; renderDetails();
}
function showEvent(event) {state.event = event; state.relation = null; renderDetails();}
function changeLabel(change) {
  if (change.type === "relation") return `${change.before ? "関係の改訂" : "関係の追加"} / ${change.after.relation_kind}`;
  if (change.after.kind !== "agreement") return `${change.before ? "改訂" : "追加"} / ${change.after.kind}`;
  if (change.after.lifecycle !== "accepted") return labels[change.after.lifecycle];
  return change.before?.lifecycle === "accepted" ? "REVISED" : "NEW";
}
function nodeById(id) { return state.data.nodes.find(n => n.id === id); }
function number(id) {return M.displayNumber(state.data,id);}
function named(id) {const node=nodeById(id);return node ? `${number(id)} ${node.title}` : id;}
function appendReference(container,id,{prefix="",suffix="",title=null}={}) {
  if (prefix) container.append(document.createTextNode(prefix));
  const node=nodeById(id);
  if (node) container.append(el("span",number(id),"object-number"),document.createTextNode(` ${title ?? node.title}${suffix}`));
  else container.append(document.createTextNode(id + suffix));
  return container;
}
function referenceButton(id,action,className,options) {return appendReference(button(null,action,className),id,options);}
function exportButton(id) {
  const action = button("↓ Markdown",()=>exportScope(id,action),"export-button");
  action.title = `${named(id)}の合意と文脈を、表示中の版で1つの${number(id)}.mdへ書き出します。`;
  action.setAttribute("aria-label",`${named(id)}をMarkdownで書き出す`);
  return action;
}
async function exportScope(id,action) {
  const data=state.data, meta=data.meta, label=M.displayNumber(data,id);
  action.disabled=true; $("export-status").textContent=`${label}のMarkdownを準備しています。`;
  try {
    const path=[meta.database_id,meta.graph_revision,meta.snapshot_id,id].map(value=>encodeURIComponent(value)).join("/");
    const response=await fetch(`/api/export/scope/${path}`,{cache:"no-store",signal:AbortSignal.timeout(15000)});
    if (!response.ok) {const error=await response.json();throw new Error(error.error?.message||"書き出しに失敗しました。");}
    const url=URL.createObjectURL(await response.blob()),link=el("a");
    link.href=url;link.download=`${label}.md`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    $("export-status").textContent=`${label}.md / rev ${meta.graph_revision}のダウンロードを開始しました。`;
  } catch(error) {$("export-status").textContent=error.message;}
  finally {action.disabled=false;}
}
function firstAgreement(data) {
  for (const group of M.groups(data)) {
    const members = data.nodes.filter(n => n.kind === "agreement" && n.lifecycle === "accepted" &&
      (group.id ? (data.scope_ids[n.id] || []).includes(group.id) : !(data.scope_ids[n.id] || []).length));
    members.sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.id.localeCompare(b.id));
    if (members.length) return members[0].id;
  }
  return null;
}
function renderRows() {
  const data = state.data;
  if (!data) return;
  const query = $("filter").value.normalize("NFKC").toLocaleLowerCase().trim();
  const terms = query.split(/\s+/).filter(Boolean);
  const showAll = $("all-states").checked;
  const agreements = data.nodes.filter(n => n.kind === "agreement" && (showAll || n.lifecycle === "accepted"));
  const visible = agreements.filter(n => M.matchesQuery(data,n,terms));
  const wanted = new Set(), container = $("rows");
  const references = new Set();
  let rowCount = 0;
  function put(key, signature, create) {
    wanted.add(key);
    let entry = state.rows.get(key);
    if (!entry || entry.signature !== signature) {
      const node = create();
      if (entry) entry.node.replaceWith(node);
      entry = {node, signature}; state.rows.set(key, entry);
    }
    container.append(entry.node);
  }
  for (const group of M.groups(data)) {
    if (group.ancestors.some(id => state.collapsed.has(id))) continue;
    const items = visible.filter(n => group.id ? (data.scope_ids[n.id] || []).includes(group.id) : !(data.scope_ids[n.id] || []).length)
      .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
    if (!group.id && !items.length || query && !items.length && state.selected !== group.id) continue;
    const collapsed = state.collapsed.has(group.id);
    const key = `scope:${group.ancestors.join("/")}/${group.id}`;
    put(key, JSON.stringify([group.node, collapsed, items.length, group.depth, group.reference, state.selected === group.id, data.display_numbers[group.id]]), () => {
      const row = el("div", null, "scope-row");
      row.dataset.scopeId = group.id; row.classList.toggle("selected",state.selected === group.id);
      const toggle = button(null, () => {
        state.collapsed.has(group.id) ? state.collapsed.delete(group.id) : state.collapsed.add(group.id); renderRows();
      }, "scope-toggle");
      const title=`${group.node.title}${group.reference ? "（参照）" : ""}`;
      toggle.append(document.createTextNode(`${collapsed ? "▸" : "▾"} `));
      if (group.id) appendReference(toggle,group.id,{title});
      else toggle.append(document.createTextNode(title));
      toggle.style.paddingLeft = `${16 + group.depth * 18}px`; toggle.setAttribute("aria-expanded", String(!collapsed));
      const info=el("div",null,"scope-info");info.append(el("span",`${items.length} AGREEMENTS`,"scope-count"));
      if (group.id) info.append(exportButton(group.id));
      row.append(toggle,info,el("span", "明示された所属のみ")); return row;
    });
    if (collapsed) continue;
    for (const n of items) {
      references.add(n.id); rowCount++;
      const contexts = M.contexts(data, n.id);
      const highlight = state.highlights.get(n.id);
      put(`${key}:${n.id}`, JSON.stringify([n, contexts, highlight, state.selected === n.id, data.scope_ids[n.id],data.display_numbers[n.id]]), () => {
        const row = el("div", null, "data-row"); row.dataset.nodeId = n.id;
        row.classList.toggle("selected", state.selected === n.id);
        row.classList.toggle("changed", Boolean(highlight));
        row.classList.toggle("terminal", ["retired", "rejected", "superseded"].includes(n.lifecycle));
        const scopes = data.scope_ids[n.id] || [];
        const left = el("div", scopes.length > 1 ? `↳ ${scopes.length}範囲に所属` : "↳", "scope-cell");
        left.title = scopes.map(named).join(" / ");
        left.style.paddingLeft = `${22 + group.depth * 18}px`;
        const item = button(null, () => select(n.id), "item-button");
        if (highlight && highlight !== labels[n.lifecycle]) item.append(badge(highlight));
        if (n.lifecycle !== "accepted") item.append(badge(labels[n.lifecycle]));
        item.title = named(n.id);
        item.append(el("span", number(n.id), "object-number"), el("span", `◎ ${n.title}`, "item-title"));
        const context = el("div", null, "context-cell");
        for (const entry of contexts.slice(0, 3)) {
          const r = entry.relation;
          const node = button(`${r.confirmation === "candidate" ? "候補 · " : ""}${named(entry.node.id)}`, () => select(entry.node.id), "context-button");
          node.classList.toggle("candidate", r.confirmation === "candidate"); context.append(node);
        }
        if (!contexts.length) context.append(el("span", "文脈は未登録", "muted"));
        if (contexts.length > 3) context.append(el("span", `ほか${contexts.length - 3}件 / 詳細へ`, "muted"));
        row.append(left, item, context); return row;
      });
    }
  }
  for (const [key, entry] of state.rows) if (!wanted.has(key)) {entry.node.remove(); state.rows.delete(key);}
  container.querySelectorAll(".empty").forEach(node => node.remove());
  if (!references.size) container.append(el("p", "表示条件に一致する合意はありません。", "empty"));
  $("counts").textContent = `合意 ${references.size} / ${data.nodes.filter(n => n.kind === "agreement").length}件 · 表示 ${rowCount}行（複数所属の参照を含む） · 全${data.selection.nodes}ノード`;
}
function appendDiff(container, before, after) {
  if (!before || !after) return;
  const a = `${before.title}\n${before.body}`, b = `${after.title}\n${after.body}`;
  if (a === b) return;
  const diff = M.textDiff(a, b), block = el("div", null, "diff");
  block.append(el("span", "REVISED / 保存された本文の差分", "diff-label"), document.createTextNode(diff.prefix));
  if (diff.removed) block.append(el("del", diff.removed));
  if (diff.removed && diff.added) block.append(document.createTextNode(" → "));
  if (diff.added) block.append(el("ins", diff.added));
  block.append(document.createTextNode(diff.suffix)); container.append(block);
}
function renderDetails() {
  const data = state.data, container = $("details");
  if (!data) return;
  if (state.event) {
    const event = state.event;
    container.replaceChildren(badge(`保存された履歴 / commit ${event.graph_revision}`), el("h1", `COMMIT ${event.graph_revision}`),
      el("p", `${event.created_at}\nsnapshot: ${event.snapshot_id}`, "metadata"), el("p", `判断理由: ${event.reason}`, "note"));
    $("selected-kind").textContent = "commit / 過去の記録";
    const provenance = data.provenance.find(p => p.id === event.provenance_id);
    if (provenance) container.append(el("p", `実行者: ${provenance.actor}\n指示の参照: ${provenance.decision?.authority_ref || "未登録"}`, "note"));
    for (const c of event.changes) {
      const heading=el("h2");
      if (c.type === "node") appendReference(heading,c.id,{prefix:`${changeLabel(c)} / `,title:c.after.title});
      else heading.textContent=`${changeLabel(c)} / ${c.after.relation_kind}`;
      container.append(heading,el("div", `内部ID: ${c.id}`, "metadata"));
      if (c.type === "node") {
        appendDiff(container, c.before, c.after);
        if (c.before) container.append(button("保存前の原文", () => select(c.id,c.before.revision_id)));
        container.append(button("保存後の原文と判断", () => select(c.id,c.after.revision_id)));
      } else {
        if (c.before) container.append(button("保存前の関係", () => selectRelation(c.id,c.before.revision_id)));
        container.append(button("保存後の関係", () => selectRelation(c.id,c.after.revision_id)));
      }
    }
    return;
  }
  if (state.relation) {
    const rev = data.revisions.find(r => r.target_type === "relation" && r.target_id === state.relation && r.revision_id === state.relationVersion);
    const relation = rev?.snapshot || (!state.relationVersion && data.relations.find(r => r.id === state.relation));
    container.replaceChildren(); $("selected-kind").textContent = "relation / 保存された関係";
    if (!relation) {container.append(el("p","指定した関係版は取得できません。","empty"));return;}
    container.append(badge(rev ? `過去版 / commit ${rev.commit_revision}` : "現在の関係"),el("h1",relation.relation_kind),
      el("p",JSON.stringify(relation,null,2),"metadata"));
    for (const [label,id] of [["起点",relation.from_node_id],["終点",relation.to_node_id]]) {
      container.append(referenceButton(id,()=>select(id),null,{prefix:`${label}: `}));
    }
    for (const id of rev?.provenance_ids || []) {
      const p = data.provenance.find(p => p.id === id);
      if (p) container.append(el("p",`理由: ${p.reason}\n実行者: ${p.actor}\n指示の参照: ${p.decision?.authority_ref || "未登録"}`,"note"));
    }
    return;
  }
  if (!state.selected) {
    container.replaceChildren(el("p", "合意を選ぶと、本文・理由・履歴を読めます。", "empty"));
    $("selected-kind").textContent = "—";
    return;
  }
  const current = nodeById(state.selected);
  const revision = state.version ? data.revisions.find(r => r.revision_id === state.version && r.target_id === state.selected && r.target_type === "node") : null;
  const node = revision ? revision.snapshot : current;
  container.replaceChildren();
  if (state.version && !revision) {
    container.append(el("p", "指定した過去版は取得できません。", "empty"));
    return;
  }
  if (!node) {container.append(el("p", "対象は未登録です。", "empty")); return;}
  $("selected-kind").textContent = `${node.kind} / ${labels[node.lifecycle]}`;
  container.append(badge(revision ? `過去版 / commit ${revision.commit_revision}` : "現在の記録"), el("span",number(node.id),"object-number detail-number"),
    el("h1", node.title), el("div", `内部ID: ${node.id}\n版ID (revision_id): ${node.revision_id}`, "metadata"));
  if (revision) container.append(button("現在版へ戻る", () => select(node.id)));
  if (node.kind === "scope" && !revision) container.append(exportButton(node.id));
  container.append(el("p", node.body, "body-text"));
  if (state.latestDiff?.id === node.id && !revision) appendDiff(container, state.latestDiff.before, state.latestDiff.after);
  container.append(el("h2", "SCOPE / 所属"));
  const scopes=el("p",null,"note object-references"),scopeIds=data.scope_ids[node.id] || [];
  if (revision || !scopeIds.length) scopes.textContent=revision ? "過去版には現在の所属を混ぜません。" : "未分類";
  else scopeIds.forEach((id,i)=>appendReference(scopes,id,{prefix:i ? " / " : ""}));
  container.append(scopes);
  if (node.locator) container.append(el("p", `所在: ${node.locator}`, "metadata"));
  if (node.content_hash) container.append(el("p", node.content_hash, "metadata"));
  if (node.evidence) {
    const e = node.evidence;
    container.append(el("h2", "EVIDENCE / 一回の観測記録"), el("p", `結果: ${e.outcome}\n方法: ${e.method}\n観測時刻: ${e.observed_at}\n実行者: ${e.actor}`, "note"));
    for (const ref of e.subject_refs) container.append(referenceButton(ref.id, () => select(ref.id, ref.revision_id), "relation-card",{suffix:` / ${ref.revision_id}`}));
    container.append(el("p", "記録した対象と方法の範囲です。現在の実ファイルの一致は別途観測が必要です。", "note muted"));
  }
  if (!revision) {
    container.append(el("h2", "RELATIONS / 記録された関係"));
    const relations = data.relations.filter(r => [r.from_node_id, r.to_node_id].includes(node.id));
    const focus = el("details", null, "focus-map"); focus.append(el("summary", "関係にフォーカス / 選択した記録の近傍"), appendReference(el("p"),node.id));
    for (const r of relations) {
      const outgoing = r.from_node_id === node.id, other = outgoing ? r.to_node_id : r.from_node_id;
      const edge = el("div",null,"focus-edge"), graphic = document.createElementNS("http://www.w3.org/2000/svg","svg");
      graphic.setAttribute("viewBox","0 0 25 44"); graphic.setAttribute("aria-hidden","true");
      const path = document.createElementNS(graphic.namespaceURI,"path");
      path.setAttribute("d", outgoing ? "M1 0 V22 H23 M18 18 L23 22 L18 26" : "M23 22 H1 V0 M1 0 L5 5 M1 0 L-3 5");
      path.setAttribute("fill","none"); path.setAttribute("stroke","currentColor");
      if (!M.active(r)) path.setAttribute("stroke-dasharray","3 3"); graphic.append(path);
      const label = el("div"); label.append(el("span",`${outgoing ? "選択元 → 相手" : "相手 → 選択元"} / ${r.relation_kind}`),
        el("span",`${labels[r.confirmation]} / ${labels[r.lifecycle]}`),referenceButton(other,()=>select(other)),
        button("関係の原文・根拠版",()=>selectRelation(r.id)));
      edge.append(graphic,label); focus.append(edge);
    }
    if (!relations.length) focus.append(el("p","関係は未登録です。","note"));
    container.append(focus);
    if (!relations.length) container.append(el("p", "関係は未登録です。", "note muted"));
    for (const r of relations) {
      const other = r.from_node_id === node.id ? r.to_node_id : r.from_node_id;
      const card = el("div", null, `relation-card ${r.confirmation === "candidate" ? "candidate" : ""}`);
      card.append(badge(labels[r.confirmation]), badge(labels[r.lifecycle]), el("div", `${r.from_node_id === node.id ? "→" : "←"} ${r.relation_kind}`),
        referenceButton(other, () => select(other)), el("span", `関係ID: ${r.id}\n根拠版: ${labels[data.basis_status[r.id]]}`, "metadata"));
      if (r.qualifier) card.append(el("p", r.qualifier, "note"));
      const details = el("details"); details.append(el("summary", "根拠版・関係の履歴"));
      for (const rev of data.revisions.filter(v => v.target_type === "relation" && v.target_id === r.id).reverse()) {
        details.append(el("p", `commit ${rev.commit_revision} / ${rev.revision_id}\n${JSON.stringify(rev.snapshot, null, 2)}`, "metadata"));
      }
      card.append(details); container.append(card);
    }
    const diagnostics = data.diagnostics[node.id] || [];
    if (diagnostics.length) container.append(el("p", diagnostics.map(d => d.message).join("\n"), "note muted"));
    if (node.kind === "agreement" && !relations.some(r => r.relation_kind === "verified_by" && M.active(r))) container.append(el("p", "検証関係は未登録です。採択済みであることだけでは、実装の検証を意味しません。", "note muted"));
  }
  container.append(el("h2", "HISTORY / 原文・判断の履歴"));
  const history = data.revisions.filter(r => r.target_type === "node" && r.target_id === node.id).reverse();
  for (let i = 0; i < history.length; i++) {
    const rev = history[i], entry = el("details", null, "history-entry");
    entry.append(el("summary", `commit ${rev.commit_revision} · ${rev.snapshot.updated_at} · ${rev.revision_id}`), el("p", rev.snapshot.body, "note"));
    appendDiff(entry, history[i + 1]?.snapshot, rev.snapshot);
    for (const id of rev.provenance_ids) {
      const p = data.provenance.find(v => v.id === id);
      if (p) entry.append(el("p", `理由: ${p.reason}\n実行者: ${p.actor}\n${p.decision ? `指示の参照: ${p.decision.authority_ref}\n` : ""}出所: ${(p.source_refs || []).join(" / ") || "未登録"}`, "note"));
    }
    entry.append(button("この過去版を読む", () => select(node.id, rev.revision_id))); container.append(entry);
  }
}
function renderChanges() {
  const container = $("changes"); container.replaceChildren();
  const events = state.data.events.filter(e => e.confirmed).slice(-4).reverse();
  if (!events.length) container.append(el("p", "確定した変更はまだありません。"));
  for (const event of events) {
    const changes = event.changes.filter(c => c.type === "node" && c.after.kind === "agreement");
    const summary=el("span",null,"change-summary");
    changes.slice(0,2).forEach((c,i)=>appendReference(summary,c.id,{prefix:`${i ? " / " : ""}${changeLabel(c)} `,title:c.after.title}));
    if (!changes.length) summary.textContent="関係・文脈の変更";
    if (changes.length > 2) summary.append(document.createTextNode(` / ほか${changes.length-2}件`));
    const item = button(null, () => showEvent(event), "change-button");
    item.title = `${event.changes.length}件の変更 / ${event.reason}`;
    item.append(el("strong", `COMMIT ${event.graph_revision} / ${event.changes.length}件の変更`), summary); container.append(item);
  }
}
function display(next, change) {
    state.data = next; state.observed = new Date(); state.disconnected = false;
    $("project-name").textContent=next.meta.project_name; $("project-name").title=next.meta.project_name;
    document.title=`${next.meta.project_name} / LATIS`;
    document.body.classList.remove("disconnected"); $("mode").textContent = state.mode;
    $("revision").textContent = `rev ${String(next.meta.graph_revision).padStart(5, "0")} / ${next.meta.snapshot_id}`;
    $("observed").textContent = state.mode === "REPLAY" ? "過去の実記録 / ライブではありません" : `取得 ${state.observed.toLocaleTimeString("ja-JP")}`;
    $("database").textContent = `${next.meta.database_id} / READ ONLY`;
    if (change.type !== "SAME") {
      if (["RESET", "RECONNECTED", "LOAD", "REPLAY"].includes(change.type)) {
        state.highlights.clear(); state.latestDiff = null; state.version = null; state.event = null; state.relation = null;
      }
      if (change.type === "RESET") {state.collapsed.clear(); state.selected = null; state.rows.clear(); $("rows").replaceChildren();}
      for (const event of change.events) for (const c of event.changes) {
        if (c.type === "node" && c.after.kind === "agreement") {
          if (state.mode === "LIVE") {state.highlights.set(c.id, changeLabel(c)); state.highlightTimes.set(c.id, performance.now());}
          state.selected = c.id; state.version = null; state.latestDiff = c; state.event = null; state.relation = null;
          if (c.after.lifecycle === "accepted") {
            for (const group of M.groups(next)) if ((next.scope_ids[c.id] || []).includes(group.id)) {
              state.collapsed.delete(group.id);
              group.ancestors.forEach(id => state.collapsed.delete(id));
            }
          }
        }
      }
      if (!state.selected || !nodeById(state.selected)) state.selected = firstAgreement(next);
      $("sync-status").textContent = `${change.type}${change.events.length > 1 ? ` / 複数件更新（${change.events.length} commits）` : ""} · ${state.mode === "REPLAY" ? "過去の実記録" : "正本と同期"} / 展示用の架空設定`;
      renderRows(); renderDetails(); renderChanges();
      if (change.events.some(e => e.changes.some(c => c.type === "node" && c.after.kind === "agreement"))) {
        [...$("rows").querySelectorAll(".data-row")].find(row => row.dataset.nodeId === state.selected)?.scrollIntoView({block:"nearest"});
      }
      if (state.highlights.size) {
        const marked = new Map(state.highlightTimes);
        setTimeout(() => {
          for (const [id, time] of marked) if (state.highlightTimes.get(id) === time) {state.highlights.delete(id);state.highlightTimes.delete(id);}
          renderRows();
        }, 3000);
      }
    }
}
async function poll() {
  const generation = state.generation;
  try {
    if (state.mode !== "LIVE") return;
    const response = await fetch("/api/graph", {cache: "no-store", signal: AbortSignal.timeout(2500)});
    const result = await response.json();
    if (generation !== state.generation || state.mode !== "LIVE") return;
    if (!response.ok || !result.ok) throw new Error(result.error?.message || "DBの読取に失敗しました。");
    const next = M.validate(result.data), change = M.transition(state.data, next, state.disconnected);
    display(next,change);
  } catch (error) {
    if (generation !== state.generation || state.mode !== "LIVE") return;
    state.disconnected = true; document.body.classList.add("disconnected"); $("mode").textContent = "DISCONNECTED";
    $("sync-status").textContent = `${error.message} 最後の正常な表示を保持しています。`;
  } finally {setTimeout(poll, 750);}
}
function stopReplay() {if (state.replay) state.replay.playing = false; $("replay-toggle").textContent = "再生";}
async function seekReplay(revision) {
  if (state.mode !== "REPLAY") return;
  const replay = state.replay, generation = ++state.generation;
  const target = Math.max(0,Math.min(replay.max,revision));
  $("replay-position").textContent = `読込中: rev ${target}`;
  try {
    const response = await fetch(`/api/replay/${target}`,{cache:"no-store",signal:AbortSignal.timeout(2500)}), result = await response.json();
    if (generation !== state.generation || state.mode !== "REPLAY") return;
    if (!response.ok || !result.ok) throw new Error(result.error?.message || "過去版を取得できません。");
    const next = M.validate(result.data), anchor = replay.commits.find(c => c.graph_revision === target);
    if (next.meta.database_id !== replay.database || next.meta.snapshot_id !== anchor?.snapshot_id) throw new Error("DBまたは履歴が切り替わりました。LIVEへ戻って再開してください。");
    replay.position = target; $("replay-range").value = target; $("replay-position").textContent = `rev ${target} / ${replay.max}`;
    display(next,{type:"REPLAY",events:next.events.filter(e=>e.graph_revision === target && e.confirmed)});
    if (replay.playing && target < replay.max) setTimeout(()=>{
      if (state.mode === "REPLAY" && state.generation === generation && replay.playing) seekReplay(target+1);
    },2500);
    else if (target === replay.max) stopReplay();
  } catch (error) {
    if (generation !== state.generation || state.mode !== "REPLAY") return;
    stopReplay(); $("mode").textContent = "REPLAY / 停止"; $("sync-status").textContent = error.message + " 最後に取得できた実記録を保持しています。";
  }
}
function startReplay() {
  if (!state.data || state.mode !== "LIVE") return;
  state.replay = {database:state.data.meta.database_id,max:state.data.meta.graph_revision,commits:state.data.commits,position:0,playing:false};
  state.mode = "REPLAY"; state.generation++; document.body.classList.add("replay");
  $("mode").textContent = "REPLAY"; $("observed").textContent = "過去の実記録 / ライブではありません";
  $("replay-controls").hidden = false; $("start-replay").hidden = true; $("replay-range").max = state.replay.max;
  seekReplay(0);
}
$("start-replay").addEventListener("click",startReplay);
$("return-live").addEventListener("click",()=>{
  stopReplay(); state.mode = "LIVE"; state.generation++; state.disconnected = true;
  document.body.classList.remove("replay"); $("replay-controls").hidden = true; $("start-replay").hidden = false;
  $("mode").textContent = "CONNECTING"; $("observed").textContent = "正本へ再接続中";
});
$("replay-first").addEventListener("click",()=>{stopReplay();seekReplay(0);});
$("replay-prev").addEventListener("click",()=>{stopReplay();seekReplay(state.replay.position-1);});
$("replay-next").addEventListener("click",()=>{stopReplay();seekReplay(state.replay.position+1);});
$("replay-range").addEventListener("input",()=>{stopReplay();seekReplay(Number($("replay-range").value));});
$("replay-toggle").addEventListener("click",()=>{
  if (state.replay.playing) {stopReplay();return;}
  state.replay.playing = true; $("replay-toggle").textContent = "停止";
  seekReplay(state.replay.position === state.replay.max ? 0 : state.replay.position+1);
});
$("filter").addEventListener("input", renderRows);
$("all-states").addEventListener("change", renderRows);
$("reduce-motion").addEventListener("change", () => document.body.classList.toggle("motion", !$("reduce-motion").checked));
fetch("/api/recording",{cache:"no-store"}).then(r=>r.json()).then(r=>{
  $("recorded-link").hidden = !(r.ok && r.data?.clips?.length);
}).catch(()=>{});
poll();
