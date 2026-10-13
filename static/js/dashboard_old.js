/* SIVOTES · Dashboard en vivo (Bootstrap 5 + ECharts) */
(function () {
  "use strict";

  const REFRESH_MS = 15000;

  // ---------- Utilidades ----------
  const $ = (sel) => document.querySelector(sel);

  function fmtPct(n) {
    return (Math.round(n * 10) / 10).toFixed(1) + "%";
  }

  function ahora() {
    return new Date().toLocaleTimeString("es-PE", { hour12: false });
  }

  // ---------- Estado inicial ----------
  const initial = window.SIVOTES_INITIAL || { general: {}, mesas: [] };

  // ---------- ECharts: barras por mesa ----------
  const chartMesas = echarts.init($("#chartMesas"));

  function buildBarOption(mesas) {
    const labels = mesas.map((m) => `Mesa ${m.numero_mesa}`);
    const data = mesas.map((m) => {
      if (!m.habiles) return 0;
      return Math.round((m.emitidos / m.habiles) * 1000) / 10;
    });
    return {
      grid: { left: 50, right: 20, top: 30, bottom: 40 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => v + " %",
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { interval: 0, rotate: labels.length > 6 ? 30 : 0 },
      },
      yAxis: {
        type: "value",
        max: 100,
        axisLabel: { formatter: "{value} %" },
      },
      series: [
        {
          type: "bar",
          data: data,
          barWidth: "45%",
          itemStyle: { color: "#0d6efd", borderRadius: [6, 6, 0, 0] },
          label: {
            show: true,
            position: "top",
            formatter: "{c}%",
            color: "#0d6efd",
            fontWeight: "bold",
          },
        },
      ],
    };
  }

  // ---------- ECharts: anillo global ----------
  const chartGlobal = echarts.init($("#chartGlobal"));

  function buildDonutOption(emitidos, faltantes) {
    return {
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      legend: { bottom: 0, left: "center" },
      series: [
        {
          name: "Electores",
          type: "pie",
          radius: ["45%", "72%"],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
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
          data: [
            { value: emitidos,  name: "Emitidos",  itemStyle: { color: "#198754" } },
            { value: faltantes, name: "Faltantes", itemStyle: { color: "#ffc107" } },
          ],
        },
      ],
    };
  }

  // ---------- Render inicial ----------
  chartMesas.setOption(buildBarOption(initial.mesas));
  chartGlobal.setOption(
    buildDonutOption(initial.general.emitidos, initial.general.faltantes)
  );

  // ---------- Actualización dinámica ----------
  function updateKpis(g) {
    $("#kpi-habiles").textContent   = g.habiles;
    $("#kpi-emitidos").textContent  = g.emitidos;
    $("#kpi-faltantes").textContent = g.faltantes;
    $("#kpi-porcentaje").textContent = g.porcentaje + "%";

    const bar = $("#progress-bar");
    bar.style.width = g.porcentaje + "%";
    bar.textContent = g.porcentaje + "%";

    $("#progress-text").textContent = `${g.emitidos} / ${g.habiles} electores`;
  }

  function updateTabla(mesas) {
    const tbody = $("#mesas-tbody");
    if (!mesas.length) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="text-center text-secondary py-4">No hay mesas registradas para este proceso.</td></tr>';
      return;
    }
    tbody.innerHTML = mesas
      .map((m) => {
        const pct = m.habiles ? Math.round((m.emitidos / m.habiles) * 1000) / 10 : 0;
        return `
          <tr>
            <td><strong>${m.numero_mesa}</strong></td>
            <td class="text-secondary">${m.descripcion || "—"}</td>
            <td class="text-end">${m.habiles}</td>
            <td class="text-end">${m.emitidos}</td>
            <td>
              <div class="d-flex align-items-center gap-2">
                <div class="progress flex-grow-1" style="height:.6rem;">
                  <div class="progress-bar bg-primary" style="width:${pct}%;"></div>
                </div>
                <small class="text-secondary" style="min-width:2.5rem;text-align:right;">${pct}%</small>
              </div>
            </td>
          </tr>`;
      })
      .join("");
  }

  async function refresh() {
    try {
      const res = await fetch(window.SIVOTES_LIVE_URL, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      if (!data.activo) {
        $("#last-update").textContent = "Proceso cerrado · " + ahora();
        return;
      }
      updateKpis(data.general);
      updateTabla(data.mesas);
      chartMesas.setOption(buildBarOption(data.mesas), { notMerge: true });
      chartGlobal.setOption(
        buildDonutOption(data.general.emitidos, data.general.faltantes),
        { notMerge: true }
      );

      $("#last-update").textContent = "Actualizado: " + ahora();
    } catch (err) {
      console.warn("[SIVOTES] refresco fallido:", err);
      $("#last-update").textContent = "Error al actualizar · " + ahora();
    }
  }

  // Primera marca de tiempo
  $("#last-update").textContent = "Actualizado: " + ahora();
  setInterval(refresh, REFRESH_MS);

  // Redimensionado responsivo de los gráficos
  window.addEventListener("resize", () => {
    chartMesas.resize();
    chartGlobal.resize();
  });
})();
