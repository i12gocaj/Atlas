/* Atlas dashboard. Render vanilla, sin dependencias. Lee window.ATLAS_DATA. */
(function () {
  "use strict";
  var D = window.ATLAS_DATA || {};
  var $ = function (id) { return document.getElementById(id); };

  // Formateo manual (no dependemos del ICU del navegador, que aqui no agrupa).
  function group(n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  var nf = { format: group };
  var eur = function (v) { return group(v) + " €"; };
  function eur2(v) {
    // Redondeamos una sola vez para que el acarreo de centimos suba al entero
    // (si no, un valor como 21,999 daria "21,100 €").
    var cents = Math.round(Math.abs(v) * 100);
    return group(Math.floor(cents / 100)) + "," + String(cents % 100).padStart(2, "0") + " €";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---------- meta / hero ----------
  function renderMeta() {
    var m = D.meta || {};
    var stats = [
      [nf.format(m.events || 0), "usos de IA en 8 semanas"],
      [m.teams || 0, "equipos"],
      [eur(m.total_cost_eur || 0), "coste total"],
      [eur(m.rejected_cost_eur || 0), (m.rejected_pct || 0).toString().replace(".", ",") + "% que no se aceptó"],
    ];
    $("stats").innerHTML = stats.map(function (s) {
      return '<div class="stat"><div class="v">' + esc(s[0]) + '</div><div class="k">' + esc(s[1]) + "</div></div>";
    }).join("");
  }

  // ---------- brief ----------
  function renderBrief() {
    var b = D.brief;
    var status = $("brief-status"), replay = $("replay");
    if (!b) {
      status.textContent = "Sin brief. Ejecuta: python -m atlas.cli brief";
      status.classList.remove("hide");
      replay.style.display = "none";
      return;
    }

    $("findings").innerHTML = (b.hallazgos || []).map(function (h) {
      var sev = (h.severidad || "media").toLowerCase();
      return '<div class="finding"><div class="sev ' + sev + '"></div><div>' +
        '<div class="t">' + esc(h.titulo) + "</div>" +
        '<div class="e">' + esc(h.evidencia) + "</div>" +
        (h.recomendacion ? '<div class="r">' + esc(h.recomendacion) + "</div>" : "") +
        "</div></div>";
    }).join("");

    var rows = (b.recomendaciones_limite || []).map(function (r) {
      var a = (r.accion || "").toLowerCase();
      return "<tr><td>" + esc(r.equipo) + "</td>" +
        '<td><span class="pill ' + a + '">' + esc((r.accion || "").toUpperCase()) + "</span></td>" +
        '<td style="color:var(--ink-2)">' + esc(r.motivo) + "</td></tr>";
    }).join("");
    $("limits").innerHTML = "<thead><tr><th>Equipo</th><th>Límite</th><th>Motivo</th></tr></thead><tbody>" + rows + "</tbody>";

    var ig = b.integrity, igEl = $("integrity");
    if (ig && ig.ok) {
      igEl.textContent = ig.checked + " cifras del resumen verificadas contra los datos, 0 inventadas por el agente";
    } else if (ig) {
      igEl.textContent = "resumen ajustado: el agente intentó usar una cifra fuera de los datos";
      igEl.style.color = "var(--ink-3)";
    } else {
      igEl.style.display = "none";
    }

    replay.addEventListener("click", function () { playBrief(b); });
    // El brief se reproduce cuando su seccion entra en pantalla (ver reveal()).
  }

  // Secuencia que muestra al agente analizando y reportando: estado -> resumen
  // (maquina de escribir) -> hallazgos uno a uno -> tabla de limites.
  function playBrief(b) {
    var status = $("brief-status"), resumen = $("resumen");
    var items = $("findings").querySelectorAll(".finding");
    resumen.textContent = "";
    status.classList.remove("hide");
    $("integrity").classList.remove("show");
    items.forEach(function (f) { f.classList.remove("show"); });
    $("limits").classList.remove("show");
    setTimeout(function () {
      status.classList.add("hide");
      typewriter(resumen, b.resumen_ejecutivo || "", function () {
        $("integrity").classList.add("show");
        items.forEach(function (f, i) { setTimeout(function () { f.classList.add("show"); }, 180 + i * 170); });
        setTimeout(function () { $("limits").classList.add("show"); }, 180 + items.length * 170 + 260);
      });
    }, 1150);
  }

  // typewriter respetando palabras (no parte a media palabra)
  function typewriter(el, text, done) {
    el.textContent = "";
    var caret = document.createElement("span");
    caret.className = "caret";
    el.appendChild(caret);
    function step() {
      var shown = el.textContent.length;
      if (shown >= text.length) {
        setTimeout(function () { caret.remove(); if (done) done(); }, 350);
        return;
      }
      var next = Math.min(text.length, shown + (text[shown] === " " ? 1 : 2));
      caret.insertAdjacentText("beforebegin", text.slice(shown, next));
      setTimeout(step, 15);
    }
    setTimeout(step, 240);
  }

  // ---------- control: politica y cumplimiento (simulador) ----------
  var SEV_LABEL = { critica: "crítica", alta: "alta", media: "media", baja: "baja" };
  // Anima el numero grande de un valor a otro (cuenta hacia arriba/abajo).
  var shownPct = 0;
  function tweenPct(target) {
    var from = shownPct, t0 = null;
    function step(ts) {
      if (t0 === null) t0 = ts;
      var k = Math.min(1, (ts - t0) / 500);
      var val = from + (target - from) * (1 - Math.pow(1 - k, 3));
      $("policy-pct").textContent = Math.round(val) + "%";
      if (k < 1) requestAnimationFrame(step); else shownPct = target;
    }
    requestAnimationFrame(step);
  }

  function renderPolicy() {
    var p = D.policy;
    if (!p) { return; }
    var viols = p.violaciones || [];
    var resolved = {};
    var euroOf = function (v) { return v.regla === "sin_derroche_modelo" ? (v.observado || 0) : 0; };

    function update() {
      var resN = viols.filter(function (_, i) { return resolved[i]; }).length;
      var remaining = viols.length - resN;
      var pct = Math.round((p.comprobaciones - remaining) / p.comprobaciones * 1000) / 10;
      tweenPct(pct);
      $("policy-pct").classList.toggle("done", remaining === 0);
      var euro = viols.reduce(function (s, v, i) { return s + (resolved[i] ? euroOf(v) : 0); }, 0);
      var euroTxt = euro ? " · recuperas " + eur2(euro) : "";
      if (resN === 0) {
        $("policy-meta").innerHTML = viols.length + " problemas de gobierno detectados sobre " + p.comprobaciones + " comprobaciones.";
      } else if (remaining === 0) {
        $("policy-meta").innerHTML = "<strong>cumplimiento total</strong>: los " + viols.length + " problemas resueltos" + euroTxt + ".";
      } else {
        $("policy-meta").innerHTML = resN + " de " + viols.length + " resueltos, " + remaining + " pendientes" + euroTxt + ".";
      }
      // Equipos: recalcula su cumplimiento segun lo resuelto.
      var rem = {};
      (p.por_equipo || []).forEach(function (t) { rem[t.equipo] = 0; });
      viols.forEach(function (v, i) { if (!resolved[i]) rem[v.equipo] = (rem[v.equipo] || 0) + 1; });
      $("policy-teams").innerHTML = (p.por_equipo || []).map(function (t) {
        var pc = Math.round((p.reglas_evaluadas - (rem[t.equipo] || 0)) / p.reglas_evaluadas * 100);
        var cls = pc === 100 ? "ok" : (pc >= 80 ? "warn" : "bad");
        return '<div class="pteam ' + cls + '"><span class="pt-name">' + esc(t.equipo) + "</span>" +
          '<span class="pt-pct">' + pc + "%</span></div>";
      }).join("");
      $("sim-reset").hidden = resN === 0;
      $("sim-apply").disabled = remaining === 0;
      $("sim-apply").textContent = remaining === 0 ? "Todo resuelto ✓" : "Aplicar todo";
    }

    $("violations").innerHTML = viols.map(function (v, i) {
      var sev = (v.severidad || "media").toLowerCase();
      return '<div class="viol" data-i="' + i + '" style="--d:' + (i * 90) + 'ms">' +
        '<span class="vsev ' + sev + '">' + esc(SEV_LABEL[sev] || sev) + "</span>" +
        '<div class="vbody">' +
        '<div class="vhead"><strong>' + esc(v.equipo) + "</strong> · " + esc(v.titulo) + "</div>" +
        '<div class="vdetail">' + esc(v.detalle) + "</div>" +
        '<div class="vfix">' + esc(v.remediacion) + "</div>" +
        "</div>" +
        '<button class="vresolve" type="button" data-i="' + i + '">Resolver</button>' +
        "</div>";
    }).join("");

    function setResolved(i, on) {
      resolved[i] = on;
      var el = $("violations").querySelector('.viol[data-i="' + i + '"]');
      if (el) {
        el.classList.toggle("resolved", on);
        el.querySelector(".vresolve").textContent = on ? "Resuelto ✓" : "Resolver";
      }
    }
    $("violations").addEventListener("click", function (e) {
      var b = e.target.closest(".vresolve"); if (!b) return;
      var i = b.getAttribute("data-i");
      setResolved(i, !resolved[i]); update();
    });
    $("sim-apply").addEventListener("click", function () {
      viols.forEach(function (_, i) { setResolved(i, true); }); update();
    });
    $("sim-reset").addEventListener("click", function () {
      viols.forEach(function (_, i) { setResolved(i, false); }); update();
    });

    shownPct = p.cumplimiento_pct;
    update();
  }

  // ---------- simulador del techo de coste ----------
  function renderCeilingSim() {
    var peaks = D.team_peaks;
    if (!peaks || !peaks.length) { return; }
    var slider = $("ceil-slider");
    var MAX = parseFloat(slider.max);
    $("ceil-bars").innerHTML = peaks.map(function (t) {
      return '<div class="cb-row" data-peak="' + t.peak_eur + '" data-team="' + esc(t.team) + '">' +
        '<div class="cb-name">' + esc(t.team) + "</div>" +
        '<div class="cb-track"><div class="cb-fill" data-w="' + (t.peak_eur / MAX * 100).toFixed(1) + '"></div>' +
        '<div class="cb-line"></div></div>' +
        '<div class="cb-val">' + eur(t.peak_eur) + "</div></div>";
    }).join("");
    var rows = Array.prototype.slice.call($("ceil-bars").querySelectorAll(".cb-row"));
    function update() {
      var ceil = parseFloat(slider.value);
      $("ceil-val").textContent = ceil;
      var linePct = (ceil / MAX * 100).toFixed(1) + "%";
      var over = [];
      rows.forEach(function (row) {
        var isOver = parseFloat(row.getAttribute("data-peak")) > ceil;
        row.classList.toggle("over", isOver);
        row.querySelector(".cb-line").style.left = linePct;
        if (isOver) over.push(row.getAttribute("data-team"));
      });
      var n = over.length;
      if (n === 0) {
        $("ceil-readout").innerHTML = "Con el techo en <strong>" + ceil + " €/semana</strong>, ningún equipo se pasa.";
      } else {
        $("ceil-readout").innerHTML = "Con el techo en <strong>" + ceil + " €/semana</strong>, se pasa" +
          (n > 1 ? "n " : " ") + "<strong>" + n + (n > 1 ? " equipos" : " equipo") + "</strong>: " + esc(over.join(", ")) + ".";
      }
    }
    slider.addEventListener("input", update);
    update();
  }

  // ---------- gobernanza en el tiempo (scorecard) ----------
  function renderHealth() {
    var s = D.scorecard;
    if (!s || !s.weeks || !s.weeks.length) { return; }
    var weeks = s.weeks, latest = s.latest;
    $("health-now").textContent = String(latest.score).replace(".", ",");
    $("health-now-lbl").textContent = "salud de gobierno la última semana (" +
      latest.iso_week.replace("2026-", "") + "), sobre 100. Pico de " +
      String(s.pico.score).replace(".", ",") + " en " +
      s.pico.iso_week.replace("2026-", "") + ".";
    var d = s.delta_vs_inicio;
    var dEl = $("health-delta");
    dEl.textContent = ((d > 0 ? "+" : "") + d).replace(".", ",");
    dEl.classList.add(d < 0 ? "danger" : "positive");

    // Sub-scores de la ultima semana.
    var comps = [
      ["Seguridad", latest.seguridad], ["Coste", latest.coste],
      ["Eficiencia", latest.eficiencia], ["Adopción", latest.adopcion],
    ];
    $("health-comp").innerHTML = '<div class="hc-title">las 4 palancas de la salud, sobre 100</div>' +
      comps.map(function (c) {
        var cls = c[1] >= 90 ? "ok" : (c[1] >= 75 ? "warn" : "bad");
        return '<div class="hc"><div class="hc-k">' + esc(c[0]) + "</div>" +
          '<div class="hc-track"><div class="hc-fill ' + cls + '" data-w="' + c[1].toFixed(0) + '"></div></div>' +
          '<div class="hc-v">' + Math.round(c[1]) + "</div></div>";
      }).join("");

    // Linea 0 a 100 con objetivo en 80.
    var W = 640, H = 260, padL = 16, padR = 16, padT = 24, padB = 30, n = weeks.length;
    var x = function (i) { return padL + (i * (W - padL - padR)) / (n - 1); };
    var y = function (v) { return H - padB - (v / 100) * (H - padT - padB); };
    var line = weeks.map(function (w, i) { return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(w.score).toFixed(1); }).join(" ");
    var area = "M" + x(0).toFixed(1) + " " + (H - padB) + " " +
      weeks.map(function (w, i) { return "L" + x(i).toFixed(1) + " " + y(w.score).toFixed(1); }).join(" ") +
      " L" + x(n - 1).toFixed(1) + " " + (H - padB) + " Z";

    var peakIdx = 0; weeks.forEach(function (w, i) { if (w.score === s.pico.score) peakIdx = i; });
    var svg = "";
    svg += '<defs><linearGradient id="gh" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#4f46e5" stop-opacity="0.10"/>' +
      '<stop offset="1" stop-color="#4f46e5" stop-opacity="0"/></linearGradient></defs>';
    // objetivo en 80
    svg += '<line x1="' + padL + '" y1="' + y(80).toFixed(1) + '" x2="' + (W - padR) + '" y2="' + y(80).toFixed(1) +
      '" stroke="var(--line)" stroke-dasharray="4 4" />';
    svg += '<text x="' + (W - padR) + '" y="' + (y(80) - 6).toFixed(1) + '" text-anchor="end" class="axis-lbl">objetivo 80</text>';
    svg += '<path d="' + area + '" fill="url(#gh)" />';
    svg += '<path d="' + line + '" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" class="draw" />';
    weeks.forEach(function (w, i) {
      var peak = i === peakIdx, last = i === n - 1;
      if (!peak && !last) return;
      var col = peak ? "var(--positive)" : (w.score < 80 ? "var(--danger)" : "var(--accent)");
      svg += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(w.score).toFixed(1) + '" r="5" fill="' + col + '" stroke="var(--panel)" stroke-width="2" />';
      // Solo etiquetamos el pico; el valor de la ultima semana ya sale en grande
      // en el callout, y aqui chocaria con la linea de objetivo.
      if (peak) {
        svg += '<text x="' + x(i).toFixed(1) + '" y="' + (y(w.score) - 12).toFixed(1) + '" text-anchor="middle" class="health-tag" fill="' + col + '">' + String(w.score).replace(".", ",") + "</text>";
      }
    });
    [0, peakIdx, n - 1].forEach(function (i) {
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle" class="axis-lbl">' + esc(weeks[i].iso_week.replace("2026-", "")) + "</text>";
    });
    $("health-chart").innerHTML = svg;
  }

  // ---------- spike line chart (SVG) ----------
  function renderSpike() {
    var trend = D.spike_trend || [];
    var an = D.anomaly;
    $("spike-title").textContent = "Coste semanal · " + (D.spike_team || "");
    if (an) $("spike-x").textContent = "x" + (Math.round(an.wow_ratio * 10) / 10).toString().replace(".", ",");
    if (an) {
      $("spike-lbl").textContent = "el coste de " + an.team + " pasó de " + eur2(an.prev_cost) +
        " a " + eur2(an.cost_eur) + " en " + an.iso_week + ", detectado por el agente.";
    }
    if (!trend.length) return;

    var W = 640, H = 260, padL = 16, padR = 16, padT = 28, padB = 30;
    var costs = trend.map(function (t) { return t.cost_eur; });
    var max = Math.max.apply(null, costs) * 1.12;
    var n = trend.length;
    var x = function (i) { return padL + (i * (W - padL - padR)) / (n - 1); };
    var y = function (v) { return H - padB - (v / max) * (H - padT - padB); };

    var spikeIdx = 0, spikeMax = -1;
    trend.forEach(function (t, i) { if (t.cost_eur > spikeMax) { spikeMax = t.cost_eur; spikeIdx = i; } });

    var line = trend.map(function (t, i) { return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(t.cost_eur).toFixed(1); }).join(" ");
    var area = "M" + x(0).toFixed(1) + " " + (H - padB) + " " +
      trend.map(function (t, i) { return "L" + x(i).toFixed(1) + " " + y(t.cost_eur).toFixed(1); }).join(" ") +
      " L" + x(n - 1).toFixed(1) + " " + (H - padB) + " Z";

    var svg = "";
    svg += '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#4f46e5" stop-opacity="0.10"/>' +
      '<stop offset="1" stop-color="#4f46e5" stop-opacity="0"/></linearGradient></defs>';
    // baseline
    svg += '<line x1="' + padL + '" y1="' + (H - padB) + '" x2="' + (W - padR) + '" y2="' + (H - padB) + '" stroke="var(--line)" />';
    svg += '<path d="' + area + '" fill="url(#g)" />';
    svg += '<path d="' + line + '" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" class="draw" />';
    // points
    trend.forEach(function (t, i) {
      var hot = i === spikeIdx;
      svg += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(t.cost_eur).toFixed(1) + '" r="' + (hot ? 5.5 : 3) +
        '" fill="' + (hot ? "var(--danger)" : "var(--panel)") + '" stroke="' + (hot ? "var(--danger)" : "var(--accent)") + '" stroke-width="2" />';
    });
    // spike annotation
    var sx = x(spikeIdx), sy = y(spikeMax);
    var anchor = spikeIdx > n / 2 ? "end" : "start";
    var tx = spikeIdx > n / 2 ? sx - 10 : sx + 10;
    svg += '<text x="' + tx.toFixed(1) + '" y="' + (sy - 12).toFixed(1) + '" text-anchor="' + anchor + '" class="spike-tag">' + eur(spikeMax) + "</text>";
    // x labels (first, spike, last)
    [0, spikeIdx, n - 1].forEach(function (i) {
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle" class="axis-lbl">' + esc(trend[i].iso_week.replace("2026-", "")) + "</text>";
    });
    $("spike-chart").innerHTML = svg;
  }

  // ---------- what-if simulator ----------
  function renderWhatif() {
    var w = D.whatif;
    if (!w || !w.weekly || !w.weekly.length) return;
    $("whatif-saved").textContent = eur2(w.saved_eur);
    $("whatif-lbl").textContent = "menos coste en " + w.spike_team + " en estas " + w.weeks +
      " semanas, redirigiendo el modelo caro al barato en tareas pequeñas.";
    $("whatif-annual").textContent = group(w.saved_annual_low_eur) + " a " + group(w.saved_annual_high_eur) + " €/año";

    var weekly = w.weekly, n = weekly.length;
    var W = 640, H = 260, padL = 16, padR = 16, padT = 28, padB = 30;
    var max = Math.max.apply(null, weekly.map(function (d) { return d.actual; })) * 1.12;
    var x = function (i) { return padL + (i * (W - padL - padR)) / (n - 1); };
    var y = function (v) { return H - padB - (v / max) * (H - padT - padB); };
    var line = function (key) {
      return weekly.map(function (d, i) { return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(d[key]).toFixed(1); }).join(" ");
    };
    // area de ahorro entre las dos lineas
    var area = "M" + x(0).toFixed(1) + " " + y(weekly[0].actual).toFixed(1) + " " +
      weekly.map(function (d, i) { return "L" + x(i).toFixed(1) + " " + y(d.actual).toFixed(1); }).join(" ") + " " +
      weekly.slice().reverse().map(function (d, i) { var idx = n - 1 - i; return "L" + x(idx).toFixed(1) + " " + y(d.counterfactual).toFixed(1); }).join(" ") + " Z";

    var svg = "";
    svg += '<line x1="' + padL + '" y1="' + (H - padB) + '" x2="' + (W - padR) + '" y2="' + (H - padB) + '" stroke="var(--line)" />';
    svg += '<path d="' + area + '" fill="var(--positive-soft)" />';
    svg += '<path d="' + line("actual") + '" fill="none" stroke="var(--danger)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />';
    svg += '<path d="' + line("counterfactual") + '" fill="none" stroke="var(--positive)" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" />';
    [0, Math.floor(n / 2), n - 1].forEach(function (i) {
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle" class="axis-lbl">' + esc(weekly[i].iso_week.replace("2026-", "")) + "</text>";
    });
    $("whatif-chart").innerHTML = svg;
    $("whatif-legend").innerHTML =
      '<span><i style="background:var(--danger)"></i> coste real</span>' +
      '<span><i style="background:var(--positive)"></i> con la política</span>';
  }

  // ---------- cost by team mini bars ----------
  function renderTeamBars() {
    var rows = D.cost_by_team || [];
    if (!rows.length) return;
    var max = Math.max.apply(null, rows.map(function (r) { return r.cost_eur; }));
    var hotTeam = D.spike_team;
    $("teambars").innerHTML = rows.map(function (r) {
      var w = (r.cost_eur / max) * 100;
      var hot = r.team === hotTeam ? " hot" : "";
      return '<div class="tb"><div>' + esc(r.team) + '</div>' +
        '<div class="tb-track"><div class="tb-fill' + hot + '" data-w="' + w.toFixed(1) + '"></div></div>' +
        '<div class="tb-val">' + eur(r.cost_eur) + "</div></div>";
    }).join("");
  }

  // ---------- evidence bars ----------
  function pctTxt(v) { return Math.round(v * 100) + "%"; }
  function renderEvidence() {
    var e = D.evidence || {};
    var rows = [];
    if (e.secrets) {
      rows.push({
        title: "Secretos en lenguaje natural",
        tool: e.secrets.tool_recall_nl, ia: e.secrets.llm_recall_nl,
        toolLabel: "Herramienta", iaLabel: "IA local", ci: e.secrets.llm_ci, n: e.secrets.ci_n,
      });
    }
    if (e.intent) {
      rows.push({
        title: "Clasificación de intención (bilingüe)",
        tool: e.intent.rule_acc, ia: e.intent.llm_acc,
        toolLabel: "Reglas", iaLabel: "IA local", ci: e.intent.llm_ci, n: e.intent.n,
      });
    }
    $("evidence").innerHTML = rows.map(function (r) {
      var ci = "";
      if (r.ci) {
        ci = '<div class="ev-ci">IA: entre ' + pctTxt(r.ci[0]) + " y " + pctTxt(r.ci[1]) + " de acierto (" + r.n + " casos)</div>";
      }
      return '<div class="ev-row"><div class="ev-title">' + esc(r.title) + "</div>" +
        bar(r.toolLabel, r.tool, "tool") + bar(r.iaLabel, r.ia, "ia") + ci + "</div>";
    }).join("");

    var n = (e.secrets ? e.secrets.total_n : 0) + (e.intent ? e.intent.n : 0);
    var capParts = [];
    if (n) capParts.push("medido sobre " + n + " casos etiquetados a mano (ES/EN)");
    if (e.intent && e.intent.rule_acc_en != null) {
      capParts.push("en inglés las reglas caen al " + pctTxt(e.intent.rule_acc_en) + ", la IA mantiene el " + pctTxt(e.intent.llm_acc_en));
    }
    $("ev-cap").textContent = capParts.join(" · ");
  }
  function bar(who, v, cls) {
    return '<div class="bar-line"><div class="who">' + esc(who) + "</div>" +
      '<div class="bar-track"><div class="bar-fill ' + cls + '" data-w="' + (v * 100).toFixed(0) + '"></div></div>' +
      '<div class="pct">' + pctTxt(v) + "</div></div>";
  }

  // ---------- secret catch ----------
  function renderSecret() {
    var s = D.nl_secret;
    if (!s) { return; }
    // resalta el fragmento del secreto (la contrasena dictada en prosa)
    var text = s.text;
    var html = esc(text);
    var m = text.match(/(clave|contrasena|password|pin)[^\d]*([A-Za-z0-9_#\-]{4,})/i);
    if (m) {
      var frag = m[0];
      html = esc(text).replace(esc(frag), "<mark>" + esc(frag) + "</mark>");
    }
    $("secret-quote").innerHTML = html;
    $("secret-foot").innerHTML = "Detectado en el equipo <strong>" + esc(s.team) +
      "</strong>. Una regex o un escáner tipo Gitleaks no lo ve: no hay firma ni alta entropía. La IA lo caza leyendo el sentido de la frase.";

    var pii = (D.evidence || {}).pii;
    if (pii) {
      $("pii-note").innerHTML = "La otra cara: la PII estructurada (IBAN, DNI, tarjeta) es territorio de la herramienta. " +
        "Regla más <strong>checksum</strong> (mod-97, letra del DNI, Luhn): precisión " + pctTxt(pii.precision) +
        " sobre " + pii.n + " casos y <strong>" + pii.decoys_fp + " falsos positivos</strong> en " + pii.decoys_n +
        " señuelos con dígito de control inválido. El LLM no calcula un mod-97: cada cosa, con su instrumento.";
    }
  }

  // ---------- animations ----------
  function animateBars(root) {
    root.querySelectorAll(".bar-fill[data-w], .tb-fill[data-w], .hc-fill[data-w], .cb-fill[data-w]").forEach(function (el) {
      requestAnimationFrame(function () { el.style.width = el.getAttribute("data-w") + "%"; });
    });
  }
  var briefPlayed = false;
  function reveal(el) {
    if (el.classList.contains("in")) return;
    el.classList.add("in");
    animateBars(el);
    if (!briefPlayed && D.brief && el.querySelector && el.querySelector("#resumen")) {
      briefPlayed = true;
      playBrief(D.brief);
    }
  }
  function observe() {
    var nodes = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) { nodes.forEach(reveal); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { reveal(en.target); io.unobserve(en.target); }
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -8% 0px" });
    nodes.forEach(function (el) { io.observe(el); });
    // Red de seguridad: nada queda oculto aunque el observer no dispare.
    setTimeout(function () { nodes.forEach(reveal); }, 3000);
  }

  // ---------- init ----------
  function init() {
    if (!window.ATLAS_DATA) {
      document.querySelector("main").innerHTML =
        '<div class="wrap" style="padding:80px 28px;color:var(--ink-2)">No hay datos. Ejecuta: <code>python -m atlas.cli export-dashboard</code></div>';
      return;
    }
    renderMeta();
    renderBrief();
    renderPolicy();
    renderCeilingSim();
    renderHealth();
    renderSpike();
    renderTeamBars();
    renderWhatif();
    renderEvidence();
    renderSecret();
    observe();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
