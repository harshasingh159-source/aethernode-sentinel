"use strict";

const POLL_MS = 4000;
const $ = (sel) => document.querySelector(sel);

const state = {
  devices: [], events: [], status: null, router: null, routerPick: new Set(),
  // open on the tab named in the address, e.g. http://127.0.0.1:8000/#all
  view: ["review", "online", "all", "router"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "review",
  query: "", editing: null,
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

// In-page confirmation: browser confirm() popups can be blocked or auto-cancelled.
function askConfirm(title, body, okLabel = "OK") {
  const dlg = $("#confirm-dialog");
  $("#confirm-title").textContent = title;
  $("#confirm-body").textContent = body;
  $("#confirm-ok").textContent = okLabel;
  return new Promise((resolve) => {
    dlg.onclose = () => resolve(dlg.returnValue === "ok");
    dlg.returnValue = "";
    dlg.showModal();
    dlg.querySelector("button[value=cancel]").focus();  // safe default
  });
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
    const pick = d.active ? el("span") : el("input", {
      type: "checkbox", className: "pick", checked: state.routerPick.has(d.mac),
      title: "Select to remove from the router",
      onchange: (e) => { e.target.checked ? state.routerPick.add(d.mac) : state.routerPick.delete(d.mac); renderRouter(); },
    });
    return el("li", { className: `device router-row${d.known && !d.trusted ? " untrusted" : ""}` },
      pick,
      el("span", { className: `dot${d.active ? " on" : ""}`, title: d.active ? "Connected" : "Not connected" }),
      el("div", { className: "info" },
        el("div", { className: "title" },
          el("span", { className: `name${d.name ? "" : " placeholder"}`, textContent: d.name || "No name reported" }),
          el("span", { className: "badges" }, ...badges)),
        el("div", { className: "meta" }, ...meta.flatMap((m, i) => (i ? [" · ", m] : [m])))),
      el("div", { className: "seen", textContent: d.active ? "connected" : "not connected" }));
  });
  // drop selections for devices that vanished or reconnected
  const removable = new Set(r.devices.filter((d) => !d.active).map((d) => d.mac));
  for (const mac of [...state.routerPick]) if (!removable.has(mac)) state.routerPick.delete(mac);
  const n = state.routerPick.size;
  $("#router-selected").textContent = n ? `${n} selected` : `${removable.size} not connected`;
  $("#router-remove").disabled = n === 0;
  $("#router-remove").textContent = n ? `Remove ${n} from router` : "Remove from router";
  $("#router-select-all").checked = removable.size > 0 && n === removable.size;

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
  li.querySelector(".forget").onclick = async () => {
    if (await askConfirm(`Forget ${label(d)}?`, "It will reappear as a new device if it's seen again.", "Forget")) {
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
    // "renamed" detail is the new name, which is usually the label already: don't repeat it
    const extra = ev.detail && ev.kind !== "online" && ev.detail !== who ? ` (${ev.detail})` : "";
    return el("li", { className: ev.kind },
      el("span", { className: "ico", textContent: ico }),
      el("div", {}, ...text, extra, el("div", { className: "when", textContent: ago(ev.ts), title: new Date(ev.ts * 1000).toLocaleString() })));
  }));
}

// ---------------------------------------------------------------- wiring

for (const tab of document.querySelectorAll(".tab")) {
  tab.onclick = () => {
    state.view = tab.dataset.view; state.editing = null;
    history.replaceState(null, "", `#${state.view}`);
    render();
  };
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
$("#router-select-all").onchange = (e) => {
  state.routerPick = new Set(e.target.checked ? state.router.devices.filter((d) => !d.active).map((d) => d.mac) : []);
  renderRouter();
};
$("#router-remove").onclick = async () => {
  const picked = state.router.devices.filter((d) => state.routerPick.has(d.mac));
  if (!picked.length) return;
  const names = picked.slice(0, 15).map((d) => `• ${d.name || d.mac}`).join("\n") +
    (picked.length > 15 ? `\n…and ${picked.length - 15} more` : "");
  const ok = await askConfirm(`Remove ${picked.length} device(s) from the router's list?`,
    `${names}\n\nThis can't be undone. A removed device can still reconnect; it just shows up as new ` +
    "(and loses any name given on the router).", `Remove ${picked.length}`);
  if (!ok) return;
  const btn = $("#router-remove"), note = $("#router-remove-result");
  btn.disabled = true; btn.textContent = "Removing…"; note.hidden = true;
  try {
    const res = await api("/router/remove", { method: "POST", body: { macs: picked.map((d) => d.mac) } });
    const skipped = Object.entries(res.skipped);
    note.textContent = `Removed ${res.removed.length} device(s) from the router.` +
      (skipped.length ? ` Skipped ${skipped.length}: ` + skipped.map(([m, why]) => `${(picked.find((d) => d.mac === m) || {}).name || m} (${why})`).join(", ") : "");
    state.routerPick.clear();
  } catch (err) {
    note.textContent = `Remove failed: ${err.message}`;
  }
  note.hidden = false;
  await refresh();
};
$("#router-refresh").onclick = () => act(() => api("/router/refresh", { method: "POST" }));
$("#router-disconnect").onclick = async () => {
  if (await askConfirm("Disconnect the router?", "AetherNode will forget its login.", "Disconnect")) {
    act(() => api("/router", { method: "DELETE" }));
  }
};

// footer: version, and the bundled license notices (present in the Windows .exe build)
api("/status").then((st) => { $("#foot-version").textContent = `AetherNode ${st.version}`; }).catch(() => {});
fetch("THIRD_PARTY_NOTICES.txt", { method: "HEAD" }).then((r) => { $("#foot-notices").hidden = !r.ok; }).catch(() => {});

refresh();
setInterval(refresh, POLL_MS);
