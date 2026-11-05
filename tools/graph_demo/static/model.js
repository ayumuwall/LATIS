/* 正本の明示関係と実履歴だけを扱う、展示画面の表示モデル。 */
((root) => {
  "use strict";
  const active = r => r.lifecycle === "active" && r.confirmation === "confirmed";
  const prefixes = {agreement:"A",proposal:"P",intent:"I",rationale:"R",question:"Q",scope:"S",artifact:"AR",task:"T"};
  const byId = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  function validate(data) {
    if (!data || !data.meta || !Number.isSafeInteger(data.meta.graph_revision) ||
        !data.meta.database_id || !data.meta.snapshot_id || typeof data.meta.project_name !== "string" || !data.meta.project_name.trim() ||
        !["nodes", "relations", "commits", "events", "revisions", "provenance"].every(k => Array.isArray(data[k]))) {
      throw new Error("表示応答の形式が不正です。");
    }
    const object = value => value && typeof value === "object" && !Array.isArray(value);
    const string = value => typeof value === "string" && value.length > 0;
    const node = n => object(n) && [n.id,n.revision_id,n.kind,n.lifecycle,n.title,n.created_at,n.updated_at].every(string) && typeof n.body === "string" &&
      (!n.evidence || object(n.evidence) && Array.isArray(n.evidence.subject_refs) && n.evidence.subject_refs.every(r=>object(r)&&string(r.id)&&string(r.revision_id)));
    const relation = r => object(r) && [r.id,r.revision_id,r.relation_kind,r.confirmation,r.lifecycle,r.from_node_id,r.to_node_id].every(string);
    const nodes = new Map(data.nodes.map(n => [n?.id, n]));
    if (data.meta.graph_revision < 0 || nodes.size !== data.nodes.length ||
        !object(data.scope_ids) || !object(data.basis_status) || !object(data.diagnostics) || !object(data.selection) ||
        !object(data.display_numbers) || Object.keys(data.display_numbers).length !== nodes.size ||
        new Set(Object.values(data.display_numbers)).size !== nodes.size ||
        !data.nodes.every(n => node(n) &&
          prefixes[n.kind] && new RegExp(`^${prefixes[n.kind]}-[1-9][0-9]*$`).test(data.display_numbers[n.id]) &&
          Array.isArray(data.scope_ids[n.id]) && data.scope_ids[n.id].every(id => nodes.get(id)?.kind === "scope")) ||
        !data.relations.every(r => relation(r) && nodes.has(r.from_node_id) && nodes.has(r.to_node_id) &&
          (r.relation_kind !== "contains" || [r.from_node_id,r.to_node_id].every(id=>nodes.get(id).kind === "scope"))) ||
        !data.events.every(e => object(e) && Number.isSafeInteger(e.graph_revision) && typeof e.confirmed === "boolean" &&
          string(e.created_at) && string(e.reason) && Array.isArray(e.changes) && e.changes.every(c => object(c) && ["node","relation"].includes(c.type) && string(c.id) &&
            (c.type === "node" ? node(c.after) && (!c.before || node(c.before)) : relation(c.after) && (!c.before || relation(c.before))))) ||
        !data.revisions.every(r=>object(r)&&string(r.target_id)&&string(r.revision_id)&&Array.isArray(r.provenance_ids)&&
          (r.target_type === "node" ? node(r.snapshot) : r.target_type === "relation" && relation(r.snapshot))) ||
        !data.provenance.every(p=>object(p)&&string(p.id)&&string(p.reason)&&(!p.source_refs || Array.isArray(p.source_refs))) ||
        !data.nodes.every(n=>Array.isArray(data.diagnostics[n.id])&&data.diagnostics[n.id].every(d=>object(d)&&string(d.message))) ||
        (data.scope_order !== undefined && (!Array.isArray(data.scope_order) || !data.scope_order.every(id=>nodes.get(id)?.kind === "scope"))) ||
        !data.commits.every(c => object(c) && Number.isSafeInteger(c.graph_revision) && string(c.snapshot_id)) ||
        !data.commits.some(c => c.graph_revision === data.meta.graph_revision && c.snapshot_id === data.meta.snapshot_id)) {
      throw new Error("表示応答の内容が不正です。最後の正常な表示を保持します。");
    }
    return data;
  }
  function transition(previous, next, recovering = false) {
    validate(next);
    if (!previous) return {type: "LOAD", events: []};
    const a = previous.meta, b = next.meta;
    const anchor = next.commits.find(c => c.graph_revision === a.graph_revision);
    if (a.database_id !== b.database_id || b.graph_revision < a.graph_revision ||
        !anchor || anchor.snapshot_id !== a.snapshot_id) return {type: "RESET", events: []};
    if (recovering) return {type: "RECONNECTED", events: []};
    if (a.graph_revision === b.graph_revision) return {type: "SAME", events: []};
    const commits = next.commits.filter(c => c.graph_revision > a.graph_revision);
    if (commits.length !== b.graph_revision - a.graph_revision) return {type: "RESET", events: []};
    return {type: "UPDATE", events: next.events.filter(e => e.graph_revision > a.graph_revision && e.confirmed && e.operation === "apply")};
  }
  function groups(data) {
    const order = new Map((data.scope_order || []).map((id,index) => [id,index]));
    const compare = (a,b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity) || byId(a,b);
    const scopes = data.nodes.filter(n => n.kind === "scope").sort(compare);
    const children = new Map(scopes.map(n => [n.id, []]));
    const parents = new Set();
    data.relations.filter(r => active(r) && r.relation_kind === "contains").forEach(r => {
      children.get(r.from_node_id)?.push(r.to_node_id);
      parents.add(r.to_node_id);
    });
    const nodes = new Map(scopes.map(n => [n.id, n]));
    const result = [], visited = new Set();
    function visit(id, depth, ancestors) {
      if (ancestors.has(id)) return;
      const reference = visited.has(id);
      result.push({id, node: nodes.get(id), depth, ancestors: [...ancestors], reference});
      if (reference) return;
      visited.add(id);
      const next = new Set([...ancestors, id]);
      (children.get(id) || []).sort((a,b) => compare(nodes.get(a),nodes.get(b))).forEach(child => visit(child, depth + 1, next));
    }
    scopes.filter(n => !parents.has(n.id)).forEach(n => visit(n.id, 0, new Set()));
    scopes.filter(n => !visited.has(n.id)).forEach(n => visit(n.id, 0, new Set()));
    result.push({id: "", node: {title: "未分類", lifecycle: "表示用分類"}, depth: 0, ancestors: []});
    return result;
  }
  function contexts(data, id) {
    const nodes = new Map(data.nodes.map(n => [n.id, n]));
    return data.relations.filter(r => r.lifecycle === "active" && [r.from_node_id, r.to_node_id].includes(id))
      .map(r => ({relation: r, node: nodes.get(r.from_node_id === id ? r.to_node_id : r.from_node_id)}))
      .filter(item => item.node && ["rationale", "intent", "question", "artifact"].includes(item.node.kind));
  }
  function textDiff(before, after) {
    const a = Array.from(before || ""), b = Array.from(after || "");
    let start = 0, end = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) start++;
    while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end++;
    return {prefix: a.slice(0, start).join(""), removed: a.slice(start, a.length - end).join(""),
      added: b.slice(start, b.length - end).join(""), suffix: end ? b.slice(b.length - end).join("") : ""};
  }
  function displayNumber(data,id) {return data.display_numbers[id] || id;}
  function matchesQuery(data,node,terms) {
    const number = displayNumber(data,node.id).toLocaleLowerCase();
    const text = `${number} ${node.title} ${node.body}`.normalize("NFKC").toLocaleLowerCase();
    return terms.every(term => /^(?:a|p|i|r|q|s|ar|t)-[1-9][0-9]*$/.test(term) ? number === term : text.includes(term));
  }
  const api = {active, validate, transition, groups, contexts, textDiff, displayNumber, matchesQuery};
  if (typeof module !== "undefined") module.exports = api;
  else root.ExplorerModel = api;
})(globalThis);
