"use strict";
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const ICONS = {
    key: '<path d="M15.5 7.5a3.5 3.5 0 1 1-3.4 4.3L4 20v-3h3v-3h3l1.4-1.4"/><circle cx="15.5" cy="7.5" r=".6"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    phone: '<path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    gauge: '<path d="M12 14l4-4M4 18a9 9 0 1 1 16 0"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    building: '<path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M16 9h2a2 2 0 0 1 2 2v10M8 7h4M8 11h4M8 15h4M3 21h18"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    flask: '<path d="M9 3h6M10 3v6L4.5 18.5A1.8 1.8 0 0 0 6 21h12a1.8 1.8 0 0 0 1.5-2.5L14 9V3M7 15h10"/>',
    chev: '<path d="M9 5l7 7-7 7"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    warn: '<path d="M12 3 2 20h20L12 3zM12 10v4M12 17h.01"/>',
    x: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    upload: '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    play: '<path d="M7 4.5v15l12-7.5z"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    wand: '<path d="M15 4V2M15 10V8M11 6h2M17 6h2M4 20 14 10M18 13l1 1M12 2l1 1"/>',
    logout: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  };
  const icon = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

  // Setting metadata: hint, input mode and range for numeric fields.
  const FIELDS = {
    PLIVO_AUTH_ID: { icon: "key", color: "c-blue", hint: "Plivo Console → Overview → Auth ID. 20 characters, starts with MA or SA.", placeholder: "MAXXXXXXXXXXXXXXXXXX", type: "text", caps: true },
    PLIVO_AUTH_TOKEN: { icon: "lock", color: "c-purple", hint: "Plivo Console → Overview → Auth Token. Stored on the server, never shown again in full.", placeholder: "Paste the token", type: "password" },
    CALLER_ID: { icon: "phone", color: "c-green", hint: "The Plivo number customers see. Tap “My numbers” to pick one from your account.", placeholder: "+1 212 555 0100", type: "tel" },
    PUBLIC_URL: { icon: "globe", color: "c-teal", hint: "Public HTTPS address of this server. Plivo sends call events here.", placeholder: "https://1-2-3-4.nip.io", type: "url" },
    THREECX_SIP_URI: { icon: "link", color: "c-indigo", hint: "Full address of the 3CX sales queue. Or use the setup assistant above.", placeholder: "sip:800@company.3cx.us", type: "text" },
    MAX_AGENT_CHANNELS: { icon: "users", color: "c-orange", hint: "How many calls your 3CX trunk and agents can take at once. Callers above this hear a callback message.", type: "number", min: 1, max: 500, step: 1, unit: "lines" },
    MAX_CONCURRENT_CALLS: { icon: "bolt", color: "c-blue", hint: "Calls in flight at the same time (Plivo channels).", type: "number", min: 1, max: 500, step: 1, unit: "calls" },
    CALLS_PER_SECOND: { icon: "gauge", color: "c-purple", hint: "Your Plivo account CPS limit. Ask Plivo support to raise it.", type: "number", min: 0.1, max: 50, step: 0.1, unit: "/s" },
    STALE_CALL_MINUTES: { icon: "clock", color: "c-gray", hint: "Free a line if Plivo never reports the hangup after this many minutes.", type: "number", min: 1, max: 240, step: 1, unit: "min" },
    COMPANY_NAME: { icon: "building", color: "c-indigo", hint: "Spoken in the message to the customer.", placeholder: "Your Company", type: "text" },
    OPT_OUT_PHONE: { icon: "ban", color: "c-red", hint: "Announced so people can opt out of further calls.", placeholder: "+1 212 555 0100", type: "tel" },
    TEST_NUMBERS: { icon: "flask", color: "c-pink", hint: "Your own phones, comma separated. Test calls only go to these.", placeholder: "+1 212 555 0100, +1 305 555 0100", type: "tel" },
  };

  const TITLES = { home: ["Overview", "Home"], plivo: ["Telephony", "Plivo"], "3cx": ["Phone system", "3CX"], campaign: ["Dialer", "Campaign"], settings: ["Preferences", "Settings"] };
  const STATUS = {
    idle: ["Not started", ""], pending: ["Starting…", "live"], running: ["Running", "live"], stopping: ["Stopping…", "bad"],
    stopped: ["Stopped", ""], done: ["Finished", "ok"], failed: ["Failed", "bad"],
  };

  let S = null; // last /api/state
  let tab = "home";
  let pollTimer = null;
  const ui = { checks: {}, dryRun: null };

  // ------------------------------------------------------------ network
  async function api(path, opts = {}) {
    const init = { method: opts.method || (opts.body ? "POST" : "GET"), headers: { "X-Panel": "1" }, credentials: "same-origin" };
    if (opts.body instanceof FormData) init.body = opts.body;
    else if (opts.body) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    let res, data;
    try {
      res = await fetch(path, init);
      data = await res.json();
    } catch {
      throw Object.assign(new Error("Network error — check your connection"), { status: 0 });
    }
    if (res.status === 401 && path !== "/api/login") { showLogin(); throw Object.assign(new Error("Signed out"), { status: 401 }); }
    if (!res.ok || data.ok === false) throw Object.assign(new Error(data.error || "Something went wrong"), { status: res.status, data });
    return data;
  }

  // ------------------------------------------------------------ toast
  let toastTimer;
  function toast(msg, ok = true) {
    const t = $("#toast");
    t.className = "toast glass " + (ok ? "ok" : "bad");
    t.innerHTML = icon(ok ? "check" : "x") + `<span>${esc(msg)}</span>`;
    t.hidden = false;
    t.style.animation = "none"; void t.offsetWidth; t.style.animation = "";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.hidden = true), 2800);
  }

  async function busy(btn, fn) {
    if (btn) { btn.classList.add("loading"); btn.disabled = true; }
    try { return await fn(); } finally { if (btn) { btn.classList.remove("loading"); btn.disabled = false; } }
  }

  // ------------------------------------------------------------ auth
  function showLogin(disabled) {
    clearInterval(pollTimer);
    $("#app").hidden = true;
    $("#login").hidden = false;
    $("#login-disabled").hidden = !disabled;
    $("#password").disabled = !!disabled;
    $("#login-form button").disabled = !!disabled;
    if (!disabled) setTimeout(() => $("#password").focus(), 50);
  }

  async function boot() {
    let s;
    try { s = await (await fetch("/api/session", { credentials: "same-origin" })).json(); }
    catch { s = { enabled: true, auth: false }; }
    if (!s.enabled) return showLogin(true);
    if (!s.auth) return showLogin(false);
    startApp();
  }

  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#login-form button[type=submit]");
    $("#login-error").textContent = "";
    try {
      await busy(btn, () => api("/api/login", { body: { password: $("#password").value } }));
      $("#password").value = "";
      startApp();
    } catch (err) {
      $("#login-error").textContent = err.message;
      const card = $("#login-form");
      card.classList.remove("shake"); void card.offsetWidth; card.classList.add("shake");
    }
  });

  function startApp() {
    $("#login").hidden = true;
    $("#app").hidden = false;
    const saved = (() => { try { return sessionStorage.getItem("tab"); } catch { return null; } })();
    go(TITLES[saved] ? saved : "home", false);
    refresh();
    clearInterval(pollTimer);
    pollTimer = setInterval(() => { if (!document.hidden && $("#sheet-wrap").hidden) refresh(); }, 4000);
  }

  async function refresh() {
    try {
      S = await api("/api/state");
      render();
    } catch (e) { if (e.status !== 401) toast(e.message, false); }
  }

  // ------------------------------------------------------------ navigation
  function go(name, animate = true) {
    tab = name;
    try { sessionStorage.setItem("tab", name); } catch {}
    $$(".tabbar button").forEach((b, i) => {
      const on = b.dataset.tab === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
      if (on) $(".lens").style.transform = `translateX(${i * 100}%)`;
    });
    $$(".view").forEach((v) => {
      const on = v.dataset.view === name;
      v.hidden = !on;
      if (on && animate) { v.style.animation = "none"; void v.offsetWidth; v.style.animation = ""; }
    });
    $("#subtitle").textContent = TITLES[name][0];
    $("#title").textContent = TITLES[name][1];
    if (animate) window.scrollTo({ top: 0, behavior: "smooth" });
    render();
  }

  // ------------------------------------------------------------ render helpers
  function settingRow(name, extra = "") {
    const f = FIELDS[name], s = S.settings[name];
    const val = s.set ? esc(f.unit && s.value ? `${s.value} ${f.unit}` : s.value) : "Not set";
    return `<button class="row" data-action="edit" data-field="${name}" ${extra}>
      <span class="ico ${f.color}">${icon(f.icon)}</span>
      <span class="label"><b>${esc(s.label)}</b></span>
      <span class="val ${s.set ? "" : "unset"}">${val}</span>${icon("chev").replace("<svg", '<svg class="chev"')}
    </button>`;
  }

  function actionRow(action, ic, color, title, sub) {
    return `<button class="row" data-action="${action}">
      <span class="ico ${color}">${icon(ic)}</span>
      <span class="label"><b>${esc(title)}</b>${sub ? `<small>${esc(sub)}</small>` : ""}</span>${icon("chev").replace("<svg", '<svg class="chev"')}
    </button>`;
  }

  function checksList(items) {
    if (!items) return "";
    let group = null, out = "";
    for (const it of items) {
      if (it.group && it.group !== group) { group = it.group; out += `<li class="group">${esc(group)}</li>`; }
      const ic = { ok: "check", warn: "warn", error: "x", info: "info" }[it.level] || "info";
      out += `<li class="${esc(it.level)}">${icon(ic)}<span>${esc(it.text)}</span></li>`;
    }
    return `<ul class="checks">${out}</ul>`;
  }

  function warningsCard(list) {
    if (!list || !list.length) return "";
    return list.map((w) => `<div class="alert glass">${icon("warn")}<p>${esc(w)}</p></div>`).join("");
  }

  const statChips = (obj) => {
    const entries = Object.entries(obj || {});
    if (!entries.length) return "";
    return `<div class="chips">${entries.map(([k, v]) => `<span class="chip"><b>${esc(v)}</b>${esc(k.replace(/_/g, " "))}</span>`).join("")}</div>`;
  };

  // ------------------------------------------------------------ views
  function render() {
    if (!S) return;
    const view = $(`.view[data-view="${tab}"]`);
    const html = ({ home: viewHome, plivo: viewPlivo, "3cx": view3cx, campaign: viewCampaign, settings: viewSettings })[tab]();
    if (view.dataset.html !== html) {
      // Preserve typing in inputs across auto-refresh.
      const focused = document.activeElement && view.contains(document.activeElement) ? document.activeElement.id : null;
      const values = {};
      $$("input[id]", view).forEach((i) => { if (i.type !== "file") values[i.id] = i.value; });
      view.innerHTML = html;
      view.dataset.html = html;
      for (const [id, v] of Object.entries(values)) { const i = document.getElementById(id); if (i && !i.value) i.value = v; }
      if (focused) { const el = document.getElementById(focused); if (el) el.focus(); }
      bindView(view);
    }
  }

  function viewHome() {
    const L = S.live, c = S.campaign;
    const pct = L.max ? Math.min(1, L.active / L.max) : 0;
    const C = 2 * Math.PI * 54;
    const st = STATUS[c.status] || [c.status, ""];
    const agentsPct = L.max_agents ? Math.min(100, (L.agents / L.max_agents) * 100) : 0;
    const missing = S.missing.length ? `<div class="alert glass">${icon("warn")}<p><b>Finish setup</b>Not set: ${esc(S.missing.join(", "))}</p></div>` : "";
    return `${missing}
    <div class="hero glass">
      <div class="ring" role="img" aria-label="${L.active} of ${L.max} calls live">
        <svg viewBox="0 0 132 132"><defs><linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f8cff"/><stop offset="1" stop-color="#a65bff"/></linearGradient></defs>
          <circle class="track" cx="66" cy="66" r="54"/>
          <circle class="meter" cx="66" cy="66" r="54" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${(C * (1 - pct)).toFixed(1)}"/>
        </svg>
        <div class="center"><b>${L.active}</b><span>of ${L.max} live</span></div>
      </div>
      <div class="hero-side">
        <h2>${esc(c.name || "No campaign yet")}</h2>
        <p><span class="dot ${st[1]}"></span>&nbsp; ${esc(st[0])}</p>
        <div class="bar-label"><span>On 3CX</span><span>${L.agents} / ${L.max_agents}</span></div>
        <div class="bar"><i data-w="${agentsPct}"></i></div>
      </div>
    </div>
    <div class="tiles">
      ${tile("plivo", "pulse", "c-blue", "Plivo", S.ready.plivo ? "Configured" : "Needs setup", S.ready.plivo)}
      ${tile("3cx", "link", "c-indigo", "3CX", S.ready["3cx"] ? "Configured" : "Needs setup", S.ready["3cx"])}
      ${tile("campaign", "list", "c-green", "Contacts", c.contacts ? "List uploaded" : "No list yet", c.contacts)}
      ${tile("settings", "ban", "c-red", "Do not call", `${S.dnc_count} numbers`, null)}
    </div>
    <p class="section-label">Quick actions</p>
    <div class="list glass">
      ${actionRow("check-all", "check", "c-green", "Run full check", "Keys, numbers, webhook and 3CX")}
      ${actionRow("open-test", "phone", "c-pink", "Test call", "Call your own phone and press 1")}
    </div>
    ${ui.checks.all ? `<div class="card glass"><h2>Health check</h2>${checksList(ui.checks.all)}</div>` : ""}`;
  }

  function tile(target, ic, color, title, sub, ok) {
    const dot = ok === null ? "" : `<span class="dot ${ok ? "ok" : "bad"}"></span>`;
    return `<button class="tile glass" data-action="go" data-tab="${target}">
      <span class="top"><span class="ico ${color}">${icon(ic)}</span>${dot}</span>
      <span><b>${esc(title)}</b><small>${esc(sub)}</small></span></button>`;
  }

  function viewPlivo() {
    return `${warningsCard(S.warnings.plivo)}
    <p class="section-label">Account</p>
    <div class="list glass">${settingRow("PLIVO_AUTH_ID")}${settingRow("PLIVO_AUTH_TOKEN")}</div>
    <p class="section-label">Calling</p>
    <div class="list glass">${settingRow("CALLER_ID")}${actionRow("numbers", "list", "c-teal", "My numbers", "Pick the Caller ID from your account")}${settingRow("PUBLIC_URL")}</div>
    <p class="footnote">Keys are in Plivo Console → Overview. The Webhook URL is this server's https address.</p>
    <div class="card glass">
      <h2>Connection</h2><p class="muted">Checks the keys, balance, Caller ID and that Plivo can reach this server.</p>
      <button class="btn primary wide" data-action="check" data-what="plivo">${icon("pulse")} Check Plivo</button>
      ${checksList(ui.checks.plivo)}
    </div>`;
  }

  function view3cx() {
    return `${warningsCard(S.warnings["3cx"])}
    <div class="card glass">
      <h2>Setup assistant</h2><p class="muted">Where should callers who press 1 go?</p>
      <div class="wizard">
        <div class="pair">
          <input id="wz-host" placeholder="company.3cx.us" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="3CX address">
          <input id="wz-ext" placeholder="800" inputmode="numeric" autocomplete="off" aria-label="Queue or ring group">
        </div>
        <div class="uri-preview" id="wz-preview"></div>
        <p class="error" id="wz-error"></p>
        <button class="btn primary wide" data-action="wizard">${icon("wand")} Save SIP address</button>
      </div>
    </div>
    <p class="section-label">Routing</p>
    <div class="list glass">${settingRow("THREECX_SIP_URI")}${settingRow("MAX_AGENT_CHANNELS")}</div>
    <p class="footnote">Address: the one you open 3CX with. Queue: 3CX → Ring Groups / Queues.</p>
    <div class="card glass">
      <h2>Connection</h2><p class="muted">Resolves your PBX and probes the SIP ports.</p>
      <button class="btn primary wide" data-action="check" data-what="3cx">${icon("pulse")} Check 3CX</button>
      ${checksList(ui.checks["3cx"])}
    </div>`;
  }

  function viewCampaign() {
    const c = S.campaign, st = STATUS[c.status] || [c.status, ""];
    const canStop = c.status === "pending" || c.status === "running";
    const dr = ui.dryRun;
    return `<div class="card glass">
      <div class="status-head"><span class="dot ${st[1]}"></span><div><h2>${esc(c.name || "No campaign yet")}</h2><span class="muted">${esc(st[0])}</span></div></div>
      ${statChips(c.progress)}
      ${Object.keys(c.results || {}).length ? `<p class="section-label">Results</p>${statChips(c.results)}` : ""}
      ${c.message ? `<p class="error">${esc(c.message)}</p>` : ""}
      ${canStop ? `<button class="btn danger wide" data-action="stop">${icon("stop")} Stop campaign</button>` : ""}
    </div>
    <p class="section-label">1 · Contacts</p>
    <div class="card glass">
      <label class="drop" id="drop">
        <input type="file" id="csv" accept=".csv,text/csv">
        ${icon("upload")}<b>${c.contacts ? "Replace contact list" : "Upload contact list"}</b>
        <small>CSV · checked without calling anyone</small>
      </label>
      ${dr ? `<p class="section-label">${esc(dr.filename)}</p>${statChips(dr.stats)}<p class="footnote">Numbers skipped for calling hours are retried on the next run.</p>` : ""}
    </div>
    <p class="section-label">2 · Launch</p>
    <div class="card glass">
      <div class="inline-form">
        <input id="camp-name" placeholder="fall-promo" autocomplete="off" autocapitalize="off" spellcheck="false" aria-label="Campaign name">
        <button class="btn primary" data-action="start" ${!c.contacts || c.busy ? "disabled" : ""}>${icon("play")} Start</button>
      </div>
      <p class="error" id="camp-error"></p>
      <p class="footnote">${c.contacts ? `Up to ${S.live.max} calls at once · ${esc(S.settings.CALLS_PER_SECOND.value)}/s · ${S.live.max_agents} lines to 3CX` : "Upload a contact list first."}</p>
    </div>
    <p class="section-label">Do not call · ${S.dnc_count}</p>
    <div class="card glass">
      <div class="inline-form">
        <input id="dnc-phone" type="tel" placeholder="+1 212 555 0100" aria-label="Number to block">
        <button class="btn glassy" data-action="dnc">${icon("ban")} Block</button>
      </div>
      <p class="error" id="dnc-error"></p>
    </div>`;
  }

  function viewSettings() {
    const nums = S.test_numbers;
    return `<p class="section-label">Load</p>
    <div class="list glass">${settingRow("MAX_CONCURRENT_CALLS")}${settingRow("CALLS_PER_SECOND")}${settingRow("STALE_CALL_MINUTES")}</div>
    ${warningsCard(S.warnings.limits)}
    <p class="section-label">Company</p>
    <div class="list glass">${settingRow("COMPANY_NAME")}${settingRow("OPT_OUT_PHONE")}</div>
    <p class="section-label">Testing</p>
    <div class="list glass">${settingRow("TEST_NUMBERS")}
      ${nums.map((n) => `<button class="row" data-action="test" data-phone="${esc(n)}"><span class="ico c-green">${icon("phone")}</span><span class="label"><b>Call ${esc(n)}</b><small>Answer and press 1 — you should reach 3CX</small></span></button>`).join("")}
    </div>
    <p class="section-label">Panel</p>
    <div class="list glass">
      ${actionRow("theme", "moon", "c-gray", "Appearance", themeLabel())}
      ${actionRow("logout", "logout", "c-red", "Sign out", "")}
    </div>`;
  }

  function bindView(view) {
    $$(".bar i[data-w]", view).forEach((i) => requestAnimationFrame(() => i.style.setProperty("width", i.dataset.w + "%")));
    const host = $("#wz-host", view);
    if (host) {
      const upd = () => {
        const h = host.value.trim().replace(/^(https?:\/\/|sip:)/i, "").split("/")[0] || "company.3cx.us";
        const x = $("#wz-ext").value.trim() || "800";
        $("#wz-preview").innerHTML = `sip:<b>${esc(x)}</b>@<b>${esc(h)}</b>`;
      };
      host.addEventListener("input", upd); $("#wz-ext").addEventListener("input", upd); upd();
    }
    const drop = $("#drop", view);
    if (drop) {
      $("#csv").addEventListener("change", (e) => e.target.files[0] && upload(e.target.files[0]));
      ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
      ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
      drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]));
    }
    $$("input", view).forEach((i) => i.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const btn = { "camp-name": "start", "dnc-phone": "dnc", "wz-ext": "wizard", "wz-host": "wizard" }[i.id];
      if (btn) { e.preventDefault(); $(`[data-action="${btn}"]`, view)?.click(); }
    }));
  }

  // ------------------------------------------------------------ theme
  function themeLabel() {
    const t = (() => { try { return localStorage.getItem("theme"); } catch { return null; } })();
    return t === "dark" ? "Dark" : t === "light" ? "Light" : "Automatic";
  }
  function applyTheme() {
    const t = (() => { try { return localStorage.getItem("theme"); } catch { return null; } })();
    if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
  }
  applyTheme();

  // ------------------------------------------------------------ sheet
  function openSheet(html, onOpen) {
    $("#sheet-body").innerHTML = html;
    $("#sheet-wrap").hidden = false;
    $("#sheet").classList.remove("closing"); $(".sheet-dim").classList.remove("closing");
    onOpen && onOpen($("#sheet"));
    const first = $("#sheet input");
    if (first && matchMedia("(pointer: fine)").matches) setTimeout(() => first.focus(), 120);
  }
  function closeSheet() {
    if ($("#sheet-wrap").hidden) return;
    $("#sheet").classList.add("closing"); $(".sheet-dim").classList.add("closing");
    setTimeout(() => { $("#sheet-wrap").hidden = true; $("#sheet-body").innerHTML = ""; }, 240);
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });

  function editSheet(name) {
    const f = FIELDS[name], s = S.settings[name];
    const isNum = f.type === "number";
    const cur = s.set && !s.secret ? s.value : "";
    const inputType = isNum ? "text" : f.type === "url" ? "url" : f.type === "tel" ? "tel" : f.type === "password" ? "password" : "text";
    openSheet(`
      <h3 id="sheet-title">${esc(s.label)}</h3>
      <p class="hint">${esc(f.hint)}</p>
      ${s.secret && s.set ? `<p class="current">Current: ${esc(s.value)} · leave blank to keep</p>` : ""}
      <input id="edit-input" type="${inputType}" ${isNum ? 'inputmode="decimal"' : ""} placeholder="${esc(f.placeholder || "")}" value="${esc(cur)}"
        autocomplete="off" autocapitalize="${f.caps ? "characters" : "off"}" spellcheck="false" aria-label="${esc(s.label)}">
      ${isNum ? `<input id="edit-range" type="range" min="${f.min}" max="${f.max}" step="${f.step}" value="${esc(cur || f.min)}" aria-label="${esc(s.label)} slider">
        <div class="range-labels"><span>${f.min}</span><span>${f.max} ${esc(f.unit)}</span></div>` : ""}
      <p class="error" id="edit-error"></p>
      <div class="actions"><button class="btn glassy" data-action="close-sheet">Cancel</button><button class="btn primary" data-action="save-field" data-field="${name}">Save</button></div>`,
    (sh) => {
      const inp = $("#edit-input", sh), rng = $("#edit-range", sh);
      if (rng) { rng.addEventListener("input", () => (inp.value = rng.value)); inp.addEventListener("input", () => { if (inp.value) rng.value = inp.value; }); }
      inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $('[data-action="save-field"]', sh).click(); } });
    });
  }

  async function saveField(btn) {
    const name = btn.dataset.field, inp = $("#edit-input");
    if (S.settings[name].secret && !inp.value.trim() && S.settings[name].set) return closeSheet();
    try {
      await busy(btn, () => api("/api/settings", { body: { values: { [name]: inp.value } } }));
      closeSheet(); toast(`${S.settings[name].label} saved`);
      ui.checks = {};
      refresh();
    } catch (e) {
      const msg = (e.data && e.data.errors && e.data.errors[name]) || e.message;
      $("#edit-error").textContent = msg; inp.classList.add("invalid");
      inp.addEventListener("input", () => inp.classList.remove("invalid"), { once: true });
    }
  }

  async function numbersSheet(btn) {
    let data;
    try { data = await busy(btn, () => api("/api/plivo/numbers")); }
    catch (e) { return toast(e.message, false); }
    const list = data.numbers.length
      ? data.numbers.map((n) => `<button class="${n.number === data.current ? "on" : ""}" data-action="pick-number" data-number="${esc(n.number)}"><span><b>${esc(n.number)}</b><br><small>${esc(n.alias || "Plivo number")}</small></span>${n.number === data.current ? icon("check") : ""}</button>`).join("")
      : `<p class="muted">No numbers in this Plivo account yet. Buy one in Plivo Console → Phone Numbers.</p>`;
    openSheet(`<h3 id="sheet-title">My numbers</h3><p class="hint">Customers will see the number you pick.</p>
      <div class="pick">${list}</div>
      <div class="actions"><button class="btn glassy" data-action="edit" data-field="CALLER_ID">Enter manually</button></div>`);
  }

  function testSheet() {
    const nums = S.test_numbers;
    openSheet(`<h3 id="sheet-title">Test call</h3>
      <p class="hint">I'll call your phone. Answer, press 1, and you should reach 3CX.</p>
      ${nums.length ? `<div class="pick">${nums.map((n) => `<button data-action="test" data-phone="${esc(n)}"><b>${esc(n)}</b>${icon("phone")}</button>`).join("")}</div>`
        : `<p class="muted">Add your own numbers first.</p><div class="actions"><button class="btn primary" data-action="edit" data-field="TEST_NUMBERS">Add test numbers</button></div>`}`);
  }

  // ------------------------------------------------------------ actions
  async function upload(file) {
    if (!/\.csv$/i.test(file.name)) return toast("Choose a .csv file", false);
    const fd = new FormData(); fd.append("file", file);
    const drop = $("#drop"); drop && drop.classList.add("over");
    try {
      const r = await api("/api/contacts", { body: fd });
      ui.dryRun = { filename: r.filename, stats: r.stats };
      toast(`${r.stats.would_call || 0} contacts can be called now`);
      refresh();
    } catch (e) { toast(e.message, false); }
    finally { drop && drop.classList.remove("over"); }
  }

  const actions = {
    go: (b) => go(b.dataset.tab),
    refresh: async (b) => { b.classList.remove("spin"); void b.offsetWidth; b.classList.add("spin"); await refresh(); },
    edit: (b) => editSheet(b.dataset.field),
    "save-field": saveField,
    "close-sheet": closeSheet,
    numbers: numbersSheet,
    "pick-number": async (b) => {
      try { await api("/api/settings", { body: { values: { CALLER_ID: b.dataset.number } } }); closeSheet(); toast("Caller ID saved"); refresh(); }
      catch (e) { toast(e.message, false); }
    },
    check: async (b) => {
      const what = b.dataset.what;
      try { ui.checks[what] = (await busy(b, () => api(`/api/check/${what}`, { method: "POST", body: {} }))).items; render(); }
      catch (e) { toast(e.message, false); }
    },
    "check-all": async (b) => {
      try { ui.checks.all = (await busy(b, () => api("/api/check/all", { method: "POST", body: {} }))).items; render(); }
      catch (e) { toast(e.message, false); }
    },
    "open-test": testSheet,
    test: async (b) => {
      try { await busy(b, () => api("/api/test", { body: { phone: b.dataset.phone } })); closeSheet(); toast(`Calling ${b.dataset.phone}…`); }
      catch (e) { toast(e.message, false); }
    },
    wizard: async (b) => {
      $("#wz-error").textContent = "";
      try {
        const r = await busy(b, () => api("/api/3cx/wizard", { body: { host: $("#wz-host").value, extension: $("#wz-ext").value } }));
        toast("3CX address saved"); ui.checks = {};
        await refresh();
        const p = $("#wz-preview"); if (p) p.textContent = r.value;
      } catch (e) {
        const er = e.data && e.data.errors;
        $("#wz-error").textContent = er ? Object.values(er).join(" · ") : e.message;
      }
    },
    start: (b) => {
      const name = $("#camp-name").value.trim();
      $("#camp-error").textContent = "";
      if (!name) { $("#camp-error").textContent = "Give the campaign a name"; return; }
      openSheet(`<h3 id="sheet-title">Start “${esc(name)}”?</h3>
        <p class="hint">Calls begin right away and only reach contacts that pass consent, do-not-call and calling-hours checks.</p>
        <div class="chips"><span class="chip"><b>${S.live.max}</b>at once</span><span class="chip"><b>${esc(S.settings.CALLS_PER_SECOND.value)}</b>per second</span><span class="chip"><b>${S.live.max_agents}</b>3CX lines</span></div>
        <div class="actions"><button class="btn glassy" data-action="close-sheet">Cancel</button><button class="btn primary" data-action="confirm-start" data-name="${esc(name)}">${icon("play")} Start</button></div>`);
    },
    "confirm-start": async (b) => {
      try {
        await busy(b, () => api("/api/campaign/start", { body: { name: b.dataset.name } }));
        closeSheet(); toast("Campaign starting"); refresh();
      } catch (e) { closeSheet(); const er = $("#camp-error"); if (er) er.textContent = e.message; toast(e.message, false); }
    },
    stop: async (b) => {
      try { await busy(b, () => api("/api/campaign/stop", { method: "POST", body: {} })); toast("Stopping — calls in progress will finish"); refresh(); }
      catch (e) { toast(e.message, false); }
    },
    dnc: async (b) => {
      const inp = $("#dnc-phone");
      $("#dnc-error").textContent = "";
      try { const r = await busy(b, () => api("/api/dnc", { body: { phone: inp.value } })); inp.value = ""; toast(`${r.phone} blocked`); refresh(); }
      catch (e) { $("#dnc-error").textContent = e.message; }
    },
    theme: () => {
      const order = [null, "light", "dark"];
      let cur = null; try { cur = localStorage.getItem("theme"); } catch {}
      const next = order[(order.indexOf(cur) + 1) % 3];
      try { next ? localStorage.setItem("theme", next) : localStorage.removeItem("theme"); } catch {}
      applyTheme(); render(); toast(`Appearance: ${themeLabel()}`);
    },
    logout: async () => { try { await api("/api/logout", { method: "POST", body: {} }); } catch {} S = null; showLogin(false); },
  };

  document.addEventListener("click", (e) => {
    const tabBtn = e.target.closest(".tabbar button");
    if (tabBtn) return go(tabBtn.dataset.tab);
    const el = e.target.closest("[data-action]");
    if (!el || !actions[el.dataset.action]) return;
    e.preventDefault();
    actions[el.dataset.action](el);
  });

  boot();
})();
