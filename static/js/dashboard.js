/* ============================================================
   SIVOTES · Dashboard en vivo (Bootstrap 5 + ECharts)
   Requiere en el template:
     - window.SIVOTES_LIVE_URL  (url al endpoint JSON)
     - window.SIVOTES_INITIAL   (datos embebidos iniciales)
     - Contenedores: #chartMesas, #chartGlobal, #chartGrados,
       #chartSecciones
     - Elementos opcionales: #kpi-habiles, #kpi-emitidos,
       #kpi-faltantes, #kpi-porcentaje, #progress-pct,
       #progress-bar, #progress-text, #mesas-tbody, #last-update
   ============================================================ */
(function () {
  "use strict";

  // ---------------- Configuración ----------------
  var REFRESH_MS = 15000;

  // ---------------- Helpers ----------------
  function $(sel) {
    return document.querySelector(sel);
  }

  function ahora() {
    return new Date().toLocaleTimeString("es-PE", { hour12: false });
  }

  function setText(sel, value) {
    var el = $(sel);
    if (el) el.textContent = value;
  }

  function pctDe(emitidos, habiles) {
    if (!habiles) return 0;
    return Math.round((emitidos / habiles) * 1000) / 10;
  }

  // Clase de color de la barra según el porcentaje alcanzado.
  function claseBarra(pct) {
    if (pct >= 75) return "bg-success";
    return "bg-primary";
  }

  // Etiqueta (badge pill) del porcentaje, mismo color por umbral.
  function etiqueta(pct) {
    if (pct >= 75) return "text-bg-success";
    return "text-bg-primary";
  }

  // ---------------- Datos iniciales ----------------
  var boot = window.SIVOTES_INITIAL || { general: {}, mesas: [] };
  var initial = {
    general: boot.general || {},
    mesas: boot.mesas || [],
    grados: boot.grados || [],
    secciones: boot.secciones || [],
  };
  var estadoInicial = {
    iniciada: !!boot.votacionIniciada,
    pausada: !!boot.votacionPausada,
  };

  // ---------------- ECharts: instancias ----------------
  var chartMesasDom = document.getElementById("chartMesas");
  var chartGlobalDom = document.getElementById("chartGlobal");
  var chartGradosDom = document.getElementById("chartGrados");
  var chartSeccionesDom = document.getElementById("chartSecciones");

  function initChart(dom) {
    return dom && typeof echarts !== "undefined"
      ? echarts.init(dom)
      : null;
  }

  var chartMesas = initChart(chartMesasDom);
  var chartGlobal = initChart(chartGlobalDom);
  var chartGrados = initChart(chartGradosDom);
  var chartSecciones = initChart(chartSeccionesDom);

  if (!chartMesas || !chartGlobal || !chartGrados || !chartSecciones) {
    console.warn("[SIVOTES] ECharts no disponible o faltan contenedores de gráficos.");
  }

  function resizeAll() {
    [chartMesas, chartGlobal, chartGrados, chartSecciones].forEach(function (c) {
      if (c) c.resize();
    });
  }

  // ---------------- ECharts: opciones ----------------
  // Barra apilada al 100%: azul = emitidos (relleno), gris = lo que falta.
  function buildPctStackedOption(labels, emitidos, legend) {
    var falta = emitidos.map(function (v) {
      return Math.round((100 - v) * 10) / 10;
    });
    var rotar = labels.length > 6;

    return {
      animationDuration: 400,
      grid: { left: 40, right: 10, top: 26, bottom: rotar ? 70 : 30 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        formatter: function (params) {
          var partes = params.map(function (p) {
            return p.marker + p.seriesName + ": <b>" + p.value + "%</b>";
          });
          return params[0].name + "<br/>" + partes.join("<br/>");
        },
      },
      legend: legend || { top: 0, data: ["Emitidos", "Falta"] },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: {
          interval: 0,
          rotate: rotar ? 30 : 0,
        },
      },
      yAxis: {
        type: "value",
        max: 100,
        axisLabel: { formatter: "{value} %" },
      },
      series: [
        {
          name: "Emitidos",
          type: "bar",
          stack: "total",
          barWidth: rotar ? "60%" : "50%",
          barMinHeight: 2,
          data: emitidos,
          itemStyle: { color: "#0d6efd" },
          label: {
            show: true,
            position: "insideTop",
            color: "#fff",
            fontWeight: "bold",
            formatter: function (p) { return p.value + "%"; },
          },
        },
        {
          name: "Falta",
          type: "bar",
          stack: "total",
          barMinHeight: 2,
          data: falta,
          itemStyle: { color: "#e9ecef" },
          label: {
            show: true,
            position: "inside",
            color: "#adb5bd",
            formatter: function (p) { return p.value > 0 ? p.value + "%" : ""; },
          },
        },
      ],
    };
  }

  function buildGradosOption(grados) {
    return buildPctStackedOption(
      grados.map(function (g) { return g.grado; }),
      grados.map(function (g) { return pctDe(g.emitidos, g.habiles); })
    );
  }

  function buildSeccionesOption(secciones) {
    return buildPctStackedOption(
      secciones.map(function (s) { return s.grado + " " + s.seccion; }),
      secciones.map(function (s) { return pctDe(s.emitidos, s.habiles); })
    );
  }

  function buildMesasOption(mesas) {
    return buildPctStackedOption(
      mesas.map(function (m) { return "Mesa " + m.numero_mesa; }),
      mesas.map(function (m) { return pctDe(m.emitidos, m.habiles); })
    );
  }

  function buildDonutOption(emitidos, faltantes) {
    var e = Number(emitidos) || 0;
    var f = Number(faltantes) || 0;
    var total = e + f;

    return {
      animationDuration: 400,
      tooltip: {
        trigger: "item",
        formatter: "{b}: {c} ({d}%)",
      },
      legend: { bottom: 0, left: "center" },
      series: [{
        name: "Electores",
        type: "pie",
        radius: ["50%", "75%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: "bold",
            formatter: "{b}\n{c}",
          },
        },
        labelLine: { show: false },
        data: total === 0
          ? [{ value: 1, name: "Sin electores", itemStyle: { color: "#e9ecef" } }]
          : [
              { value: e, name: "Emitidos",  itemStyle: { color: "#198754" } },
              { value: f, name: "Faltantes", itemStyle: { color: "#ffc107" } },
            ],
      }],
    };
  }

  // ---------------- KPIs ----------------
  function updateKpis(g) {
    g = g || {};

    setText("#kpi-habiles", g.habiles != null ? g.habiles : 0);
    setText("#kpi-emitidos", g.emitidos != null ? g.emitidos : 0);
    setText("#kpi-faltantes", g.faltantes != null ? g.faltantes : 0);

    var pct = Number(g.porcentaje) || 0;
    var pctTxt = pct + "%";

    setText("#kpi-porcentaje", pctTxt);
    setText("#progress-pct", pctTxt);

    var bar = $("#progress-bar");
    if (bar) bar.style.width = pct + "%";

    var pTxt = $("#progress-text");
    if (pTxt) {
      pTxt.textContent = (g.emitidos || 0) + " / " + (g.habiles || 0) + " electores";
    }
  }

  // ---------------- Tabla de mesas ----------------
  function updateTabla(mesas) {
    var tbody = $("#mesas-tbody");
    if (!tbody) return;

    if (!mesas || !mesas.length) {
      tbody.innerHTML =
        '<tr><td colspan="4" class="text-center text-secondary py-3 small">' +
        'No hay mesas registradas.</td></tr>';
      return;
    }

    tbody.innerHTML = mesas.map(function (m) {
      var pct = pctDe(m.emitidos, m.habiles);
      var desc = m.descripcion
        ? '<div class="text-secondary small">' + m.descripcion + '</div>'
        : '';
      var barra = claseBarra(pct);

      return (
        '<tr>' +
          '<td><strong>' + m.numero_mesa + '</strong>' + desc + '</td>' +
          '<td class="text-end">' + m.habiles + '</td>' +
          '<td class="text-end">' + m.emitidos + '/' + m.habiles + '</td>' +
          '<td>' +
            '<div class="d-flex align-items-center gap-2">' +
              '<div class="progress flex-grow-1" style="height:.65rem;">' +
                '<div class="progress-bar ' + barra + '" style="width:' + pct + '%;"></div>' +
              '</div>' +
              '<span class="badge rounded-pill ' + etiqueta(pct) + '" style="min-width:2.9rem;font-size:.8rem;">' +
                pct + '%' +
              '</span>' +
            '</div>' +
          '</td>' +
        '</tr>'
      );
    }).join("");
  }

  // ---------------- Render combinado ----------------
  function renderAll(general, mesas, grados, secciones) {
    updateKpis(general || {});
    updateTabla(mesas || []);

    if (chartMesas) {
      chartMesas.setOption(buildMesasOption(mesas || []), { notMerge: true });
    }
    if (chartGlobal) {
      chartGlobal.setOption(
        buildDonutOption((general || {}).emitidos, (general || {}).faltantes),
        { notMerge: true }
      );
    }
    if (chartGrados) {
      chartGrados.setOption(buildGradosOption(grados || []), { notMerge: true });
    }
    if (chartSecciones) {
      chartSecciones.setOption(buildSeccionesOption(secciones || []), { notMerge: true });
    }
    resizeAll();
  }

  // ---------------- Refresco periódico ----------------
  function refresh() {
    var url = window.SIVOTES_LIVE_URL;
    if (!url) return;

    fetch(url, {
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(function (res) {
        var ctype = res.headers.get("content-type") || "";
        if (!res.ok) {
          return res.text().then(function (txt) {
            console.error(
              "[SIVOTES] HTTP " + res.status + " en " + res.url +
              "\nRespuesta: " + txt.slice(0, 300)
            );
            throw new Error("HTTP " + res.status + " (" + (ctype.split(";")[0] || "sin content-type") + ")");
          });
        }
        if (ctype.indexOf("application/json") === -1) {
          return res.text().then(function (txt) {
            console.error(
              "[SIVOTES] Respuesta no-JSON en " + res.url +
              " (" + ctype + "): " + txt.slice(0, 300)
            );
            throw new Error("Respuesta no-JSON");
          });
        }
        return res.json();
      })
      .then(function (data) {
        var lastUpd = $("#last-update");

        if (!data.activo) {
          if (lastUpd) lastUpd.textContent = "Proceso cerrado · " + ahora();
          return;
        }

        // Si el estado de la jornada cambió (otro panel inició/pausó/reanudó),
        // recargamos para refrescar badge y botones.
        if (!!data.votacion_iniciada !== estadoInicial.iniciada ||
            !!data.votacion_pausada !== estadoInicial.pausada) {
          window.location.reload();
          return;
        }

        renderAll(data.general, data.mesas, data.grados, data.secciones);
        if (lastUpd) lastUpd.textContent = "Actualizado: " + ahora();
      })
      .catch(function (err) {
        console.warn("[SIVOTES] refresco fallido:", err);
        var lastUpd = $("#last-update");
        if (lastUpd) {
          lastUpd.textContent = "Error al actualizar · " + ahora() + " · " + err.message;
        }
      });
  }

  // ---------------- Arranque ----------------
  renderAll(initial.general, initial.mesas, initial.grados, initial.secciones);
  setText("#last-update", "Actualizado: " + ahora());

  // Redimensionado tras layout/fuentes
  window.addEventListener("load", resizeAll);

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(resizeAll);
  }

  // Ciclo de refresco
  setInterval(refresh, REFRESH_MS);

  window.addEventListener("resize", resizeAll);
})();