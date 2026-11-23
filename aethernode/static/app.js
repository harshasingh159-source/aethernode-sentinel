"use strict";

const POLL_MS = 4000;
const $ = (sel) => document.querySelector(sel);

const state = {
  devices: [], events: [], status: null, router: null,
  view: "review", query: "", editing: null,
  lastEventId: null, fresh: new Set(),
};

// ---------------------------------------------------------------- api

async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

async function refresh() {
  try {
    const [status, devices, events, router] = await Promise.all([
      api("/status"), api("/devices"), api("/events?limit=60"), api("/router").catch(() => null)]);
    handleNewEvents(events);
    Object.assign(state, { status, devices, events, router });
    banner(status.scanner?.error ? `Scanner problem: ${status.scanner.error}` : "");
    render();
  } catch (e) {
    banner("Can't reach the AetherNode server. Is it still running?");
  }
}

function handleNewEvents(events) {
  const newestId = events[0]?.id ?? 0;
  if (state.lastEventId !== null) {
    for (const ev of events) {
      if (ev.id <= state.lastEventId) break;
      if (ev.kind === "joined") {
        state.fresh.add(ev.mac);
        setTimeout(() => state.fresh.delete(ev.mac), 3000);
        notify("New device on your network", `${ev.label || "Unknown device"} — ${ev.detail || ev.mac}`);
      }
    }
  }
  state.lastEventId = newestId;
}

async function act(fn) {
  try { await fn(); } catch (e) { banner(`Action failed: ${e.message}`); }
  await refresh();
}

// ---------------------------------------------------------------- helpers

function ago(ts) {
  if (!ts) return "never";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function label(d) {
  return d.name || d.hostname || d.vendor || (d.private_mac ? "Phone/laptop with private address" : "Unknown device");
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter((c) => c !== null && c !== undefined && c !== false));
  return node;
}

function banner(msg) {
  const b = $("#banner");
  b.textContent = msg;
  b.hidden = !msg;
}

function notify(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}

const VIEWS = {
  review: (d) => !d.trusted,
  online: (d) => d.online,
  all: () => true,
  router: () => false,
};

// ---------------------------------------------------------------- render

function render() {
  const { status } = state;
  const c = status.counts;
  $("#c-online").textContent = c.online;
  $("#c-untrusted").textContent = c.untrusted;
  $("#c-trusted").textContent = c.trusted;
  $("#c-total").textContent = c.total;
  $(".tile.warn").classList.toggle("hot", c.untrusted_online > 0);
  document.title = c.untrusted_online ? `(${c.untrusted_online}) AetherNode` : "AetherNode";

  renderScanStatus(status.scanner);
  for (const tab of document.querySelectorAll(".tab")) {
    const v = tab.dataset.view;
    const n = v === "router" ? (state.router?.configured ? state.router.devices.filter((d) => d.active).length : "")
      : state.devices.filter(VIEWS[v]).length;
    tab.hidden = v === "router" && !state.router;
    tab.replaceChildren(v === "review" ? "Need review" : v[0].toUpperCase() + v.slice(1),
      el("span", { className: "n", textContent: n }));
    tab.classList.toggle("active", tab.dataset.view === state.view);
  }
  const routerView = state.view === "router";
  $("#router-view").hidden = !routerView;
  $("#devices").hidden = routerView;
  $("#search").hidden = routerView;
  if (routerView) { $("#empty").hidden = true; renderRouter(); }
  else if (!state.editing) renderDevices();
  renderEvents();
}

function renderScanStatus(s) {
  const line = $("#scan-status");
  document.body.classList.toggle("scanning", !!s?.scanning);
  $("#scan-btn").disabled = !s || s.scanning;
  if (!s) { line.textContent = "Scanner disabled (dashboard only)"; return; }
  if (s.scanning) { line.textContent = `Scanning ${s.subnet || "network"}…`; return; }
  const parts = [];
  if (s.subnet) parts.push(s.subnet);
  parts.push(s.last_scan ? `last scan ${ago(s.last_scan)} · ${s.last_scan_found} present` : "waiting for first scan");
  if (s.next_scan) parts.push(`next in ${Math.max(0, Math.round(s.next_scan - Date.now() / 1000))}s`);
  parts.push(s.live === "on" ? "live alerts on" : "sweep mode");
  line.textContent = parts.join(" · ");
  line.title = s.live !== "on" ? `Live sniffing: ${s.live}` : "";
}

function renderRouter() {
  const r = state.router;
  if (!r) return;
  const form = $("#router-form");
  const needsLogin = !r.configured || r.status === "auth_failed";
  $("#router-connected").hidden = !r.configured;
  if (form.hidden && needsLogin && !form.url.value) form.url.value = r.url || r.suggested_url || "";
  if (form.hidden && needsLogin && !form.username.value && r.username) form.username.value = r.username;
  form.hidden = !needsLogin;
  if (!r.configured) return;

  const parts = [`${r.kind} router at ${r.url}`, `signed in as ${r.username}`];
  parts.push(r.last_poll ? `updated ${ago(r.last_poll)}` : "connecting…");
  if (!r.remembered) parts.push("not remembered after restart");
  $("#router-summary").textContent = parts.join(" · ");
  const err = $("#router-error");
  err.hidden = !r.error;
  err.textContent = r.status === "auth_failed" ? `Router rejected the login: ${r.error} Sign in again below.` : `Last refresh failed: ${r.error || ""}`;

  const active = r.devices.filter((d) => d.active).length;
  const list = r.devices.map((d) => {
    const badges = [];
    if (d.trusted) badges.push(el("span", { className: "badge ok", textContent: "Trusted" }));
    else if (d.known) badges.push(el("span", { className: "badge warn", textContent: "Needs review" }));
    else badges.push(el("span", { className: "badge", textContent: "Not seen by scanner" }));
    if (d.connection) badges.push(el("span", { className: "badge", textContent: d.connection }));
    const meta = [d.ip || "no IP", el("span", { className: "mono", textContent: d.mac })];
    if (d.label && d.label !== d.name) meta.push(`you call it "${d.label}"`);
    return el("li", { className: `device${d.known && !d.trusted ? " untrusted" : ""}` },
      el("span", { className: `dot${d.active ? " on" : ""}`, title: d.active ? "Connected" : "Not connected" }),
      el("div", { className: "info" },
        el("div", { className: "title" },
          el("span", { className: `name${d.name ? "" : " placeholder"}`, textContent: d.name || "No name reported" }),
          el("span", { className: "badges" }, ...badges)),
        el("div", { className: "meta" }, ...meta.flatMap((m, i) => (i ? [" · ", m] : [m])))),
      el("div", { className: "seen", textContent: d.active ? "connected" : "not connected" }));
  });
  $("#router-devices").replaceChildren(...(list.length ? list
    : [el("li", { className: "empty", textContent: r.last_poll ? "The router reported no devices." : "Reading the router's device list…" })]));
  $("#router-summary").textContent += ` · ${active} connected / ${r.devices.length} known`;
}

function renderDevices() {
  const q = state.query.trim().toLowerCase();
  const list = state.devices
    .filter(VIEWS[state.view])
    .filter((d) => !q || [d.name, d.hostname, d.vendor, d.ip, d.mac].some((v) => v && v.toLowerCase().includes(q)));

  const ul = $("#devices");
  ul.replaceChildren(...list.map(deviceRow));

  const empty = $("#empty");
  empty.hidden = list.length > 0;
  if (!list.length) {
    empty.textContent = q ? "No devices match your search."
      : state.view === "review" ? (state.devices.length ? "All clear — every device is trusted. ✓" : "No devices yet. The first scan takes about 10 seconds…")
      : state.view === "online" ? "No devices online right now." : "No devices yet.";
  }
}

function deviceRow(d) {
  const li = $("#device-tpl").content.firstElementChild.cloneNode(true);
  li.classList.toggle("untrusted", !d.trusted);
  li.classList.toggle("fresh", state.fresh.has(d.mac));
  li.querySelector(".dot").classList.toggle("on", d.online);
  li.querySelector(".dot").title = d.online ? "Online" : "Offline";

  const name = li.querySelector(".name");
  name.textContent = label(d);
  name.classList.toggle("placeholder", !d.name && !d.hostname);

  const badges = li.querySelector(".badges");
  if (d.is_self) badges.append(el("span", { className: "badge self", textContent: "This PC" }));
  if (!d.trusted && Date.now() / 1000 - d.first_seen < 86400) badges.append(el("span", { className: "badge new", textContent: "New" }));
  if (d.private_mac) badges.append(el("span", { className: "badge", textContent: "Private MAC", title: "This device hides its real hardware address" }));

  const meta = [d.ip, el("span", { className: "mono", textContent: d.mac })];
  if (d.name && d.hostname) meta.push(d.hostname);
  if (d.vendor && label(d) !== d.vendor) meta.push(d.vendor);
  li.querySelector(".meta").append(...meta.flatMap((m, i) => (i ? [" · ", m] : [m])));

  li.querySelector(".seen").textContent = d.online ? "online now" : `seen ${ago(d.last_seen)}`;
  li.querySelector(".seen").title = `First seen ${new Date(d.first_seen * 1000).toLocaleString()}`;

  const trust = li.querySelector(".trust");
  trust.textContent = d.trusted ? "Untrust" : "Trust";
  trust.classList.toggle("ghost", d.trusted);
  trust.onclick = () => act(() => api(`/devices/${encodeURIComponent(d.mac)}`, { method: "PATCH", body: { trusted: !d.trusted } }));

  li.querySelector(".rename").onclick = () => startRename(li, d);
  li.querySelector(".forget").onclick = () => {
    if (confirm(`Forget ${label(d)}?\nIt will reappear as a new device if it's seen again.`)) {
      act(() => api(`/devices/${encodeURIComponent(d.mac)}`, { method: "DELETE" }));
    }
  };
  return li;
}

function startRename(li, d) {
  state.editing = d.mac;
  const input = el("input", { className: "rename-input", value: d.name || d.hostname || "", maxLength: 64, placeholder: "e.g. Mom's phone" });
  const finish = () => { state.editing = null; renderDevices(); };
  const form = el("form", { className: "rename-form" }, input,
    el("button", { className: "btn small", type: "submit", textContent: "Save" }),
    el("button", { className: "btn small ghost", type: "button", textContent: "Cancel", onclick: finish }));
  form.onsubmit = (e) => {
    e.preventDefault();
    state.editing = null;
    // naming a device is the same as vouching for it
    act(() => api(`/devices/${encodeURIComponent(d.mac)}`, { method: "PATCH", body: { name: input.value, trusted: input.value.trim() ? true : d.trusted } }));
  };
  input.onkeydown = (e) => { if (e.key === "Escape") finish(); };
  li.querySelector(".title").replaceChildren(form);
  input.focus();
  input.select();
}

const EVENT_TEXT = {
  joined: ["🆕", "New device joined"],
  online: ["🟢", "came online"],
  offline: ["⚪", "went offline"],
  ip_changed: ["🔁", "changed IP"],
  trusted: ["✅", "marked trusted"],
  untrusted: ["⚠️", "marked untrusted"],
  renamed: ["✏️", "renamed"],
  forgotten: ["🗑️", "forgotten"],
};

function renderEvents() {
  const ol = $("#events");
  if (!state.events.length) {
    ol.replaceChildren(el("li", { className: "empty", textContent: "Nothing yet." }));
    return;
  }
  ol.replaceChildren(...state.events.map((ev) => {
    const [ico, verb] = EVENT_TEXT[ev.kind] || ["•", ev.kind];
    const who = ev.label || ev.mac;
    const text = ev.kind === "joined" ? [el("span", { className: "what", textContent: verb }), `: ${who}`]
      : [`${who} ${verb}`];
    const extra = ev.detail && ev.kind !== "online" ? ` (${ev.detail})` : "";
    return el("li", { className: ev.kind },
      el("span", { className: "ico", textContent: ico }),
      el("div", {}, ...text, extra, el("div", { className: "when", textContent: ago(ev.ts), title: new Date(ev.ts * 1000).toLocaleString() })));
  }));
}

// ---------------------------------------------------------------- wiring

for (const tab of document.querySelectorAll(".tab")) {
  tab.onclick = () => { state.view = tab.dataset.view; state.editing = null; render(); };
}
$("#search").oninput = (e) => { state.query = e.target.value; renderDevices(); };
$("#scan-btn").onclick = () => act(() => api("/scan", { method: "POST" }));

const notifyBtn = $("#notify-btn");
if ("Notification" in window && Notification.permission === "default") {
  notifyBtn.hidden = false;
  notifyBtn.onclick = () => Notification.requestPermission().then(() => { notifyBtn.hidden = true; });
}

const routerForm = $("#router-form");
routerForm.onsubmit = async (e) => {
  e.preventDefault();
  const btn = routerForm.querySelector("button[type=submit]");
  const errEl = $("#router-form-error");
  btn.disabled = true; btn.textContent = "Signing in…"; errEl.hidden = true;
  try {
    await api("/router", { method: "PUT", body: {
      url: routerForm.url.value.trim(), username: routerForm.username.value.trim(),
      password: routerForm.password.value, remember: routerForm.remember.checked } });
    routerForm.password.value = "";
    routerForm.hidden = true;
  } catch (err) {
    errEl.textContent = err.message; errEl.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Connect";
  }
  await refresh();
};
$("#router-refresh").onclick = () => act(() => api("/router/refresh", { method: "POST" }));
$("#router-disconnect").onclick = () => {
  if (confirm("Disconnect the router? AetherNode will forget its login.")) act(() => api("/router", { method: "DELETE" }));
};

refresh();
setInterval(refresh, POLL_MS);
