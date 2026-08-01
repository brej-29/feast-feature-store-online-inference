/* Fraud Feature Store — UI logic (vanilla JS, no build step). */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fmt = (n, d = 2) =>
    n === null || n === undefined || Number.isNaN(n)
      ? "—"
      : Number(n).toLocaleString(undefined, { maximumFractionDigits: d });
  const money = (n) => (n === null || n === undefined ? "—" : "$" + fmt(n, 0));
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let body = null;
    try { body = await res.json(); } catch (_) {}
    if (!res.ok) {
      const detail = (body && body.detail) || `${res.status} ${res.statusText}`;
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 4200);
  }

  function animateNumber(el, to, { suffix = "", decimals = 0, dur = 700 } = {}) {
    if (reduce) { el.textContent = fmt(to, decimals) + suffix; return; }
    const from = 0, start = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(from + (to - from) * eased, decimals) + suffix;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  /* ---- Status pills + hero stats + model card ---- */
  function pill(label, state, value) {
    const cls = { ok: "live", warn: "warn", down: "down" }[state] || "";
    return `<span class="pill"><span class="dot ${cls}"></span><span class="txt-full">${label}</span>&nbsp;<span style="color:var(--text)">${value}</span></span>`;
  }

  async function loadStatus() {
    const statuses = $("#statuses");
    let apiOk = false, storeState = "down", storeTxt = "offline", model = "—";
    try { await api("/health"); apiOk = true; } catch (_) {}
    try {
      const info = await api("/api/model/info");
      model = info.model_version || "—";
      $("#statModel").textContent = model;
      const m = info.metrics || {};
      if (m.pr_auc) $("#statPrauc").textContent = fmt(m.pr_auc, 2);
      renderMetrics(m, info);
    } catch (_) {}
    try {
      const h = await api("/api/feast/health");
      if (h.status === "ok") { storeState = "ok"; storeTxt = "connected"; }
    } catch (_) { storeState = "warn"; storeTxt = "degraded"; }
    statuses.innerHTML =
      pill("API", apiOk ? "ok" : "down", apiOk ? "live" : "down") +
      pill("Store", storeState, storeTxt) +
      pill("Model", model === "—" ? "warn" : "ok", model);
  }

  function renderMetrics(m, info) {
    const rows = [
      ["PR-AUC", fmt(m.pr_auc, 3)],
      ["ROC-AUC", fmt(m.roc_auc, 3)],
      ["Recall @ 90% precision", m["recall_at_precision_0.90"] != null ? fmt(m["recall_at_precision_0.90"], 2) : "—"],
      ["Decision threshold", info && info.threshold != null ? fmt(info.threshold, 3) : "—"],
      ["Test fraud rate", m.test_fraud_rate != null ? (fmt(m.test_fraud_rate * 100, 2) + "%") : "—"],
      ["Brier score", fmt(m.brier_score, 4)],
    ];
    $("#metrics").innerHTML = rows
      .map(([l, n]) => `<div class="metric"><div class="n mono">${n}</div><div class="l">${l}</div></div>`)
      .join("");
  }

  /* ---- Presets ---- */
  let presets = [];
  async function loadPresets() {
    const sel = $("#preset");
    try {
      const data = await api("/api/demo/entities");
      presets = data.scenarios || [];
      sel.innerHTML =
        `<option value="">Custom transaction…</option>` +
        presets.map((s, i) => `<option value="${i}">${esc(s.label)}</option>`).join("");
      if (presets.length) { sel.value = "0"; applyPreset(0); }
    } catch (e) {
      sel.innerHTML = `<option value="">Presets unavailable</option>`;
    }
  }
  function applyPreset(i) {
    const s = presets[i];
    if (!s) { $("#presetNote").textContent = ""; return; }
    $("#amount").value = s.amount;
    $("#type").value = s.type;
    $("#oldbalanceOrg").value = s.oldbalanceOrg;
    $("#oldbalanceDest").value = s.oldbalanceDest;
    $("#customer_id").value = s.customer_id;
    $("#merchant_id").value = s.merchant_id;
    $("#presetNote").textContent = s.note || "";
  }

  function readForm() {
    return {
      entity_ids: {
        customer_id: $("#customer_id").value.trim(),
        merchant_id: $("#merchant_id").value.trim(),
      },
      request: {
        amount: parseFloat($("#amount").value) || 0,
        type: $("#type").value,
        oldbalanceOrg: parseFloat($("#oldbalanceOrg").value) || 0,
        oldbalanceDest: parseFloat($("#oldbalanceDest").value) || 0,
      },
    };
  }

  /* ---- Gauge ---- */
  function gaugeSvg(p, fraud) {
    const r = 64, c = 2 * Math.PI * r;
    const color = fraud ? "var(--danger)" : "var(--accent)";
    const off = reduce ? c * (1 - p) : c;
    return `
      <svg width="150" height="150" viewBox="0 0 150 150">
        <circle cx="75" cy="75" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="11"/>
        <circle id="gaugeArc" cx="75" cy="75" r="${r}" fill="none" stroke="${color}" stroke-width="11"
          stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"
          transform="rotate(-90 75 75)" style="transition:stroke-dashoffset .9s var(--ease)"/>
      </svg>`;
  }

  /* ---- Feature groups ---- */
  const GROUP_LABELS = {
    customer_profile_v2: "Customer profile",
    merchant_profile_v2: "Merchant profile",
    device_profile_v2: "Device profile",
    account_profile_v2: "Account profile",
    geocell_profile_v2: "Geo-cell profile",
    customer_realtime_v1: "Customer real-time",
  };
  function renderFeatureGroups(retrieved, requestFeatures) {
    const groups = {};
    Object.entries(retrieved || {}).forEach(([full, info]) => {
      const [view, ...rest] = full.split("__");
      const short = rest.join("__");
      (groups[view] = groups[view] || []).push([short, info.value, info.from_store]);
    });
    let html = "";
    // request features first — these come straight from the transaction
    const reqRows = Object.entries(requestFeatures || {})
      .map(([k, v]) => `<tr><td class="name">${esc(k)}</td><td class="value">${fmt(v, 3)}</td></tr>`)
      .join("");
    html += featGroup("Request (from the transaction)", reqRows, "request", true);
    Object.keys(GROUP_LABELS).forEach((view) => {
      const rows = (groups[view] || []);
      if (!rows.length) return;
      const anyStore = rows.some((r) => r[2]);
      const body = rows
        .map(([n, v, fromStore]) =>
          `<tr><td class="name">${esc(n)}</td><td class="value">${fmt(v, 3)}<span class="flag ${fromStore ? "src store" : "src default"}">${fromStore ? "store" : "default"}</span></td></tr>`)
        .join("");
      html += featGroup(GROUP_LABELS[view], body, anyStore ? "store" : "default", false);
    });
    return `<div class="feat-groups">${html}</div>`;
  }
  function featGroup(title, rows, srcClass, open) {
    const badge = srcClass === "request"
      ? ""
      : `<span class="src ${srcClass}">${srcClass === "store" ? "from store" : "defaults"}</span>`;
    return `<details class="fgroup"${open ? " open" : ""}>
      <summary>${title}${badge}
        <svg class="chev" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
      </summary>
      <table class="ftable"><tbody>${rows}</tbody></table>
    </details>`;
  }

  /* ---- Why-this-score contributions ---- */
  function contribSummary(list, fraud) {
    const raising = list.filter((c) => c.impact > 0);
    const lowering = list.filter((c) => c.impact < 0);
    const names = (arr, n) => arr.slice(0, n).map((c) => `<b>${esc(c.label)}</b>`);
    const join = (arr) => arr.length <= 1 ? arr.join("") : arr.slice(0, -1).join(", ") + " and " + arr[arr.length - 1];

    if (!raising.length && !lowering.length) return "";
    if (raising.length && !lowering.length) {
      return `${fraud ? "Flagged mainly because of" : "Nudged toward suspicious mainly because of"} ${join(names(raising, 3))}` +
        (raising.length > 3 ? `, plus ${raising.length - 3} more signal${raising.length - 3 > 1 ? "s" : ""}` : "") + ".";
    }
    if (lowering.length && !raising.length) {
      return `Looks legitimate mainly because of ${join(names(lowering, 3))} — nothing here resembles this dataset's fraud pattern.`;
    }
    return `${join(names(raising, 2))} push${raising.length === 1 ? "es" : ""} the risk up, while ${join(names(lowering, 2))} ` +
      `pull${lowering.length === 1 ? "s" : ""} it back down` +
      (fraud ? " — but not enough to outweigh the risk." : ", landing below the decision threshold.");
  }

  function renderContribs(list, fraud) {
    const maxAbs = Math.max(...list.map((c) => Math.abs(c.impact)), 1e-9);
    const rows = list.map((c) => {
      const up = c.impact > 0;
      const pct = Math.min(100, (Math.abs(c.impact) / maxAbs) * 100);
      return `<div class="ctr-row">
        <span class="ctr-label" title="${esc(c.feature)}">${esc(c.label)}</span>
        <span class="ctr-track"><span class="ctr-fill ${up ? "up" : "down"}" data-w="${pct}"></span></span>
        <span class="ctr-val ${up ? "up" : "down"}">${up ? "+" : "−"}${fmt(Math.abs(c.impact) * 100, 1)}pp</span>
      </div>`;
    }).join("");
    const summary = contribSummary(list, fraud);
    return `<div class="expl"><h4>Why this score</h4>
      ${summary ? `<p class="expl-summary">${summary}</p>` : ""}
      ${rows}
      <div class="lat-total">How much each signal moved the probability, versus that signal at its baseline value. Red raises risk, green lowers it.</div></div>`;
  }

  /* ---- Score ---- */
  async function score() {
    const btn = $("#scoreBtn"), lbl = btn.querySelector(".btnlabel");
    btn.disabled = true; lbl.textContent = "Scoring…";
    try {
      const payload = readForm();
      if (!payload.entity_ids.customer_id || !payload.entity_ids.merchant_id) {
        toast("Customer ID and Merchant ID are required."); return;
      }
      const r = await api("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderResult(r);
    } catch (e) {
      if (e.status === 401) toast("The API is key-protected. For a public demo, leave API_KEY unset on the server.");
      else toast("Prediction failed: " + e.message);
    } finally {
      btn.disabled = false; lbl.textContent = "Score transaction";
    }
  }

  function renderResult(r) {
    $("#resultEmpty").hidden = true;
    const body = $("#resultBody");
    body.hidden = false;
    const dbg = r.debug_info || {};
    const p = r.fraud_probability;
    const fraud = r.is_fraud;
    const maxLat = Math.max(r.feature_fetch_ms, r.inference_ms, 0.001);
    const fetchPct = Math.min(100, (r.feature_fetch_ms / maxLat) * 100);
    const inferPct = Math.min(100, (r.inference_ms / maxLat) * 100);

    body.innerHTML = `
      <div class="gauge-wrap">
        <div class="gauge">${gaugeSvg(p, fraud)}<div class="val"><div class="pct" id="gaugePct">0%</div><div class="cap">fraud risk</div></div></div>
        <div class="verdict">
          <span class="badge ${fraud ? "fraud" : "legit"}">
            ${fraud
              ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg> Flagged as fraud'
              : '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> Looks legitimate'}
          </span>
          <p>Probability <span class="mono">${fmt(p, 4)}</span> vs. decision threshold <span class="thresh">${fmt(r.threshold, 3)}</span>.</p>
          <p class="thresh">model ${esc(r.model_version)}</p>
          ${dbg.shadow ? `<p class="thresh">shadow · challenger <span class="mono">${esc(dbg.shadow.model_version)}</span>
            scored <span class="mono">${fmt(dbg.shadow.fraud_probability, 4)}</span>
            (${dbg.shadow.agrees_with_champion ? "agrees" : "<b style='color:var(--warn)'>disagrees</b>"}) —
            logged for comparison, never served</p>` : ""}
        </div>
      </div>
      ${dbg.degraded ? `<div class="degraded-note">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>
        <div>Online store unavailable — scored from request-time features and training defaults only.${dbg.degraded_reason ? `<br><span class="mono" style="font-size:11px;opacity:.8">${esc(dbg.degraded_reason)}</span>` : ""}</div></div>` : ""}
      ${dbg.top_contributors && dbg.top_contributors.length ? renderContribs(dbg.top_contributors, fraud) : ""}
      <div class="lat">
        <h4>Where the time went</h4>
        <div class="lat-bar"><span class="k">feature fetch</span><span class="track"><span class="fill fetch" id="lbFetch"></span></span><span class="v">${fmt(r.feature_fetch_ms, 1)} ms</span></div>
        <div class="lat-bar"><span class="k">inference</span><span class="track"><span class="fill infer" id="lbInfer"></span></span><span class="v">${fmt(r.inference_ms, 1)} ms</span></div>
        <div class="lat-total">total ${fmt(r.latency_ms, 1)} ms · ${dbg.missing_feature_count ?? 0} of 54 store features missing (defaulted)</div>
      </div>
      <div class="feat">
        <h4>Features the model actually saw</h4>
        ${renderFeatureGroups(dbg.retrieved_features, dbg.request_features)}
      </div>`;

    // animate
    animateNumber($("#gaugePct"), Math.round(p * 100), { suffix: "%" });
    if (!reduce) {
      const arc = $("#gaugeArc");
      if (arc) { const c = 2 * Math.PI * 64; requestAnimationFrame(() => { arc.style.strokeDashoffset = c * (1 - p); }); }
    }
    requestAnimationFrame(() => {
      $("#lbFetch").style.width = fetchPct + "%";
      $("#lbInfer").style.width = inferPct + "%";
      body.querySelectorAll(".ctr-fill").forEach((el) => { el.style.width = el.dataset.w + "%"; });
    });
  }

  /* ---- Streaming simulation ---- */
  function rtCard(view, opts = {}) {
    const feats = view.realtime_features || {};
    const prev = opts.prev || {};
    const rows = Object.entries(feats).map(([k, v]) => {
      const changed = opts.compare && String(prev[k]) !== String(v);
      return `<div class="rt-row ${changed ? "changed" : ""}"><span class="k">${esc(k)}</span><span class="v mono">${v === null ? "—" : fmt(v, 2)}</span></div>`;
    }).join("");
    const pct = Math.round(view.fraud_probability * 100);
    const col = view.is_fraud ? "var(--danger)" : "var(--accent)";
    return `<div class="rt-score" style="color:${col}">${pct}% <span style="font-size:12px;color:var(--text-dim)">fraud risk</span></div>${rows || '<div class="rt-row"><span class="k">no realtime features yet</span></div>'}`;
  }

  async function simulate() {
    const btn = $("#simBtn"), lbl = btn.querySelector(".btnlabel");
    btn.disabled = true; lbl.textContent = "Pushing event…";
    try {
      const r = await api("/api/demo/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(readForm()),
      });
      const wrap = $("#simResult");
      wrap.hidden = false;
      if (r.degraded) {
        $("#rtBefore").innerHTML = rtCard(r.before || { fraud_probability: 0, realtime_features: {} });
        $("#rtAfter").innerHTML = `<div style="color:var(--warn);font-size:13px">${r.message}</div>`;
        $("#simNote").textContent = "";
        return;
      }
      const prev = r.before.realtime_features || {};
      $("#rtBefore").innerHTML = rtCard(r.before);
      $("#rtAfter").innerHTML = rtCard(r.after, { compare: true, prev });
      $("#rtAfter").classList.remove("flash"); void $("#rtAfter").offsetWidth; $("#rtAfter").classList.add("flash");
      const d = (r.after.fraud_probability - r.before.fraud_probability) * 100;
      const ev = r.event || {};
      $("#simNote").textContent =
        `Pushed a live ${money(ev.last_txn_amount)} flagged event for ${ev.customer_id}. ` +
        `Real-time features updated in the store and the fraud probability moved ${d >= 0 ? "+" : ""}${fmt(d, 1)} points on re-score.`;
    } catch (e) {
      if (e.status === 401) toast("The API is key-protected. Leave API_KEY unset for a public demo.");
      else toast("Simulation failed: " + e.message);
    } finally {
      btn.disabled = false; lbl.textContent = "Push a live event & re-score";
    }
  }

  /* ---- Scroll reveal (position-based; robust everywhere, with a failsafe
     so content can never stay hidden even if scroll events never fire) ---- */
  function revealInView() {
    const vh = window.innerHeight || document.documentElement.clientHeight;
    document.querySelectorAll(".reveal:not(.in)").forEach((el) => {
      if (el.getBoundingClientRect().top < vh * 0.92) el.classList.add("in");
    });
  }
  function revealAll() {
    document.querySelectorAll(".reveal:not(.in)").forEach((el) => el.classList.add("in"));
  }
  function initReveal() {
    if (reduce) { revealAll(); return; }
    revealInView();
    window.addEventListener("scroll", revealInView, { passive: true });
    window.addEventListener("resize", revealInView);
    setTimeout(revealInView, 300);
    setTimeout(revealAll, 4000); // ultimate failsafe: never lose content
  }

  /* ---- Data glossary: accordion tree + detail panel ---- */
  function initGlossary() {
    const tree = $("#gtree");
    if (!tree) return;
    const detail = $("#gdetail");
    const entitySelect = $("#entitySelect");
    let lastLeaf = null; // remember the active leaf so the entity dropdown can live-update it

    function showDetail(leaf) {
      const label = leaf.dataset.label;
      const desc = leaf.dataset.desc;
      const full = leaf.dataset.full || `${entitySelect.value}__${leaf.dataset.suffix}`;
      detail.innerHTML = `
        <div class="gdetail-name">${esc(full)}</div>
        <div class="gdetail-label">${esc(label)}</div>
        <div class="gdetail-desc">${desc}</div>`;
    }

    tree.querySelectorAll(".gparent").forEach((btn) => {
      btn.addEventListener("click", () => {
        const group = btn.closest(".ggroup");
        const wasOpen = group.classList.contains("open");
        tree.querySelectorAll(".ggroup").forEach((g) => {
          g.classList.remove("open");
          g.querySelector(".gparent").setAttribute("aria-expanded", "false");
          g.querySelector(".gchildren").hidden = true;
        });
        if (!wasOpen) {
          group.classList.add("open");
          btn.setAttribute("aria-expanded", "true");
          group.querySelector(".gchildren").hidden = false;
        }
      });
    });

    tree.querySelectorAll(".gleaf").forEach((leaf) => {
      leaf.addEventListener("click", () => {
        tree.querySelectorAll(".gleaf.active").forEach((el) => el.classList.remove("active"));
        leaf.classList.add("active");
        lastLeaf = leaf.dataset.suffix ? leaf : null; // only profile leaves depend on the entity dropdown
        showDetail(leaf);
      });
    });

    entitySelect.addEventListener("change", () => { if (lastLeaf) showDetail(lastLeaf); });
  }

  /* ---- Wire up ---- */
  $("#preset").addEventListener("change", (e) => { if (e.target.value !== "") applyPreset(+e.target.value); });
  $("#scoreBtn").addEventListener("click", score);
  $("#simBtn").addEventListener("click", simulate);
  initReveal();
  initGlossary();
  loadStatus();
  loadPresets();
})();
