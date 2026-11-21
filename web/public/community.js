// Community help requests on the flood map. Plain JS, no build step.
// Loaded after the map page's own script, so it can use its globals: map, L, esc, hexAt, select.
(function () {
  "use strict";
  const h = typeof esc === "function" ? esc
    : s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const CATS = {
    flooding: "Flooding / water coming in", sandbags: "Need sandbags", evacuation: "Need help evacuating",
    cleanup: "Cleanup after flooding", supplies: "Need supplies", other: "Other",
  };
  const STATUS = {open: "Open", help_on_the_way: "Help on the way", resolved: "Resolved"};
  const LOGIN = "/login?next=/flood_vulnerability_map.html";
  const SAFETY = '<p class="note"><i class="fa-solid fa-triangle-exclamation"></i> Demo only. In an emergency, call 911.</p>';
  const details = document.getElementById("details"), panel = document.getElementById("panel");
  const defaultDetails = details.innerHTML;

  let me = null, requests = [], picking = false, temp = null;
  // help pins get their own pane, above every other marker layer (the page's "sites" pane is 620)
  map.createPane("help"); map.getPane("help").style.zIndex = 640;
  const layer = L.layerGroup().addTo(map);

  // ------------------------------------------------------------ helpers
  async function api(method, url, body) {
    const opts = {method, credentials: "same-origin", headers: {}};
    if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || (r.status === 401 ? "Please log in first." : `Something went wrong (${r.status}).`));
    return data;
  }
  function show(html) {
    details.innerHTML = html;
    panel.scrollTop = details.offsetTop - 12;
  }
  function selectHexAt(ll) {
    if (typeof hexAt === "function" && typeof select === "function") select(hexAt(ll));
  }
  function ago(t) {
    const s = (Date.now() - new Date(t).getTime()) / 1000;
    if (!(s >= 60)) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    if (s < 86400) return Math.floor(s / 3600) + " h ago";
    return Math.floor(s / 86400) + " d ago";
  }
  function icon(kind) {
    return L.divIcon({className: "cm-marker", iconSize: [30, 30], iconAnchor: [15, 15],
      html: `<span class="cm-pin cm-${kind}"><i class="fa-solid fa-hand-holding-heart"></i></span>`});
  }
  function clearTemp() { if (temp) { map.removeLayer(temp); temp = null; } }

  // ------------------------------------------------------------ "Help requests" section: first thing in the panel
  const box = document.createElement("section");
  box.className = "cm-section";
  const sub = panel.querySelector(".sub");
  sub ? sub.after(box) : panel.prepend(box);
  box.addEventListener("change", e => { e.target.checked ? layer.addTo(map) : map.removeLayer(layer); });
  box.addEventListener("click", e => {
    const a = e.target.closest("[data-act]");
    if (!a) return;
    e.preventDefault();
    if (a.dataset.act === "logout") api("POST", "/api/logout").catch(() => {}).finally(() => location.reload());
    if (a.dataset.act === "ask") startPick();
    if (a.dataset.act === "open") {
      const r = requests.find(x => x.id === a.dataset.id);
      if (r) { map.flyTo([r.lat, r.lng], Math.max(map.getZoom(), 15), {duration: 0.6}); showCard(r); }
    }
  });
  function renderBox() {
    const open = requests.filter(r => r.status !== "resolved");
    const list = open.slice(0, 6).map(r => `<li><a href="#" data-act="open" data-id="${h(r.id)}">
        <span class="cm-chip cm-${h(r.status)}">${h(STATUS[r.status] || r.status)}</span>
        <b>${h(CATS[r.category] || r.category)}</b>
        <small>${h(r.requesterName)} · ${ago(r.createdAt)}${(r.volunteers || []).length ? ` · ${r.volunteers.length} helping` : ""}</small></a></li>`).join("");
    box.innerHTML = `<h2><i class="fa-solid fa-hand-holding-heart"></i> Help requests <span class="cm-count">${open.length} open</span></h2>
      <a href="#" class="cm-btn cm-primary cm-askbig" data-act="ask"><i class="fa-solid fa-hand-holding-heart"></i> Ask for help</a>
      <p class="note cm-who">${me ? `Signed in as <b>${h(me.name)}</b> · <a href="#" data-act="logout">Log out</a>`
        : `<a href="${LOGIN}">Log in / Sign up</a> to ask for help or volunteer.`}</p>
      ${open.length ? `<ul class="cm-list">${list}</ul>${open.length > 6 ? `<p class="note">+ ${open.length - 6} more on the map</p>` : ""}`
        : '<p class="note">No open requests right now.</p>'}
      <label class="note"><input type="checkbox" ${map.hasLayer(layer) ? "checked" : ""}> Show help pins on the map</label>`;
  }

  // ------------------------------------------------------------ "Ask for help" button + pick-a-spot mode
  const Ask = L.Control.extend({
    options: {position: "topleft"},
    onAdd() {
      const b = L.DomUtil.create("a", "leaflet-bar cm-ask");
      b.href = "#"; b.setAttribute("role", "button");
      b.innerHTML = '<i class="fa-solid fa-hand-holding-heart"></i> Ask for help';
      L.DomEvent.on(b, "click", e => { L.DomEvent.stop(e); startPick(); });
      return b;
    },
  });
  new Ask().addTo(map);
  const banner = L.DomUtil.create("div", "cm-banner", map.getContainer());
  banner.textContent = "Click where help is needed (Esc to cancel)";
  banner.hidden = true;

  function startPick() {
    if (!me) { location.href = LOGIN; return; }
    picking = true;
    map.getContainer().classList.add("cm-picking");
    banner.hidden = false;
  }
  function stopPick() {
    picking = false;
    map.getContainer().classList.remove("cm-picking");
    banner.hidden = true;
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape" && picking) stopPick(); });
  map.on("click", e => { if (picking) { stopPick(); showForm(e.latlng); } });

  // ------------------------------------------------------------ new request form
  function showForm(ll) {
    clearTemp();
    temp = L.marker(ll, {pane: "help", icon: icon("new"), interactive: false}).addTo(map);
    const hex = typeof hexAt === "function" ? hexAt(ll) : null;
    const risk = hex && hex.feature.properties.risk;
    show(`<h2>Ask for help</h2><div class="card cm-form">
      ${risk ? `<p class="note" style="margin-top:0">Flood risk here: <b>${h(risk)}</b></p>` : ""}
      <form>
        <label>What kind of help?
          <select name="category">${Object.entries(CATS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label>Details
          <textarea name="details" rows="4" maxlength="500" required placeholder="What's happening and what do you need?"></textarea></label>
        <label>Number of people
          <input name="people" type="number" min="1" max="50" value="1" required></label>
        <p class="cm-err" hidden></p>
        <div class="cm-actions">
          <button type="submit" class="cm-btn cm-primary">Submit</button>
          <button type="button" class="cm-btn" data-act="cancel">Cancel</button>
        </div>
      </form>${SAFETY}</div>`);
    const form = details.querySelector("form"), err = form.querySelector(".cm-err");
    form.querySelector("[data-act=cancel]").onclick = () => { clearTemp(); details.innerHTML = defaultDetails; };
    form.onsubmit = async e => {
      e.preventDefault();
      const f = new FormData(form), btn = form.querySelector("[type=submit]");
      btn.disabled = true; err.hidden = true;
      try {
        const {request} = await api("POST", "/api/requests", {
          lat: ll.lat, lng: ll.lng, category: f.get("category"),
          details: String(f.get("details")).trim(), people: Number(f.get("people")),
        });
        clearTemp();
        await load();
        showCard(requests.find(r => r.id === request.id) || request);
      } catch (ex) {
        err.textContent = ex.message; err.hidden = false; btn.disabled = false;
      }
    };
    form.querySelector("textarea").focus();
  }

  // ------------------------------------------------------------ request card
  function showCard(r, msg) {
    const vols = r.volunteers || [];
    const mine = me && me.id === r.requesterId;
    const helped = me && vols.some(v => v.userId === me.id);
    const done = r.status === "resolved";
    let btns = "";
    if (!me && !done) btns = `<a class="cm-btn cm-primary" href="${LOGIN}">Log in to volunteer</a>`;
    if (me && !mine && !helped && !done) btns += '<button class="cm-btn cm-primary" data-act="volunteer">I can help</button>';
    if (mine && !done) btns += '<button class="cm-btn" data-act="resolve">Mark resolved</button>';
    selectHexAt(L.latLng(r.lat, r.lng));
    show(`<h2>Help request</h2><div class="card">
      <div class="risk-head"><span class="cm-chip cm-${h(r.status)}">${h(STATUS[r.status] || r.status)}</span>
        <b style="font-size:16px">${h(CATS[r.category] || r.category)}</b></div>
      <p class="cm-details">${h(r.details)}</p>
      <p class="note"><i class="fa-solid fa-user-group"></i> ${h(r.people)} ${r.people == 1 ? "person" : "people"}</p>
      <p class="note">Asked by ${h(r.requesterName)} · ${ago(r.createdAt)}</p>
      <p class="note">Volunteers: ${vols.length ? vols.map(v => h(v.name)).join(", ") : "No one yet"}</p>
      ${btns ? `<div class="cm-actions">${btns}</div>` : ""}
      ${msg ? `<p class="cm-err">${h(msg)}</p>` : ""}${SAFETY}</div>`);
    details.querySelectorAll("button[data-act]").forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const {request} = await api("POST", `/api/requests/${encodeURIComponent(r.id)}/${b.dataset.act}`);
        showCard(request);
        load();
      } catch (ex) { showCard(r, ex.message); }
    });
  }

  // ------------------------------------------------------------ markers
  function draw() {
    layer.clearLayers();
    requests.filter(r => r.status !== "resolved").forEach(r => {
      L.marker([r.lat, r.lng], {pane: "help", icon: icon(r.status), riseOnHover: true, keyboard: false})
        .bindTooltip(`<b>${h(CATS[r.category] || r.category)}</b><br>${h(STATUS[r.status] || r.status)}`,
          {direction: "top", offset: [0, -12], className: "risk-tip"})
        .on("click", () => { if (!picking) showCard(r); })
        .addTo(layer);
    });
  }
  async function load() {
    try { requests = (await api("GET", "/api/requests")).requests || []; draw(); }
    catch (ex) { console.warn("Could not load help requests:", ex.message); }
    renderBox();
  }

  renderBox();
  api("GET", "/api/me").then(d => { me = d.user || null; }).catch(() => {}).finally(load);
  setInterval(load, 30000);
})();
